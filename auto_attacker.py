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
    print("Automated Sneaky Attacker Loop Active. Press [Ctrl+C] to stop.")
    
    # 1. Initial baseline to record clean normal data (Long startup baseline)
    initial_normal_dur = random.randint(150, 240) # 2.5 to 4 minutes
    print(f"\n[*] [INIT] Establishing initial NORMAL baseline traffic for {initial_normal_dur} seconds...")
    send_mode("NORMAL")
    time.sleep(initial_normal_dur)

    while True:
        # 2. Attack Phase (Unpredictable, short-lived bursts to prevent packet overloading)
        active_attack = random.choice(ATTACKS)
        
        # Decide attack duration (15-25s is ideal to populate sliding windows without drowning normal data)
        roll = random.random()
        if roll < 0.30:
            attack_dur = random.randint(10, 15)  # Quick spike
            intensity = "SHORT BURST"
        else:
            attack_dur = random.randint(15, 25)  # Standard window capture
            intensity = "STANDARD"
            
        print(f"\n[!] [ATTACK] Launching {intensity} {active_attack} for {attack_dur} seconds...")
        send_mode(active_attack)
        time.sleep(attack_dur)

        # 3. Transition back to long, dominant NORMAL recovery windows (unpredictably spaced)
        # Normal durations are kept very long (3 to 5.5 minutes) so that attacks are sparse
        recovery_dur = random.randint(180, 330) 
        
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
