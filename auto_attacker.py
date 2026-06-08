import paho.mqtt.client as mqtt
import time
import random
import json
import sys

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "netguard/cmd"

# List of 6 advanced attack modes
ATTACKS = ["DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"]

def get_random_attack():
    # Rare attacks (Slow Rate, Poison, Replay, Evasion) get 85% total chance.
    # High-packet flood attacks (DoS, Topic Bomb) get 15% total chance to avoid bloating the logs.
    choices = ["SLOW_RATE_ATTACK", "DATA_POISON", "REPLAY_ATTACK", "EVASION_ATTACK", "DOS_FLOOD", "TOPIC_BOMB"]
    weights = [0.25, 0.25, 0.20, 0.15, 0.10, 0.05]
    return random.choices(choices, weights=weights, k=1)[0]

def on_connect(client, userdata, flags, rc, *args):
    if rc == 0:
        print("Connected to MQTT Broker successfully!")
        print(f"Publishing control commands to topic: {TOPIC}")
        print("=" * 60)
    else:
        print(f"MQTT Connection failed with code {rc}")
        sys.exit(1)

# Initialize MQTT Client with backward compatibility for Paho MQTT version 1 & 2
try:
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    client = mqtt.Client()

client.on_connect = on_connect

print(f"Connecting to public MQTT Broker at {BROKER}:{PORT}...")
try:
    client.connect(BROKER, PORT, 60)
except Exception as e:
    print(f"Failed to connect to broker: {e}")
    sys.exit(1)

client.loop_start()

def send_mode(mode):
    payload = json.dumps({"command": "SET_MODE", "mode": mode})
    client.publish(TOPIC, payload, qos=1)
    print(f"[{time.strftime('%H:%M:%S')}] >>> COMMAND PUBLISHED: {mode}")

try:
    print("Automated Sneaky Attacker Loop Active. Press [Ctrl+C] to stop.")
    
    # 1. Initial baseline to record clean normal data (Stealth startup)
    initial_normal_dur = random.randint(60, 100) # 1 to 1.7 minutes
    print(f"\n[*] [INIT] Establishing initial NORMAL baseline traffic for {initial_normal_dur} seconds...")
    send_mode("NORMAL")
    time.sleep(initial_normal_dur)

    while True:
        # 2. Attack Phase (Weighted selection favoring rare classes)
        active_attack = get_random_attack()
        
        # Adjust duration ranges to match packet output rates
        if active_attack == "SLOW_RATE_ATTACK":
            attack_dur = random.randint(60, 95)  # Extended duration for sparse packet logs
            intensity = "EXTENDED LOW-RATE"
        elif active_attack == "DATA_POISON":
            attack_dur = random.randint(45, 75)  # Medium-long duration for DHT spoofing
            intensity = "EXTENDED POISON"
        elif active_attack in ["REPLAY_ATTACK", "EVASION_ATTACK"]:
            attack_dur = random.randint(25, 45)  # Standard capture
            intensity = "STANDARD TIMING"
        else: # DOS_FLOOD or TOPIC_BOMB
            attack_dur = random.randint(8, 12)   # Short bursts to prevent flood congestion
            intensity = "SHORT HIGH-RATE BURST"
            
        print(f"\n[!] [ATTACK] Launching {intensity} {active_attack} for {attack_dur} seconds...")
        send_mode(active_attack)
        time.sleep(attack_dur)

        # 3. Transition back to NORMAL recovery (unpredictably spaced)
        recovery_dur = random.randint(80, 150) 
        
        print(f"\n[*] [NORMAL] Resetting to dominant NORMAL baseline for {recovery_dur} seconds...")
        send_mode("NORMAL")
        time.sleep(recovery_dur)

except KeyboardInterrupt:
    print("\n\n[!] Execution halted by user.")
    print("[*] Restoring physical attacker node to NORMAL mode before exit...")
    send_mode("NORMAL")
    time.sleep(2)
    
finally:
    client.loop_stop()
    client.disconnect()
    print("[+] MQTT connection closed. Automation finished.")
