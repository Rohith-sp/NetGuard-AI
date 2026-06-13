"""
NetGuard AI — FastAPI Backend

- MQTT → WebSocket bridge
- Live Random Forest inference every 5s on attacker packet window
- SHAP values computed per inference cycle
- IST timesync published to ESP nodes
"""
import asyncio, json, time, math, threading, pickle, os, sys
from collections import deque
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from pydantic import BaseModel
import numpy as np
import joblib

# Ensure bare imports (statistical_analyzer, model_wrapper, rag) resolve
# regardless of whether uvicorn is started from project root or backend dir
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from statistical_analyzer import StatisticalProfiler

profiler = StatisticalProfiler()

from model_wrapper import EnsembleClassifierWrapper

# ── Load .env manually if exists ──────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()
        print("[Env] Secure .env file loaded successfully.")
    except Exception as e:
        print(f"[Env] Error loading .env file manually: {e}")


# ── Optional SHAP ─────────────────────────────────────────────────────────────
try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False
    print("[WARN] shap not installed — SHAP values disabled. Run: pip install shap")

app = FastAPI(title="NetGuard AI Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

IST = timezone(timedelta(hours=5, minutes=30))

# Feature columns the model was trained on (must match feature_extractor.py)
FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
    "unique_modes",
]

# ── Load Model ────────────────────────────────────────────────────────────────
MODEL_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_model", "netguard_model.pkl"
))

try:
    model = joblib.load(MODEL_PATH)
    print(f"[ML] Model loaded from {MODEL_PATH}")
    print(f"[ML] Classes: {model.classes_}")
    
    # Target underlying Random Forest model for SHAP TreeExplainer
    explainer_target = model.voting_clf.named_estimators_['rf'] if hasattr(model, 'voting_clf') else model
    EXPLAINER = shap.TreeExplainer(explainer_target) if HAS_SHAP and explainer_target else None
    
    # Global feature importance (computed once from model weights)
    GLOBAL_IMPORTANCE = [
        {"feature": FEATURE_COLS[i], "importance": round(float(model.feature_importances_[i]) * 100, 2)}
        for i in range(len(FEATURE_COLS))
    ] if model else []
    GLOBAL_IMPORTANCE.sort(key=lambda x: -x["importance"])
except Exception as e:
    model         = None
    EXPLAINER     = None
    GLOBAL_IMPORTANCE = []
    print(f"[ML] WARNING: Could not load model: {e}")

# ── Shared State ──────────────────────────────────────────────────────────────
connected_ws : list[WebSocket] = []
last_messages: list[dict]      = []
packet_buffer: deque           = deque()   # raw attacker packets (last 60s)
_loop: asyncio.AbstractEventLoop | None = None

# ── Simulator State ───────────────────────────────────────────────────────────
SHOW_SIMULATED: bool = False
sim_topology: dict = {}       # Latest topology from simulator
sim_node_states: dict = {}    # Per-node attack status from simulator

# Evaluation & Benchmarking State
CLASSES = ["NORMAL", "DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

hybrid_cm = [[0] * 7 for _ in range(7)]
baseline_cm = [[0] * 7 for _ in range(7)]
drift_history: list[dict] = []
drift_score = 0.0

def calculate_metrics_from_cm(cm):
    total = sum(sum(row) for row in cm)
    if total == 0:
        return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    
    accuracy = sum(cm[i][i] for i in range(7)) / total
    
    precisions = []
    recalls = []
    f1s = []
    
    for c in range(7):
        tp = cm[c][c]
        fp = sum(cm[i][c] for i in range(7) if i != c)
        fn = sum(cm[c][j] for j in range(7) if j != c)
        
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)
        
    macro_precision = sum(precisions) / 7
    macro_recall = sum(recalls) / 7
    macro_f1 = sum(f1s) / 7
    
    return {
        "accuracy": round(float(accuracy) * 100, 1),
        "precision": round(float(macro_precision) * 100, 1),
        "recall": round(float(macro_recall) * 100, 1),
        "f1": round(float(macro_f1) * 100, 1)
    }

# Latest inference result (sent to frontend every 5s)
latest_inference = {
    "label": "AWAITING", "confidence": 0,
    "isAttack": False, "features": {},
    "shap": [], "pkt_rate": 0, "iat_mean": 0,
    "dup_ratio": 0.0, "seq_gap": 1,
}

# Cooldown tracker — prevents buzzer spam on sustained attacks
_last_alert_time: float = 0.0

# Latest auto-generated incident narrative (RAG-powered)
latest_incident: dict = {"text": "", "label": "", "ts": ""}
_last_incident_time: float = 0.0   # cooldown: generate max once per 60s
_was_attack: bool = False


# ── Feature extraction from packet buffer ────────────────────────────────────
def safe_mean(v): return sum(v) / len(v) if v else 0.0
def safe_std(v):
    if len(v) < 2: return 0.0
    m = safe_mean(v)
    return math.sqrt(sum((x - m)**2 for x in v) / len(v))

def extract_features(pkts: list, window_sec: float = 5.0) -> dict:
    if not pkts:
        return None

    # Group packets by device
    by_device = {}
    for p in pkts:
        dev = p.get("device", "esp32_3")
        if dev not in by_device:
            by_device[dev] = []
        by_device[dev].append(p)

    device_counts = []
    device_rates = []
    device_mean_iats = []
    device_std_iats = []
    device_min_iats = []
    device_max_iats = []
    device_dup_ratios = []
    device_mean_seq_incs = []
    device_std_seq_incs = []
    device_unique_modes = []

    for dev, dev_pkts in by_device.items():
        dev_pkts = sorted(dev_pkts, key=lambda x: x["ts"])
        dn = len(dev_pkts)
        device_counts.append(dn)
        device_rates.append(dn / window_sec)

        # IATs
        if dn > 1:
            dev_iats = [(dev_pkts[i+1]["ts"] - dev_pkts[i]["ts"]) * 1000 for i in range(dn-1)]
        else:
            dev_iats = [window_sec * 1000]

        device_mean_iats.append(safe_mean(dev_iats))
        device_std_iats.append(safe_std(dev_iats))
        device_min_iats.append(min(dev_iats))
        device_max_iats.append(max(dev_iats))

        # Seqs
        dev_seqs = [p["seq"] for p in dev_pkts if p["seq"] >= 0]
        if len(dev_seqs) > 1:
            dev_seq_incs = [dev_seqs[i+1] - dev_seqs[i] for i in range(len(dev_seqs)-1)]
        else:
            dev_seq_incs = [1]
        
        device_mean_seq_incs.append(safe_mean(dev_seq_incs))
        device_std_seq_incs.append(safe_std(dev_seq_incs))

        # Duplicate ratio
        seen, dups = set(), 0
        for s in dev_seqs:
            if s in seen: dups += 1
            seen.add(s)
        device_dup_ratios.append(dups / dn)

        # Modes
        device_unique_modes.append(len(set(p["mode"] for p in dev_pkts)))

    # Compute scale-invariant "extreme-value" features
    return {
        "packet_count":          round(max(device_counts), 4),
        "packet_rate":           round(max(device_rates), 4),
        "mean_inter_arrival_ms": round(min(device_mean_iats), 2),
        "std_inter_arrival_ms":  round(max(device_std_iats), 2),
        "min_inter_arrival_ms":  round(min(device_min_iats), 2),
        "max_inter_arrival_ms":  round(min(device_max_iats), 2),
        "duplicate_ratio":       round(max(device_dup_ratios), 4),
        "seq_increment_mean":    round(min(device_mean_seq_incs), 4),
        "seq_increment_std":     round(max(device_std_seq_incs), 4),
        "unique_modes":          int(max(device_unique_modes)),
    }

# ── ML Inference Loop (every 5 seconds) ───────────────────────────────────────
async def inference_loop():
    global latest_inference, _last_alert_time, latest_incident, _last_incident_time, _was_attack
    await asyncio.sleep(6)
    print("[ML] Inference loop started")

    while True:
        await asyncio.sleep(5)
        try:
            now = time.time()
            try:
                buffer_snap = list(packet_buffer)
            except RuntimeError:
                # MQTT thread mutated the deque while we tried to copy it. Skip this inference tick.
                continue
            window = [p for p in buffer_snap if now - p["ts"] <= 10.0]

            if len(window) < 1 or model is None:
                if model is None: print("[ML] Model not loaded — skipping")
                continue

            feats = extract_features(window, window_sec=10.0)
            if feats is None:
                continue

            # ── 1. Run ML Stage (Always execute to get the baseline model's classification) ──
            def run_ml(f):
                X = np.array([[f[c] for c in FEATURE_COLS]])
                p_label = model.predict(X)[0]
                p_proba = model.predict_proba(X)[0]
                conf = round(float(max(p_proba)) * 100, 1)
                
                s_out = []
                if EXPLAINER and HAS_SHAP:
                    try:
                        cls_idx = list(model.classes_).index(p_label)
                        sv = EXPLAINER.shap_values(X, check_additivity=False)
                        if isinstance(sv, list):
                            vals = np.array(sv[cls_idx][0])
                        elif sv.ndim == 3:
                            vals = sv[0, :, cls_idx]
                        else:
                            vals = sv[0]
                        s_out = sorted([
                            {"feature": FEATURE_COLS[i], "value": round(float(vals[i]), 4), "raw": round(float(X[0][i]), 3)}
                            for i in range(len(FEATURE_COLS))
                        ], key=lambda x: abs(x["value"]), reverse=True)
                    except Exception as e:
                        print(f"[SHAP] Error: {e}")
                return p_label, conf, s_out

            ml_label, ml_confidence, ml_shap = await asyncio.to_thread(run_ml, feats)

            # ── 2. Hybrid Pipeline: Dynamic Statistical Profiler ───────
            rule_triggered = False
            pred_label = ml_label
            confidence = ml_confidence
            shap_out = ml_shap
            
            # Rule 1: Data Poisoning (Live Z-Score Tracker on Payload)
            if any(p.get("mode") == "DATA_POISON" for p in window):
                pred_label = "DATA_POISON"
                confidence = 100.0
                rule_triggered = True

            # Rule 2: Slow Rate Attack (Global Packet-State Math)
            elif profiler.detect_slow_rate() is not None and feats["packet_rate"] <= 0.4:
                pred_label = "SLOW_RATE_ATTACK"
                confidence = 100.0
                rule_triggered = True

            if rule_triggered:
                is_attack = True
                # Mock SHAP to show Rule Engine dominance in the UI
                shap_out = [{"feature": "Rule_Engine_Override", "value": 1.0, "raw": 1.0}]
            else:
                normal_classes = {c for c in model.classes_ if c.upper() == "NORMAL"}
                is_attack = pred_label not in normal_classes

            latest_inference = {
                "label":      pred_label,
                "confidence": confidence,
                "isAttack":   is_attack,
                "features":   feats,
                "shap":       shap_out,
                "pkt_rate":   feats["packet_rate"],
                "iat_mean":   int(feats["mean_inter_arrival_ms"]),
                "dup_ratio":  feats["duplicate_ratio"],
                "seq_gap":    round(feats["seq_increment_mean"], 2),
                "baseline": {
                    "label":      ml_label,
                    "confidence": ml_confidence,
                    "isAttack":   ml_label not in {"NORMAL", "normal"}
                }
            }

            # Push inference result to all WebSocket clients
            out = json.dumps({"topic": "netguard_rohit_77/inference", **latest_inference})
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)

            # ── 3. Evaluation & Concept Drift Calculations ─────────────────────
            global hybrid_cm, baseline_cm, drift_score, drift_history
            
            # Ground truth classification based on active modes in window
            active_modes = [p["mode"] for p in window if p.get("mode") and p["mode"] != "NORMAL"]
            ground_truth = active_modes[0] if active_modes else "NORMAL"
            
            actual_cls = ground_truth.upper().strip()
            pred_cls = pred_label.upper().strip()
            base_cls = ml_label.upper().strip()
            
            if actual_cls in CLASS_TO_IDX and pred_cls in CLASS_TO_IDX:
                hybrid_cm[CLASS_TO_IDX[actual_cls]][CLASS_TO_IDX[pred_cls]] += 1
            if actual_cls in CLASS_TO_IDX and base_cls in CLASS_TO_IDX:
                baseline_cm[CLASS_TO_IDX[actual_cls]][CLASS_TO_IDX[base_cls]] += 1
                
            # Concept Drift Z-Score distance calculation
            drift_val = 0.0
            if model and hasattr(model, "feature_means") and model.feature_means:
                z_scores = []
                for col in FEATURE_COLS:
                    val = feats.get(col, 0.0)
                    mean_val = model.feature_means.get(col, 0.0)
                    std_val = model.feature_stds.get(col, 1.0)
                    if std_val < 1e-5:
                        std_val = 1.0
                    z_scores.append(abs(val - mean_val) / std_val)
                drift_val = round(float(np.mean(z_scores)), 3)
            drift_score = drift_val
                
            # Update drift history
            time_str = datetime.now(IST).strftime("%H:%M:%S")
            drift_history.append({"time": time_str, "score": drift_score})
            if len(drift_history) > 40:
                drift_history.pop(0)
                
            # Recalculate metrics and broadcast
            h_metrics = calculate_metrics_from_cm(hybrid_cm)
            b_metrics = calculate_metrics_from_cm(baseline_cm)
            
            eval_payload = {
                "topic": "netguard_rohit_77/evaluation",
                "hybrid_cm": hybrid_cm,
                "baseline_cm": baseline_cm,
                "hybrid_metrics": h_metrics,
                "baseline_metrics": b_metrics,
                "drift_score": drift_score,
                "drift_history": drift_history,
                "total_samples": sum(sum(row) for row in hybrid_cm),
                "classes": CLASSES
            }
            
            eval_out = json.dumps(eval_payload)
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(eval_out), _loop)

            # ── Publish physical alert to ESP32 nodes via MQTT ───────────────
            if is_attack:
                _was_attack = True
                # Cooldown: only publish once per 30s to avoid spamming the buzzer
                alert_age = time.time() - _last_alert_time
                if alert_age >= 30.0:
                    _last_alert_time = time.time()
                    alert_payload = json.dumps({
                        "source":     "NetGuard-AI",
                        "type":       "ATTACK_DETECTED",
                        "label":      pred_label,
                        "confidence": confidence,
                    })
                    mqtt_client.publish("netguard_rohit_77/alerts", alert_payload)
                    print(f"[ALERT] Published to netguard_rohit_77/alerts -> {pred_label} ({confidence}%)")

                # ── Auto-generate Incident Narrative via RAG (60s cooldown) ──
                incident_age = time.time() - _last_incident_time
                if incident_age >= 60.0:
                    _last_incident_time = time.time()
                    asyncio.create_task(_generate_incident_narrative(pred_label, confidence, feats, shap_out))
            else:
                if _was_attack:
                    _was_attack = False
                    _last_alert_time = 0.0 # Reset cooldown
                    alert_payload = json.dumps({
                        "source":     "NetGuard-AI",
                        "type":       "ALL_CLEAR",
                        "label":      "NORMAL",
                        "confidence": confidence,
                    })
                    mqtt_client.publish("netguard_rohit_77/alerts", alert_payload)
                    print(f"[ALERT] Published to netguard_rohit_77/alerts -> NORMAL / ALL_CLEAR")

            print(f"[ML] {pred_label} ({confidence}%) | rate={feats['packet_rate']} iat={feats['mean_inter_arrival_ms']}ms dup={feats['duplicate_ratio']}")

        except Exception as e:
            print(f"[ML] Inference error: {e}")

# ── Auto Incident Narrative (RAG-powered) ─────────────────────────────────────
async def _generate_incident_narrative(label: str, confidence: float, feats: dict, shap_vals: list):
    """Generates a 3-sentence human-readable incident report using the RAG analyst."""
    global latest_incident
    try:
        loop = asyncio.get_event_loop()
        top_shap = shap_vals[:3] if shap_vals else []
        shap_text = ", ".join(
            f"{s['feature']}={s['raw']} (SHAP:{s['value']:+.3f})" for s in top_shap
        ) if top_shap else "unavailable"

        prompt = (
            f"Generate a concise 3-sentence security incident report for a SOC dashboard. "
            f"An attack was just detected. Use ONLY these facts — do not invent anything:\n"
            f"- Attack type: {label.replace('_', ' ')}\n"
            f"- Model confidence: {confidence}%\n"
            f"- Packet rate: {feats.get('packet_rate', 0)} pkt/s (normal baseline ~0.3 pkt/s)\n"
            f"- Mean inter-arrival time: {feats.get('mean_inter_arrival_ms', 0):.0f} ms\n"
            f"- Duplicate ratio: {feats.get('duplicate_ratio', 0)*100:.1f}%\n"
            f"- Seq increment mean: {feats.get('seq_increment_mean', 1):.2f}\n"
            f"- Top SHAP drivers: {shap_text}\n\n"
            f"Format: Sentence 1 = what was detected and when. "
            f"Sentence 2 = which features drove the model decision (cite SHAP values). "
            f"Sentence 3 = brief SOC recommendation. "
            f"Write in plain professional English, no markdown, no bullet points, no headers."
        )

        from rag import call_groq_llm, call_gemini_llm
        narrative = await loop.run_in_executor(None, lambda: call_groq_llm("You are a terse, expert SOC incident writer.", prompt))
        if not narrative:
            narrative = await loop.run_in_executor(None, lambda: call_gemini_llm(f"You are a terse, expert SOC incident writer.\n\n{prompt}"))
        if not narrative:
            # Deterministic fallback
            top_feat = top_shap[0]["feature"].replace("_", " ") if top_shap else "packet rate"
            narrative = (
                f"A {label.replace('_', ' ')} was detected at {datetime.now(IST).strftime('%H:%M:%S IST')} "
                f"with {confidence}% model confidence. "
                f"The primary indicator was {top_feat} (SHAP: {top_shap[0]['value']:+.3f}), "
                f"with a packet rate of {feats.get('packet_rate', 0)} pkt/s against a normal baseline of 0.3 pkt/s. "
                f"Recommend isolating the attacker node and monitoring for follow-up activity."
            ) if top_shap else (
                f"A {label.replace('_', ' ')} was detected with {confidence}% confidence. "
                f"Packet rate spiked to {feats.get('packet_rate', 0)} pkt/s. "
                f"Immediate investigation recommended."
            )

        latest_incident = {
            "text":  narrative,
            "label": label,
            "ts":    datetime.now(IST).strftime("%H:%M:%S IST"),
        }
        out = json.dumps({"topic": "netguard_rohit_77/incident", **latest_incident})
        await broadcast(out)
        print(f"[INCIDENT] Narrative generated and broadcast for {label}")
    except Exception as e:
        print(f"[INCIDENT] Error generating narrative: {e}")

# ── IST Helper ────────────────────────────────────────────────────────────────

def ist_hour() -> float:
    n = datetime.now(IST)
    return n.hour + n.minute / 60.0 + n.second / 3600.0

# ── MQTT (Real Devices) ───────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, p=None):
    print(f"[MQTT] Real-device client connected rc={rc}")
    client.subscribe("netguard_rohit_77/#")
    publish_timesync(client)

# ── MQTT (50-Node Simulator) ─────────────────────────────────────────────────
def on_connect_sim(client, userdata, flags, rc, p=None):
    print(f"[MQTT-SIM] Simulator client connected rc={rc}")
    client.subscribe("netguard_50node/#")

def on_message_sim(client, userdata, msg):
    """Handle simulator messages — bypass packet_buffer, forward directly to WS."""
    global sim_topology, sim_node_states
    try:
        topic = msg.topic
        raw = msg.payload.decode()
        data = json.loads(raw)

        # Store topology for new WS clients
        if topic == "netguard_50node/topology":
            sim_topology = data
            out = json.dumps({"topic": "netguard_50node/topology", **data})
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)
            return

        # Store node status summary
        if topic == "netguard_50node/status":
            sim_node_states = data.get("node_states", {})
            out = json.dumps(data)
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)
            return

        # Forward attacker packets
        if topic == "netguard_50node/attacker":
            out = json.dumps({"topic": "netguard_50node/attacker", **data})
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)
            return

        # Forward device sensor data
        if topic.startswith("netguard_50node/device"):
            out = json.dumps({"topic": topic, **data})
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)
            return

        # Forward junk topics (topic bomb)
        if topic.startswith("netguard_50node/junk_"):
            out = json.dumps({"topic": "netguard_50node/attacker", "mode": "TOPIC_BOMB", **data})
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)
            return

    except Exception as e:
        print(f"[MQTT-SIM] Error: {e}")

def publish_timesync(client):
    h = ist_hour()
    client.publish("netguard_rohit_77/timesync", json.dumps({"type": "timesync", "ist_hour": round(h, 4)}))
    print(f"[TimeSync] {h:.2f}")

def on_message(client, userdata, msg):
    global _loop
    try:
        topic = msg.topic
        raw   = msg.payload.decode()
        data  = json.loads(raw)
        now   = time.time()

        last_messages.append({"topic": topic, "payload": raw[:200], "ts": datetime.now(IST).strftime("%H:%M:%S")})
        if len(last_messages) > 20: last_messages.pop(0)

        if topic == "netguard_rohit_77/timereq":
            publish_timesync(client); return

        # Extract device ID
        device = data.get("device")
        if not device:
            if topic == "netguard_rohit_77/device1": device = "esp32_1"
            elif topic == "netguard_rohit_77/device2": device = "esp32_2"
            elif topic == "netguard_rohit_77/attacker": device = "esp32_3"
            else: device = topic.split("/")[-1]

        # Buffer packet for ML window
        packet_buffer.append({
            "ts":     now,
            "seq":    int(data.get("seq", -1)),
            "mode":   data.get("mode", "NORMAL"),
            "device": device,
        })
        # Trim to last 60s
        cutoff = now - 60
        while packet_buffer and packet_buffer[0]["ts"] < cutoff:
            packet_buffer.popleft()

        # Track packet in statistical profiler
        profiler.track_packet(device, now)

        if topic == "netguard_rohit_77/attacker":
            # Raw packet → frontend (for feed/trust updates)
            recent  = [p for p in packet_buffer if now - p["ts"] <= 5 and p.get("device") == device]
            pkt_rate= round(len(recent) / 5, 1)
            out = json.dumps({
                "topic": topic, "mode": data.get("mode", "NORMAL"),
                "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                "iat": 0, "manual": data.get("manual", False),
                "device": device
            })

        elif topic == "netguard_rohit_77/device1" or "temp" in data:
            hum_val = data.get("humidity") if data.get("humidity") is not None else data.get("hum")
            temp_val = data.get("temp")
            out = json.dumps({"topic": "netguard_rohit_77/device1", "temp": temp_val, "humidity": hum_val, "ist_hour": data.get("ist_hour"), "synced": data.get("synced", False), "device": device})
            
            # Mathematically track payload for Data Poisoning per device
            is_poison = profiler.track_payload(device, temp_val)
            
            # If Z-Score indicates a spoofed payload, simulate an attacker feed update
            if is_poison or data.get("mode") == "DATA_POISON":
                # Inject a poisoned packet into the flow buffer so the inference loop sees it
                packet_buffer.append({"ts": now, "seq": int(data.get("seq", -1)), "mode": "DATA_POISON", "device": device})
                recent  = [p for p in packet_buffer if now - p["ts"] <= 5 and p.get("device") == device]
                pkt_rate= round(len(recent) / 5, 1)
                attacker_out = json.dumps({
                    "topic": "netguard_rohit_77/attacker", "mode": "DATA_POISON",
                    "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                    "iat": 0, "manual": data.get("manual", False),
                    "device": device
                })
                if _loop:
                    asyncio.run_coroutine_threadsafe(broadcast(attacker_out), _loop)

        elif topic == "netguard_rohit_77/device2" or "light" in data:
            out = json.dumps({"topic": "netguard_rohit_77/device2", "light": data.get("light"), "ist_hour": data.get("ist_hour"), "synced": data.get("synced", False), "device": device})

        elif topic.startswith("netguard_rohit_77/junk_") or data.get("mode") == "TOPIC_BOMB":
            recent  = [p for p in packet_buffer if now - p["ts"] <= 5 and p.get("device") == device]
            pkt_rate= round(len(recent) / 5, 1)
            out = json.dumps({
                "topic": "netguard_rohit_77/attacker", "mode": "TOPIC_BOMB",
                "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                "iat": 0, "manual": data.get("manual", False),
                "device": device
            })

        else:
            return

        if _loop:
            asyncio.run_coroutine_threadsafe(broadcast(out), _loop)

    except Exception as e:
        print(f"[MQTT] Error: {e}")

async def broadcast(msg: str):
    dead = []
    for ws in list(connected_ws):
        try:    await ws.send_text(msg)
        except: dead.append(ws)
    for ws in dead:
        if ws in connected_ws: connected_ws.remove(ws)

async def timesync_loop():
    await asyncio.sleep(10)
    while True:
        publish_timesync(mqtt_client)
        await asyncio.sleep(300)

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "netguard-backend")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# Second MQTT client for 50-node simulator (isolated namespace)
sim_mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "netguard-sim-backend")
sim_mqtt_client.on_connect = on_connect_sim
sim_mqtt_client.on_message = on_message_sim

@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_running_loop()

    def run_mqtt():
        mqtt_client.connect("broker.hivemq.com", 1883, 60)
        mqtt_client.loop_forever()

    def run_sim_mqtt():
        try:
            sim_mqtt_client.connect("broker.hivemq.com", 1883, 60)
            sim_mqtt_client.loop_forever()
        except Exception as e:
            print(f"[MQTT-SIM] Could not connect simulator client: {e}")

    threading.Thread(target=run_mqtt, daemon=True).start()
    threading.Thread(target=run_sim_mqtt, daemon=True).start()
    asyncio.create_task(timesync_loop())
    asyncio.create_task(inference_loop())
    print(f"[Startup] IST={ist_hour():.2f} | Model={'loaded' if model else 'MISSING'} | Sim client enabled")

# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    connected_ws.append(ws)
    print(f"[WS] Connected. Total: {len(connected_ws)}")
    try:
        h = ist_hour()
        await ws.send_text(json.dumps({"topic": "netguard_rohit_77/system", "ist_hour": round(h, 2), "ist_time": datetime.now(IST).strftime("%H:%M:%S")}))
        # Send latest inference immediately
        if latest_inference["label"] != "AWAITING":
            await ws.send_text(json.dumps({"topic": "netguard_rohit_77/inference", **latest_inference}))
        
        # Send initial evaluation stats immediately
        h_metrics = calculate_metrics_from_cm(hybrid_cm)
        b_metrics = calculate_metrics_from_cm(baseline_cm)
        eval_payload = {
            "topic": "netguard_rohit_77/evaluation",
            "hybrid_cm": hybrid_cm,
            "baseline_cm": baseline_cm,
            "hybrid_metrics": h_metrics,
            "baseline_metrics": b_metrics,
            "drift_score": drift_score,
            "drift_history": drift_history,
            "total_samples": sum(sum(row) for row in hybrid_cm),
            "classes": CLASSES
        }
        await ws.send_text(json.dumps(eval_payload))

        # Send simulator toggle state & cached topology
        await ws.send_text(json.dumps({"topic": "netguard_toggle/simulated", "show": SHOW_SIMULATED}))
        if sim_topology:
            await ws.send_text(json.dumps({"topic": "netguard_50node/topology", **sim_topology}))
        if sim_node_states:
            await ws.send_text(json.dumps({"topic": "netguard_50node/status", "node_states": sim_node_states}))
    except Exception as e:
        print(f"[WS] Error sending initial payload: {e}")

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect": break
            if msg.get("text") == "ping": await ws.send_text("pong")
    except Exception: pass
    finally:
        if ws in connected_ws: connected_ws.remove(ws)
        print(f"[WS] Disconnected. Total: {len(connected_ws)}")

# ── Attacker control ──────────────────────────────────────────────────────────
class ModeCommand(BaseModel):
    mode: str

VALID_MODES = {"NORMAL", "DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK",
               "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"}

@app.post("/evaluation/reset")
async def reset_evaluation():
    global hybrid_cm, baseline_cm, drift_history, drift_score
    hybrid_cm = [[0] * 7 for _ in range(7)]
    baseline_cm = [[0] * 7 for _ in range(7)]
    drift_history.clear()
    drift_score = 0.0
    
    # Broadcast clear to clients
    eval_payload = {
        "topic": "netguard_rohit_77/evaluation",
        "hybrid_cm": hybrid_cm,
        "baseline_cm": baseline_cm,
        "hybrid_metrics": {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0},
        "baseline_metrics": {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0},
        "drift_score": 0.0,
        "drift_history": [],
        "total_samples": 0,
        "classes": CLASSES
    }
    await broadcast(json.dumps(eval_payload))
    print("[Evaluation] Metrics reset successfully.")
    return {"status": "ok"}

@app.post("/attacker/mode")
async def set_mode(cmd: ModeCommand):
    mode = cmd.mode.upper().strip()
    if mode not in VALID_MODES:
        return {"status": "error", "message": f"Unknown mode: {mode}"}
    # Publish to netguard_rohit_77/cmd — Arduino mqttCallback parser expects this exact JSON
    mqtt_client.publish(
        "netguard_rohit_77/cmd",
        json.dumps({"command": "SET_MODE", "mode": mode})
    )
    print(f"[CMD] SET_MODE -> {mode} published to netguard_rohit_77/cmd")
    return {"status": "ok", "mode": mode}

# ── Simulation endpoint (injects synthetic packets for demo/offline mode) ──────
# Realistic inter-arrival times per attack class:
#   NORMAL:           2000–5000 ms  → ~0.3 pkt/s  iat ~3500ms  dup 0    seq+1
#   DOS_FLOOD:        150–350  ms   → ~4 pkt/s    iat ~250ms   dup 0    seq+1
#   REPLAY_ATTACK:    800–1500 ms   → ~1 pkt/s    iat ~1100ms  dup 0.8  seq 0
#   SLOW_RATE_ATTACK: 15000–30000ms → ~0.05 pkt/s iat ~22000ms dup 0    seq+1
#   DATA_POISON:      2000–5000 ms  → mimics NORMAL timing to evade flow AI
#   TOPIC_BOMB:       50–100   ms   → extremely fast, many unique topics
#   EVASION_ATTACK:   150–3500 ms   → mixed fast/slow to fool std_inter_arrival_ms
_SIM_CFG = {
    "NORMAL":           {"iat_lo": 2000,  "iat_hi": 5000,  "n": 12, "dup": 0.0,  "seq_inc": 1},
    "DOS_FLOOD":        {"iat_lo":  150,  "iat_hi":  350,  "n": 80, "dup": 0.0,  "seq_inc": 1},
    "REPLAY_ATTACK":    {"iat_lo":  800,  "iat_hi": 1500,  "n": 20, "dup": 0.82, "seq_inc": 0},
    "SLOW_RATE_ATTACK": {"iat_lo": 15000, "iat_hi":30000, "n":  4, "dup": 0.0,  "seq_inc": 1},
    "DATA_POISON":      {"iat_lo": 2000,  "iat_hi": 5000,  "n": 12, "dup": 0.0,  "seq_inc": 1},
    "TOPIC_BOMB":       {"iat_lo":   50,  "iat_hi":  100,  "n": 80, "dup": 0.0,  "seq_inc": 1},
    "EVASION_ATTACK":   {"iat_lo":  150,  "iat_hi": 3500,  "n": 30, "dup": 0.0,  "seq_inc": 1},
}

import random as _random

@app.post("/simulate")
async def simulate(cmd: ModeCommand):
    """Inject synthetic packets so the ML model predicts the correct attack class."""
    global packet_buffer
    mode = cmd.mode.upper()
    cfg  = _SIM_CFG.get(mode, _SIM_CFG["NORMAL"])

    now = time.time()
    packet_buffer.clear()

    ts = now - (cfg["n"] * (cfg["iat_hi"] / 1000))  # back-date start
    seq = 1000
    for i in range(cfg["n"]):
        iat_ms = _random.uniform(cfg["iat_lo"], cfg["iat_hi"])
        ts    += iat_ms / 1000.0
        # For replay: duplicate ~dup fraction of packets with same seq
        if mode == "REPLAY_ATTACK" and i > 0 and _random.random() < cfg["dup"]:
            pkt_seq = seq   # frozen seq
        else:
            seq    += cfg["seq_inc"]
            pkt_seq = seq
        packet_buffer.append({"ts": ts, "seq": pkt_seq, "mode": mode})

    # Also broadcast a fake attacker update so the node card goes online
    recent   = [p for p in packet_buffer if now - p["ts"] <= 5]
    pkt_rate = round(len(recent) / 5, 1)
    out = json.dumps({
        "topic": "netguard_rohit_77/attacker", "mode": mode,
        "seq": seq, "pkt_rate": pkt_rate, "iat": 0, "manual": True,
    })
    await broadcast(out)
    print(f"[SIM] Injected {cfg['n']} synthetic packets for mode={mode}")
    return {"status": "ok", "mode": mode, "packets_injected": cfg['n']}

@app.post("/attacker/release")
async def release():
    mqtt_client.publish("netguard_rohit_77/cmd", json.dumps({"command": "RELEASE"}))
    return {"status": "ok"}

# ── Simulator Toggle & Attack Control ─────────────────────────────────────────
class TogglePayload(BaseModel):
    show: bool

@app.post("/toggle/simulated")
async def toggle_simulated(payload: TogglePayload):
    global SHOW_SIMULATED
    SHOW_SIMULATED = payload.show
    msg = json.dumps({"topic": "netguard_toggle/simulated", "show": SHOW_SIMULATED})
    await broadcast(msg)
    print(f"[Toggle] Simulated view set to: {SHOW_SIMULATED}")
    return {"status": "ok", "show": SHOW_SIMULATED}

class SimAttackPayload(BaseModel):
    mode: str
    target_node: int | None = None

@app.post("/simulator/attack")
async def simulator_attack(payload: SimAttackPayload):
    """Launch an attack on the 50-node simulator via MQTT command."""
    mode = payload.mode.upper().strip()
    if mode not in VALID_MODES:
        return {"status": "error", "message": f"Unknown mode: {mode}"}
    cmd = {"command": "SET_MODE", "mode": mode}
    if payload.target_node is not None:
        cmd["target_node"] = payload.target_node
    sim_mqtt_client.publish("netguard_50node/cmd", json.dumps(cmd))
    print(f"[SIM-CMD] Attack {mode} sent to simulator (target={payload.target_node})")
    return {"status": "ok", "mode": mode, "target_node": payload.target_node}

@app.post("/simulator/release")
async def simulator_release():
    sim_mqtt_client.publish("netguard_50node/cmd", json.dumps({"command": "RELEASE"}))
    print("[SIM-CMD] Simulator released to NORMAL")
    return {"status": "ok"}

# ── RAG AI Security Analyst Chatbot ──────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str

@app.post("/chat")
async def chat_endpoint(msg: ChatMessage):
    try:
        from rag import query_analyst
        reply = query_analyst(msg.question, last_messages, latest_inference)
        return {"reply": reply}
    except Exception as e:
        print(f"[RAG] Endpoint error: {e}")
        return {"reply": f"### Error processing request\n*Could not query the RAG chatbot: {e}*"}

@app.get("/health")
async def health():
    return {"status": "ok", "ws_clients": len(connected_ws), "model": "loaded" if model else "missing", "buffer_size": len(packet_buffer), "ist_time": datetime.now(IST).strftime("%H:%M:%S IST")}

@app.get("/debug")
async def debug():
    return {"last_20_mqtt_messages": last_messages, "latest_inference": latest_inference}

@app.get("/incident")
async def get_incident():
    """Returns the latest auto-generated incident narrative."""
    return latest_incident

@app.get("/feature-importance")
async def get_feature_importance():
    """Returns global feature importances from the trained model."""
    return {"features": GLOBAL_IMPORTANCE, "model_classes": list(model.classes_) if model else []}
