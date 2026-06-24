"""
NetGuard AI — Full Node Simulator (replaces all 3 Wokwi simulations)
Publishes realistic data to HiveMQ on the same topics Wokwi would use.
- ESP32_1 (DHT22): Bangalore temp/humidity based on real IST system time
- ESP32_2 (LDR):   Bangalore light levels based on real IST sunrise/sunset
- ESP32_3 (Attacker): Auto-switching attack modes, responds to netguard/cmd
"""
import paho.mqtt.client as mqtt
import json, time, math, random, threading
from datetime import datetime, timezone, timedelta

BROKER = "broker.hivemq.com"
PORT   = 1883
IST    = timezone(timedelta(hours=5, minutes=30))

# ── Helpers ────────────────────────────────────────────────────────────────────
def ist_hour():
    n = datetime.now(IST)
    return n.hour + n.minute / 60.0 + n.second / 3600.0

def bangalore_temp(h):
    base = 26.5 + 6.5 * math.sin((h - 5.5) * math.pi / 12.0)
    return round(max(18.0, min(38.0, base + random.uniform(-0.4, 0.4))), 1)

def bangalore_hum(h):
    base = 57.0 - 19.0 * max(0, math.sin((h - 5.5) * math.pi / 12.0))
    if h < 5.5 or h > 17.5: base += 8.0
    return round(max(25.0, min(92.0, base + random.uniform(-0.3, 0.3))), 1)

def bangalore_light(h):
    if h < 6.17 or h > 18.42: return random.randint(0, 25)
    factor = math.sin((h - 6.17) * math.pi / 12.25)
    lux = int(max(0, factor) * 3800) + random.randint(-60, 60)
    return max(0, lux)

# ── Attacker state ─────────────────────────────────────────────────────────────
# Starts in NORMAL — only changes when dashboard sends SET_MODE command
atk_mode    = "NORMAL"
atk_seq     = 0
manual_lock = False   # True when operator has triggered an attack mode

def get_interval():
    return {"NORMAL": (2.0, 5.0), "DOS_FLOOD": (0.15, 0.35),
            "REPLAY_ATTACK": (0.8, 1.5), "SLOW_RATE_ATTACK": (15.0, 30.0)}.get(atk_mode, (2.0, 5.0))

# ── MQTT setup ─────────────────────────────────────────────────────────────────
def make_client(cid):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, cid)
    return c

# Shared client for commands
cmd_client = make_client("ng-sim-cmd")

def on_cmd_message(c, u, msg):
    global atk_mode, manual_lock
    try:
        d = json.loads(msg.payload.decode())
        if d.get("command") == "SET_MODE":
            atk_mode    = d.get("mode", "NORMAL")
            manual_lock = atk_mode != "NORMAL"
            print(f"[CMD] Mode set → {atk_mode}")
        elif d.get("command") == "RELEASE":
            atk_mode    = "NORMAL"
            manual_lock = False
            print("[CMD] Released → NORMAL")
    except: pass

def on_cmd_connect(c, u, f, rc, p=None):
    c.subscribe("netguard/cmd")
    c.subscribe("netguard/timesync")
    print("[CMD] Subscribed to netguard/cmd")

cmd_client.on_connect = on_cmd_connect
cmd_client.on_message = on_cmd_message

# ── Node threads ────────────────────────────────────────────────────────────────
def run_dht():
    c = make_client("ng-sim-dht22")
    c.connect(BROKER, PORT, 60)
    c.loop_start()
    print("[DHT] Running...")
    while True:
        h    = ist_hour()
        temp = bangalore_temp(h)
        hum  = bangalore_hum(h)
        payload = json.dumps({"device": "esp32_1", "temp": temp, "humidity": hum, "ist_hour": round(h, 2), "synced": True})
        c.publish("netguard/device1", payload)
        print(f"[DHT] {payload}")
        time.sleep(random.uniform(2.0, 5.0))

def run_ldr():
    c = make_client("ng-sim-ldr")
    c.connect(BROKER, PORT, 60)
    c.loop_start()
    print("[LDR] Running...")
    while True:
        h    = ist_hour()
        lux  = bangalore_light(h)
        payload = json.dumps({"device": "esp32_2", "light": lux, "ist_hour": round(h, 2), "synced": True})
        c.publish("netguard/device2", payload)
        print(f"[LDR] {payload}")
        time.sleep(random.uniform(2.0, 5.0))

def run_attacker():
    global atk_mode, atk_seq
    c = make_client("ng-sim-attacker")
    c.connect(BROKER, PORT, 60)
    c.loop_start()
    print("[ATK] Running — waiting for trigger from dashboard...")
    replay_payload = None

    while True:
        # Sequence number — frozen during replay attack
        if atk_mode != "REPLAY_ATTACK":
            atk_seq += 1
            replay_payload = None  # reset replay buffer when mode changes

        if atk_mode == "REPLAY_ATTACK":
            if replay_payload is None:
                payload_dict = {
                    "device": "esp32_3", "mode": atk_mode,
                    "seq": atk_seq, "manual": manual_lock,
                    "gas_ppm": round(random.uniform(40.0, 150.0), 2)
                }
                replay_payload = json.dumps(payload_dict)
            payload = replay_payload
            topic = "netguard/attacker"
        elif atk_mode == "DATA_POISON":
            fakeTemp = round(random.uniform(-500, 1500), 2)
            fakeHum = round(random.uniform(-200, 300), 2)
            fakePPM = round(random.uniform(5000, 15000), 2)
            payload = json.dumps({
                "device": "esp32_1", "temp": fakeTemp, "humidity": fakeHum, 
                "gas_ppm": fakePPM, "poisoned": True, "mode": atk_mode,
                "seq": atk_seq, "manual": manual_lock
            })
            topic = "netguard/device1"
        elif atk_mode == "TOPIC_BOMB":
            payload = json.dumps({"device": "esp32_3", "mode": atk_mode, "garbage": True, "seq": atk_seq, "manual": manual_lock})
            topic = f"netguard/junk_{random.randint(0, 1000)}"
        else:
            payload = json.dumps({
                "device": "esp32_3", "mode": atk_mode,
                "seq": atk_seq, "manual": manual_lock,
                "gas_ppm": round(random.uniform(40.0, 150.0), 2)
            })
            topic = "netguard/attacker"

        c.publish(topic, payload)
        print(f"[ATK] {topic} -> {payload}")

        lo, hi = get_interval()
        time.sleep(random.uniform(lo, hi))

# ── Main ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print(" NetGuard Node Simulator — All 3 ESP32 nodes")
    print(f" IST Time: {datetime.now(IST).strftime('%H:%M:%S')}")
    print(f" Bangalore Light: {bangalore_light(ist_hour())} LUX")
    print(f" Bangalore Temp:  {bangalore_temp(ist_hour())} °C")
    print("=" * 55)

    # Connect command listener
    cmd_client.connect(BROKER, PORT, 60)
    cmd_client.loop_start()

    # Start each node in its own thread
    for fn in [run_dht, run_ldr, run_attacker]:
        t = threading.Thread(target=fn, daemon=True)
        t.start()
        time.sleep(1)  # stagger connections

    print("\n[SIM] All nodes running. Press Ctrl+C to stop.\n")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SIM] Stopped.")
