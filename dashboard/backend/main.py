"""
NetGuard AI — FastAPI Backend
- MQTT → WebSocket bridge
- Live Random Forest inference every 5s on attacker packet window
- SHAP values computed per inference cycle
- IST timesync published to ESP nodes
"""
import asyncio, json, time, math, threading, pickle, os
from collections import deque
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt
from pydantic import BaseModel
import numpy as np

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

# ── Load Model ────────────────────────────────────────────────────────────────
MODEL_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "mqtt_collector", "netguard_model.pkl"
))

try:
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    print(f"[ML] Model loaded from {MODEL_PATH}")
    print(f"[ML] Classes: {model.classes_}")
    EXPLAINER = shap.TreeExplainer(model) if HAS_SHAP else None
except Exception as e:
    model    = None
    EXPLAINER= None
    print(f"[ML] WARNING: Could not load model: {e}")

# Feature columns the model was trained on (must match feature_extractor.py)
FEATURE_COLS = [
    "packet_count", "packet_rate",
    "mean_inter_arrival_ms", "std_inter_arrival_ms",
    "min_inter_arrival_ms",  "max_inter_arrival_ms",
    "duplicate_ratio", "seq_increment_mean", "seq_increment_std",
    "unique_modes",
]

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

# ── Feature extraction from packet buffer ────────────────────────────────────
def safe_mean(v): return sum(v) / len(v) if v else 0.0
def safe_std(v):
    if len(v) < 2: return 0.0
    m = safe_mean(v)
    return math.sqrt(sum((x - m)**2 for x in v) / len(v))

def extract_features(pkts: list, window_sec: float = 5.0) -> dict:
    n = len(pkts)
    if n < 2:
        return None

    timestamps = sorted(p["ts"] for p in pkts)
    iats = [(timestamps[i+1] - timestamps[i]) * 1000 for i in range(len(timestamps)-1)]

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
        "unique_modes":          len(set(p["mode"] for p in pkts)),
    }

# ── ML Inference Loop (every 5 seconds) ───────────────────────────────────────
async def inference_loop():
    global latest_inference
    await asyncio.sleep(6)
    print("[ML] Inference loop started")

    while True:
        await asyncio.sleep(5)
        try:
            now = time.time()
            window = [p for p in packet_buffer if now - p["ts"] <= 10.0]

            if len(window) < 2 or model is None:
                if model is None: print("[ML] Model not loaded — skipping")
                continue

            feats = extract_features(window, window_sec=10.0)
            if feats is None:
                continue

            X = np.array([[feats[c] for c in FEATURE_COLS]])

            # ── Real model inference ──────────────────────────────────────
            pred_label = model.predict(X)[0]
            pred_proba = model.predict_proba(X)[0]
            confidence = round(float(max(pred_proba)) * 100, 1)
            is_attack  = pred_label not in ("NORMAL", "normal")

            # ── SHAP values ───────────────────────────────────────────────
            shap_out = []
            if EXPLAINER and HAS_SHAP:
                try:
                    sv = EXPLAINER.shap_values(X)
                    cls_idx = list(model.classes_).index(pred_label)
                    # Handle (n_classes, n_samples, n_features) or (n_samples, n_features, n_classes)
                    if isinstance(sv, list):
                        vals = np.array(sv[cls_idx][0])
                    elif sv.ndim == 3:
                        vals = sv[0, :, cls_idx]
                    else:
                        vals = sv[0]
                    shap_out = sorted([
                        {"feature": FEATURE_COLS[i], "value": round(float(vals[i]), 4), "raw": round(float(X[0][i]), 3)}
                        for i in range(len(FEATURE_COLS))
                    ], key=lambda x: abs(x["value"]), reverse=True)
                except Exception as e:
                    print(f"[SHAP] Error: {e}")

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

            print(f"[ML] {pred_label} ({confidence}%) | rate={feats['packet_rate']} iat={feats['mean_inter_arrival_ms']}ms dup={feats['duplicate_ratio']}")

        except Exception as e:
            print(f"[ML] Inference error: {e}")

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

        last_messages.append({"topic": topic, "payload": raw[:200], "ts": datetime.now(IST).strftime("%H:%M:%S")})
        if len(last_messages) > 20: last_messages.pop(0)

        if topic == "netguard/timereq":
            publish_timesync(client); return

        if topic == "netguard/attacker":
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

            # Raw packet → frontend (for feed/trust updates)
            recent  = [p for p in packet_buffer if now - p["ts"] <= 5]
            pkt_rate= round(len(recent) / 5, 1)
            out = json.dumps({
                "topic": topic, "mode": data.get("mode", "NORMAL"),
                "seq": data.get("seq", 0), "pkt_rate": pkt_rate,
                "iat": 0, "manual": data.get("manual", False),
            })

        elif topic == "netguard/device1":
            out = json.dumps({"topic": topic, "temp": data.get("temp"), "humidity": data.get("humidity"), "ist_hour": data.get("ist_hour"), "synced": data.get("synced", False)})

        elif topic == "netguard/device2":
            out = json.dumps({"topic": topic, "light": data.get("light"), "ist_hour": data.get("ist_hour"), "synced": data.get("synced", False)})

        else:
            return

        if _loop:
            asyncio.run_coroutine_threadsafe(broadcast(out), _loop)

    except Exception as e:
        print(f"[MQTT] Error: {e}")

async def broadcast(msg: str):
    dead = []
    for ws in connected_ws:
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

@app.on_event("startup")
async def startup():
    global _loop
    _loop = asyncio.get_running_loop()

    def run_mqtt():
        mqtt_client.connect("broker.hivemq.com", 1883, 60)
        mqtt_client.loop_forever()

    threading.Thread(target=run_mqtt, daemon=True).start()
    asyncio.create_task(timesync_loop())
    asyncio.create_task(inference_loop())
    print(f"[Startup] IST={ist_hour():.2f} | Model={'loaded' if model else 'MISSING'}")

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

@app.post("/attacker/mode")
async def set_mode(cmd: ModeCommand):
    mqtt_client.publish("netguard/cmd", json.dumps({"command": "SET_MODE", "mode": cmd.mode}))
    print(f"[CMD] SET_MODE → {cmd.mode}")
    return {"status": "ok", "mode": cmd.mode}

@app.post("/attacker/release")
async def release():
    mqtt_client.publish("netguard/cmd", json.dumps({"command": "RELEASE"}))
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok", "ws_clients": len(connected_ws), "model": "loaded" if model else "missing", "buffer_size": len(packet_buffer), "ist_time": datetime.now(IST).strftime("%H:%M:%S IST")}

@app.get("/debug")
async def debug():
    return {"last_20_mqtt_messages": last_messages, "latest_inference": latest_inference}
