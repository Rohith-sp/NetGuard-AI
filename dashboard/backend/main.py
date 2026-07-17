"""
NetGuard AI — FastAPI Backend
- MQTT → WebSocket bridge
- Live Random Forest inference every 5s on attacker packet window
- SHAP values computed per inference cycle
- IST timesync published to ESP nodes
"""
import asyncio, json, time, math, threading, pickle, os, random, warnings
warnings.filterwarnings("ignore", category=UserWarning)
from collections import deque
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
import paho.mqtt.client as mqtt
from pydantic import BaseModel
import numpy as np
import joblib
from statistical_analyzer import StatisticalProfiler

# ── API Key Authentication ────────────────────────────────────────────────────
API_KEY = os.environ.get("NETGUARD_API_KEY", "changeme-dev-key")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key


# ── MQTT Configuration ─────────────────────────────────────────────────────────
MQTT_BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
MQTT_USE_TLS = os.environ.get("MQTT_USE_TLS", "false").lower() == "true"
MQTT_CA_CERTS = os.environ.get("MQTT_CA_CERTS")

profiler = StatisticalProfiler()


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
]

# ── Load Model ────────────────────────────────────────────────────────────────
MODEL_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "ml_model", "netguard_model.pkl"
))

try:
    model = joblib.load(MODEL_PATH)
    print(f"[ML] Model loaded from {MODEL_PATH}")
    print(f"[ML] Classes: {model.classes_}")
    EXPLAINER = shap.TreeExplainer(model) if HAS_SHAP else None
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

latest_gas_ppm: float | None = None


# ── Feature extraction from packet buffer ────────────────────────────────────
def safe_mean(v): return sum(v) / len(v) if v else 0.0
def safe_std(v):
    if len(v) < 2: return 0.0
    m = safe_mean(v)
    return math.sqrt(sum((x - m)**2 for x in v) / len(v))

def extract_features(pkts: list, window_sec: float = 5.0) -> dict:
    n = len(pkts)
    if n < 1:
        return None

    timestamps = sorted(p["ts"] for p in pkts)
    if len(timestamps) > 1:
        iats = [(timestamps[i+1] - timestamps[i]) * 1000 for i in range(len(timestamps)-1)]
    else:
        # Single packet in the window — hallmark of Slow Rate Attack
        # Treat the whole window duration as one giant IAT (matches training augmentation)
        iats = [window_sec * 1000]

    seqs = [p["seq"] for p in pkts if p["seq"] >= 0]
    seq_incs = [seqs[i+1] - seqs[i] for i in range(len(seqs)-1)]

    seen, dups = set(), 0
    for s in seqs:
        if s in seen: dups += 1
        seen.add(s)
    dup_ratio = dups / n

    return {
        "packet_count":          n,
        "packet_rate":           round(n / window_sec, 4),
        "mean_inter_arrival_ms": round(safe_mean(iats), 2),
        "std_inter_arrival_ms":  round(safe_std(iats), 2),
        "min_inter_arrival_ms":  round(min(iats), 2) if iats else 0,
        "max_inter_arrival_ms":  round(max(iats), 2) if iats else 0,
        "duplicate_ratio":       round(dup_ratio, 4),
        "seq_increment_mean":    round(safe_mean(seq_incs), 4),
        "seq_increment_std":     round(safe_std(seq_incs), 4),
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

            # ── 1. Hybrid Pipeline: Dynamic Statistical Profiler ───────
            rule_triggered = False
            
            # Rule 1: Data Poisoning (Live Z-Score Tracker on Payload)
            if any(p.get("mode") == "DATA_POISON" for p in window):
                pred_label = "DATA_POISON"
                confidence = 100.0
                rule_triggered = True

            # Rule 2: Slow Rate Attack (Global Packet-State Math)
            elif profiler.detect_slow_rate() and feats["packet_rate"] <= 0.4:
                pred_label = "SLOW_RATE_ATTACK"
                confidence = 100.0
                rule_triggered = True

            if rule_triggered:
                is_attack = True
                # Mock SHAP to show Rule Engine dominance in the UI
                shap_out = [{"feature": "Rule_Engine_Override", "value": 1.0, "raw": 1.0}]
            else:
                # ── 2. Hybrid Pipeline: ML Stage (Offloaded to thread) ──
                def run_ml(f):
                    X = np.array([[f[c] for c in FEATURE_COLS]])
                    p_label = model.predict(X)[0]
                    p_proba = model.predict_proba(X)[0]
                    conf = round(float(max(p_proba)) * 100, 1)
                    
                    s_out = []
                    if EXPLAINER and HAS_SHAP:
                        try:
                            sv = EXPLAINER.shap_values(X)
                            cls_idx = list(model.classes_).index(p_label)
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

                pred_label, confidence, shap_out = await asyncio.to_thread(run_ml, feats)
                
                normal_classes = {c for c in model.classes_ if c.upper() == "NORMAL"}
                is_attack  = pred_label not in normal_classes

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
            }

            # Push inference result to all WebSocket clients
            out = json.dumps({"topic": "netguard/inference", **latest_inference})
            if _loop:
                asyncio.run_coroutine_threadsafe(broadcast(out), _loop)

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
                    mqtt_client.publish("netguard/alerts", alert_payload)
                    print(f"[ALERT] Published to netguard/alerts -> {pred_label} ({confidence}%)")

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
                    mqtt_client.publish("netguard/alerts", alert_payload)
                    print(f"[ALERT] Published to netguard/alerts -> NORMAL / ALL_CLEAR")

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

        from rag import call_groq_llm
        narrative = await loop.run_in_executor(None, lambda: call_groq_llm("You are a terse, expert SOC incident writer.", prompt))
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
        out = json.dumps({"topic": "netguard/incident", **latest_incident})
        await broadcast(out)
        print(f"[INCIDENT] Narrative generated and broadcast for {label}")
    except Exception as e:
        print(f"[INCIDENT] Error generating narrative: {e}")

# ── IST Helper ────────────────────────────────────────────────────────────────

def ist_hour() -> float:
    n = datetime.now(IST)
    return n.hour + n.minute / 60.0 + n.second / 3600.0

# ── MQTT ──────────────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc, p=None):
    print(f"[MQTT] Connected rc={rc}")
    client.subscribe("netguard/#")
    publish_timesync(client)

def publish_timesync(client):
    h = ist_hour()
    client.publish("netguard/timesync", json.dumps({"type": "timesync", "ist_hour": round(h, 4)}))
    print(f"[TimeSync] {h:.2f}")

def on_message(client, userdata, msg):
    global _loop
    try:
        topic = msg.topic
        raw   = msg.payload.decode()
        data  = json.loads(raw)
        now   = time.time()

        # Seamless digital LDR conversion: Map 0 (Bright) and 1 (Dark) to realistic LUX
        if topic == "netguard/device2" and "light" in data:
            val = data["light"]
            if val == 0:
                data["light"] = 1350 + random.randint(-40, 40) # Bright daytime ambient
                raw = json.dumps(data)
            elif val == 1:
                data["light"] = 18 + random.randint(-5, 10)    # Nighttime / covered
                raw = json.dumps(data)

        last_messages.append({"topic": topic, "payload": raw[:200], "ts": datetime.now(IST).strftime("%H:%M:%S")})
        if len(last_messages) > 20: last_messages.pop(0)

        if topic == "netguard/timereq":
            publish_timesync(client); return

        if topic == "netguard/attacker" or data.get("mode") in ["DATA_POISON", "TOPIC_BOMB"]:
            profiler.track_packet(now)
            # Buffer packet for ML window
            packet_buffer.append({
                "ts":   now,
                "seq":  int(data.get("seq", -1)),
                "mode": data.get("mode", "NORMAL"),
            })
            # Trim to last 60s
            cutoff = now - 60
            while packet_buffer and packet_buffer[0]["ts"] < cutoff:
                packet_buffer.popleft()

        if topic == "netguard/attacker":
            # Raw packet → frontend (for feed/trust updates)
            recent  = [p for p in packet_buffer if now - p["ts"] <= 5]
            pkt_rate= round(len(recent) / 5, 1)
            gas_ppm = data.get("gas_ppm")
            if gas_ppm is not None:
                global latest_gas_ppm
                latest_gas_ppm = gas_ppm
            
            out = json.dumps({
                "topic": topic, "mode": data.get("mode", "NORMAL"),
                "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                "iat": 0, "manual": data.get("manual", False),
                "gas_ppm": gas_ppm,
            })
            if gas_ppm is not None:
                profiler.track_payload("esp32_3", "gas_ppm", gas_ppm)

        elif topic == "netguard/device1":
            profiler.track_packet(now)
            hum_val = data.get("humidity") if data.get("humidity") is not None else data.get("hum")
            temp_val = data.get("temp")
            gas_ppm = data.get("gas_ppm")
            out = json.dumps({"topic": topic, "temp": temp_val, "humidity": hum_val, "gas_ppm": gas_ppm, "ist_hour": data.get("ist_hour"), "synced": data.get("synced", False)})
            
            # Mathematically track payload for Data Poisoning
            is_poison_temp = profiler.track_payload("esp32_1", "temp", temp_val)
            is_poison_hum = profiler.track_payload("esp32_1", "humidity", hum_val)
            is_poison_gas = profiler.track_payload("esp32_1", "gas_ppm", gas_ppm)
            is_poison = is_poison_temp or is_poison_hum or is_poison_gas
            
            # If Z-Score indicates a spoofed payload, simulate an attacker feed update
            if is_poison or data.get("mode") == "DATA_POISON":
                # Inject a poisoned packet into the flow buffer so the inference loop sees it
                packet_buffer.append({"ts": now, "seq": int(data.get("seq", -1)), "mode": "DATA_POISON"})
                recent  = [p for p in packet_buffer if now - p["ts"] <= 5]
                pkt_rate= round(len(recent) / 5, 1)
                attacker_out = json.dumps({
                    "topic": "netguard/attacker", "mode": "DATA_POISON",
                    "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                    "iat": 0, "manual": data.get("manual", False),
                })
                if _loop:
                    asyncio.run_coroutine_threadsafe(broadcast(attacker_out), _loop)

        elif topic == "netguard/device2":
            profiler.track_packet(now)
            out = json.dumps({"topic": topic, "light": data.get("light"), "ist_hour": data.get("ist_hour"), "synced": data.get("synced", False)})

        elif topic.startswith("netguard/junk_") or data.get("mode") == "TOPIC_BOMB":
            profiler.track_packet(now)
            recent  = [p for p in packet_buffer if now - p["ts"] <= 5]
            pkt_rate= round(len(recent) / 5, 1)
            out = json.dumps({
                "topic": "netguard/attacker", "mode": "TOPIC_BOMB",
                "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                "iat": 0, "manual": data.get("manual", False),
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

async def gas_explanation_loop():
    from rag import call_groq_llm
    await asyncio.sleep(10) # Initial delay
    while True:
        try:
            if latest_gas_ppm is not None:
                prompt = f"The current MQ135 gas sensor reading is {latest_gas_ppm} PPM. Provide a single, very short 4-8 word sentence explaining if this air quality is good, moderate, or hazardous. Be extremely concise. No markdown."
                explanation = await asyncio.to_thread(call_groq_llm, "You are a terse air quality expert.", prompt)
                
                if explanation:
                    out = json.dumps({
                        "topic": "netguard/gas_explanation",
                        "explanation": explanation.strip()
                    })
                    await broadcast(out)
        except Exception as e:
            print(f"[Gas Explanation Loop] Error: {e}")
        await asyncio.sleep(120)

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "netguard-backend")

# Configure MQTT authentication if provided
if MQTT_USERNAME and MQTT_PASSWORD:
    mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Configure TLS if enabled
if MQTT_USE_TLS:
    if MQTT_CA_CERTS:
        mqtt_client.tls_set(ca_certs=MQTT_CA_CERTS)
    else:
        mqtt_client.tls_set()
    mqtt_client.tls_insecure_set(False)

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_running_loop()

    def run_mqtt():
        while True:
            try:
                mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
                mqtt_client.loop_forever()
            except Exception as e:
                print(f"[MQTT] Connection failed: {e}. Retrying in 5s...")
                time.sleep(5)

    threading.Thread(target=run_mqtt, daemon=True).start()
    asyncio.create_task(timesync_loop())
    asyncio.create_task(gas_explanation_loop())
    asyncio.create_task(inference_loop())
    print(f"[Startup] IST={ist_hour():.2f} | Model={'loaded' if model else 'MISSING'} | MQTT={'TLS' if MQTT_USE_TLS else 'plain'} {'auth' if MQTT_USERNAME else 'no-auth'}")

# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    connected_ws.append(ws)
    print(f"[WS] Connected. Total: {len(connected_ws)}")
    try:
        h = ist_hour()
        await ws.send_text(json.dumps({"topic": "netguard/system", "ist_hour": round(h, 2), "ist_time": datetime.now(IST).strftime("%H:%M:%S")}))
        # Send latest inference immediately
        if latest_inference["label"] != "AWAITING":
            await ws.send_text(json.dumps({"topic": "netguard/inference", **latest_inference}))
    except Exception: pass

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

@app.post("/attacker/mode", dependencies=[Depends(verify_api_key)])
async def set_mode(cmd: ModeCommand):
    mode = cmd.mode.upper().strip()
    if mode not in VALID_MODES:
        return {"status": "error", "message": f"Unknown mode: {mode}"}
    # Publish to netguard/cmd — Arduino mqttCallback parser expects this exact JSON
    mqtt_client.publish(
        "netguard/cmd",
        json.dumps({"command": "SET_MODE", "mode": mode})
    )
    print(f"[CMD] SET_MODE -> {mode} published to netguard/cmd")
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

@app.post("/simulate", dependencies=[Depends(verify_api_key)])
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
        "topic": "netguard/attacker", "mode": mode,
        "seq": seq, "pkt_rate": pkt_rate, "iat": 0, "manual": True,
    })
    await broadcast(out)
    print(f"[SIM] Injected {cfg['n']} synthetic packets for mode={mode}")
    return {"status": "ok", "mode": mode, "packets_injected": cfg['n']}

@app.post("/attacker/release", dependencies=[Depends(verify_api_key)])
async def release():
    mqtt_client.publish("netguard/cmd", json.dumps({"command": "RELEASE"}))
    return {"status": "ok"}

# ── RAG AI Security Analyst Chatbot ──────────────────────────────────────────
class ChatMessage(BaseModel):
    question: str

@app.post("/chat", dependencies=[Depends(verify_api_key)])
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
