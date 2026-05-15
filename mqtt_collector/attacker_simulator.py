"""
NetGuard AI — Mid-Speed Calibrated Attacker
=========================================
Faster intervals for practical dataset generation (~20-30 mins for 3k pkts).
"""

import json
import random
import time
import threading
import paho.mqtt.client as mqtt

# ── Config ──
BROKER = "broker.hivemq.com"
TOPIC  = "netguard/attacker"
DEVICE = "esp32_3"

# ── Mode Timing Logic (MID-SPEED) ──
# NORMAL: ~5s
# DOS: 0.15-0.3s
# REPLAY: 0.8-1.5s
# SLOW: 15-30s

MODE_DURATIONS = {
    "NORMAL":           (60, 120), # Stay hidden
    "DOS_FLOOD":        (15, 30),  # Hard bursts
    "REPLAY_ATTACK":    (20, 40),  # Scripted repetition
    "SLOW_RATE_ATTACK": (60, 100), # Stealthy window
}

# ── State ──
seq_number = 0
connected = False
state_lock = threading.Lock()

def jitter(base, percent=0.2):
    return base + random.uniform(-(base*percent), (base*percent))

def on_connect(client, userdata, flags, rc):
    global connected
    if rc == 0: connected = True

def build_payload(mode: str, seq: int):
    return json.dumps({"device": DEVICE, "mode": mode, "seq": seq}, separators=(",", ":"))

# ── Runners ──
def run_normal(client, duration):
    global seq_number
    end = time.time() + duration
    while time.time() < end:
        with state_lock:
            seq_number += 1
            s = seq_number
        client.publish(TOPIC, build_payload("NORMAL", s))
        print(f"  [NORMAL] Sent Seq {s}")
        time.sleep(jitter(5.0, 0.2)) # 4s to 6s

def run_dos_flood(client, duration):
    global seq_number
    end = time.time() + duration
    while time.time() < end:
        with state_lock:
            seq_number += 1
            s = seq_number
        client.publish(TOPIC, build_payload("DOS_FLOOD", s))
        print(f"  [FLOOD]  Sent Seq {s}")
        time.sleep(random.uniform(0.15, 0.35))

def run_replay(client, duration):
    global seq_number
    with state_lock: s = seq_number
    payload = build_payload("REPLAY_ATTACK", s)
    end = time.time() + duration
    while time.time() < end:
        client.publish(TOPIC, payload)
        print(f"  [REPLAY] Sent Seq {s} (FROZEN)")
        time.sleep(random.uniform(0.8, 1.5))

def run_slow_rate(client, duration):
    global seq_number
    end = time.time() + duration
    while time.time() < end:
        with state_lock:
            seq_number += 1
            s = seq_number
        client.publish(TOPIC, build_payload("SLOW_RATE_ATTACK", s))
        print(f"  [SLOW]   Sent Seq {s} (Stealth)")
        gap = random.uniform(15, 30) # 15-30s is "slow" compared to 5s
        wake = time.time() + gap
        while time.time() < wake and time.time() < end: time.sleep(1)

RUNNERS = {"NORMAL": run_normal, "DOS_FLOOD": run_dos_flood, "REPLAY_ATTACK": run_replay, "SLOW_RATE_ATTACK": run_slow_rate}

def main():
    mqttc = mqtt.Client()
    mqttc.on_connect = on_connect
    mqttc.connect_async(BROKER, 1883, 60)
    mqttc.loop_start()

    print("=" * 60)
    print("  NetGuard AI — MID-SPEED ATTACKER")
    print("=" * 60)

    curr = "NORMAL"
    try:
        while True:
            dur = random.uniform(*MODE_DURATIONS[curr])
            print(f"\n[!] MODE CHANGE -> {curr} for {int(dur)}s")
            RUNNERS[curr](mqttc, dur)
            curr = random.choices(list(RUNNERS.keys()), weights=[30, 25, 25, 20])[0]
    except KeyboardInterrupt:
        mqttc.loop_stop()

if __name__ == "__main__":
    main()
