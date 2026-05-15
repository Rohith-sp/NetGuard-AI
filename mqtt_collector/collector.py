"""
NetGuard AI — Phase 2 MQTT Collector
=====================================
Subscribes to all three ESP32 node topics, logs raw telemetry, and writes
a structured CSV dataset ready for ML feature extraction.

Topics consumed:
  netguard/device1   → DHT Node  (temp, humidity)
  netguard/device2   → LDR Node  (light)
  netguard/attacker  → Attacker  (mode, seq)

Run:
  pip install paho-mqtt
  python collector.py
"""

import json
import csv
import os
import time
import random
import threading
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# ── Config ────────────────────────────────────────────────────────────────────
BROKER       = "broker.hivemq.com"
PORT         = 1883
TOPICS       = [
    ("netguard/device1",  0),
    ("netguard/device2",  0),
    ("netguard/attacker", 0),
]
OUTPUT_DIR   = os.path.join(os.path.dirname(__file__), "dataset")
RAW_LOG      = os.path.join(OUTPUT_DIR, "raw_telemetry.log")
CSV_FILE     = os.path.join(OUTPUT_DIR, "netguard_dataset.csv")

# CSV column schema
CSV_COLUMNS = [
    "timestamp_utc",     # ISO-8601 timestamp
    "topic",             # MQTT topic
    "device",            # device identifier from payload
    "mode",              # attacker mode / "LEGITIMATE" for sensors
    "seq",               # sequence number (attacker only, else -1)
    "temp",              # temperature   (DHT only, else -1)
    "humidity",          # humidity      (DHT only, else -1)
    "light",             # light value   (LDR only, else -1)
    "inter_arrival_ms",  # ms since last packet from SAME device
    "label",             # ground-truth: NORMAL / DOS_FLOOD / REPLAY_ATTACK /
                         #               SLOW_RATE_ATTACK / LEGITIMATE
]

# ── State ─────────────────────────────────────────────────────────────────────
last_seen    = {}   # device → last arrival timestamp (float, epoch seconds)
packet_count = 0
lock         = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────
def ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=CSV_COLUMNS).writeheader()


def label_for(topic: str, payload: dict) -> str:
    """Assign ground-truth label from the payload itself."""
    if topic == "netguard/attacker":
        return payload.get("mode", "UNKNOWN")
    return "LEGITIMATE"


def inter_arrival(device: str, now: float) -> int:
    """Return ms since last packet from this device, or -1 on first seen."""
    with lock:
        prev = last_seen.get(device)
        last_seen[device] = now
    if prev is None:
        return -1
    return int((now - prev) * 1000)


def write_raw_log(raw: str, timestamp: str):
    with open(RAW_LOG, "a") as f:
        f.write(f"[{timestamp}] {raw}\n")


def write_csv_row(row: dict):
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(row)


def simulate_packet_loss() -> bool:
    """
    Randomly drop ~3 % of packets to model real-world UDP / broker unreliability.
    Returns True if the packet should be DROPPED (not logged).
    """
    return random.random() < 0.03


# ── MQTT callbacks ────────────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[+] Connected to {BROKER}")
        for topic, qos in TOPICS:
            client.subscribe(topic, qos)
            print(f"    Subscribed → {topic}")
    else:
        print(f"[-] Connection failed (rc={rc}). Retrying...")


def on_message(client, userdata, msg):
    global packet_count

    now       = time.time()
    ts_str    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    raw_str   = msg.payload.decode("utf-8", errors="replace")
    topic     = msg.topic

    # Write raw log unconditionally (even dropped packets go here for debugging)
    write_raw_log(f"{topic}  {raw_str}", ts_str)

    # Simulate packet loss
    if simulate_packet_loss():
        print(f"  [DROP] {topic}  {raw_str}")
        return

    try:
        payload = json.loads(raw_str)
    except json.JSONDecodeError:
        print(f"  [WARN] Non-JSON payload on {topic}: {raw_str}")
        return

    device  = payload.get("device", topic.split("/")[-1])
    mode    = payload.get("mode", "LEGITIMATE")
    seq     = payload.get("seq",  -1)
    temp    = payload.get("temp", -1)
    hum     = payload.get("humidity", -1)
    light   = payload.get("light", -1)

    ia_ms   = inter_arrival(device, now)
    lbl     = label_for(topic, payload)

    row = {
        "timestamp_utc":  ts_str,
        "topic":          topic,
        "device":         device,
        "mode":           mode,
        "seq":            seq,
        "temp":           temp,
        "humidity":       hum,
        "light":          light,
        "inter_arrival_ms": ia_ms,
        "label":          lbl,
    }

    write_csv_row(row)

    with lock:
        packet_count += 1
        count_snapshot = packet_count

    print(
        f"  [{count_snapshot:>5}] {ts_str}  {topic:<26}"
        f"  label={lbl:<18}  ia={ia_ms:>6}ms"
    )


def on_disconnect(client, userdata, rc):
    print(f"[!] Disconnected (rc={rc}). Will auto-reconnect...")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ensure_dirs()
    print("=" * 70)
    print("  NetGuard AI — Phase 2 MQTT Collector")
    print(f"  Output: {CSV_FILE}")
    print("=" * 70)

    client_id = f"NetGuard-Collector-{random.randint(1000, 9999)}"
    mqttc = mqtt.Client(client_id=client_id)
    mqttc.on_connect    = on_connect
    mqttc.on_message    = on_message
    mqttc.on_disconnect = on_disconnect

    mqttc.reconnect_delay_set(min_delay=1, max_delay=30)
    mqttc.connect(BROKER, PORT, keepalive=60)

    print(f"  Connecting as {client_id} ...")
    print("  Press Ctrl+C to stop.\n")

    try:
        mqttc.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[+] Stopped. Total packets logged: {packet_count}")
        print(f"    Dataset → {CSV_FILE}")
        mqttc.disconnect()


if __name__ == "__main__":
    main()
