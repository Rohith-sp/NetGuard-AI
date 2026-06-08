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
    print("Automated Attacker Loop Active. Press [Ctrl+C] to stop.")
    
    # 1. Initial baseline to record clean normal data
    initial_normal_dur = random.randint(30, 50)
    print(f"\n[*] Phase 1: Establishing initial NORMAL baseline data for {initial_normal_dur} seconds...")
    send_mode("NORMAL")
    time.sleep(initial_normal_dur)

    while True:
        # 2. Pick a random attack class dynamically
        active_attack = random.choice(ATTACKS)
        attack_dur = random.randint(20, 35) # Run attack for 20-35 seconds
        
        print(f"\n[*] Phase 2: Launching attack {active_attack} for {attack_dur} seconds...")
        send_mode(active_attack)
        time.sleep(attack_dur)

        # 3. Always transition back to NORMAL baseline to record recovery windows
        recovery_dur = random.randint(30, 50) # Maintain normal for 30-50 seconds
        print(f"\n[*] Phase 3: Transitioning back to NORMAL baseline for {recovery_dur} seconds...")
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
