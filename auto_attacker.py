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
    
    # 1. Initial baseline to record clean normal data (Stealth startup)
    initial_normal_dur = random.randint(45, 90)
    print(f"\n[*] [INIT] Establishing initial NORMAL baseline traffic for {initial_normal_dur} seconds...")
    send_mode("NORMAL")
    time.sleep(initial_normal_dur)

    while True:
        # 2. Unpredictable Attacking Behavior
        # Determine if we run a single attack or a chained back-to-back attack (30% chance of chain)
        is_chain = random.random() < 0.30
        
        attacks_to_run = []
        if is_chain:
            # Pick 2 distinct attacks to chain back-to-back
            atk1 = random.choice(ATTACKS)
            atk2 = random.choice([a for a in ATTACKS if a != atk1])
            attacks_to_run = [atk1, atk2]
            print(f"\n[!] [SNEAKY] Attacker is planning a CHAIN attack: {atk1} ➔ {atk2}!")
        else:
            attacks_to_run = [random.choice(ATTACKS)]

        for active_attack in attacks_to_run:
            # Determine attack intensity & duration profiles
            roll = random.random()
            if roll < 0.20:
                # 20% chance: Short aggressive burst
                attack_dur = random.randint(5, 12)
                intensity = "SHORT BURST"
            elif roll < 0.85:
                # 65% chance: Standard attack
                attack_dur = random.randint(20, 45)
                intensity = "STANDARD"
            else:
                # 15% chance: Heavy sustained threat
                attack_dur = random.randint(60, 100)
                intensity = "HEAVY SUSTAINED"
                
            print(f"\n[!] [ATTACK] Launching {intensity} {active_attack} for {attack_dur} seconds...")
            send_mode(active_attack)
            time.sleep(attack_dur)
            
            # If we are chaining, insert a tiny transition delay (1-2s) or switch immediately
            if is_chain and active_attack != attacks_to_run[-1]:
                time.sleep(random.uniform(0.5, 2.0))

        # 3. Transition back to NORMAL recovery (with randomized resting periods)
        normal_roll = random.random()
        if normal_roll < 0.25:
            # 25% chance: Quick scan/recovery (attacker goes low-profile briefly)
            recovery_dur = random.randint(15, 25)
            profile = "QUICK RECOVERY"
        elif normal_roll < 0.85:
            # 60% chance: Standard normal baseline
            recovery_dur = random.randint(45, 75)
            profile = "STANDARD NORMAL"
        else:
            # 15% chance: Long stealth resting (completely hidden to mimic normal operations)
            recovery_dur = random.randint(120, 180)
            profile = "STEALTH DECEPTIVE REST"
            
        print(f"\n[*] [NORMAL] Resetting to {profile} baseline for {recovery_dur} seconds...")
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
