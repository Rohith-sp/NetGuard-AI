"""
NetGuard AI — Real-time Physical Hardware Telemetry Collector
=============================================================
Connects to your MQTT broker, displays a live terminal dashboard of incoming 
ESP32 traffic, and logs raw packets to a structured CSV file for training.

Features:
  - Interactive terminal layout (using ANSI colors & msvcrt key polling)
  - Toggle between Auto-labeling (from payloads) and Manual-labeling (keyboard hotkeys)
  - Real-time inter-arrival time and packet rate counters per device
  - Graceful connection handling and CSV logging

Dependencies:
  pip install paho-mqtt

Usage:
  python real_time_collector.py
"""

import json
import csv
import os
import sys
import time
import threading
import msvcrt  # Native Windows console input
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ── Colors & UI helpers ───────────────────────────────────────────────────────
CLR_ESC = "\033["
RESET = CLR_ESC + "0m"
BOLD = CLR_ESC + "1m"
GREEN = CLR_ESC + "32m"
RED = CLR_ESC + "31m"
YELLOW = CLR_ESC + "33m"
BLUE = CLR_ESC + "36m"
MAGENTA = CLR_ESC + "35m"
BG_DARK = CLR_ESC + "40m"
WHITE = CLR_ESC + "37m"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# ── Load Config ───────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
try:
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)
except Exception as e:
    # Fallback default configuration
    config = {
        "broker": "broker.hivemq.com",
        "port": 1883,
        "topics": {
            "netguard_rohit_77/device1": {"device_id": "esp32_1", "description": "DHT22 Node"},
            "netguard_rohit_77/device2": {"device_id": "esp32_2", "description": "LDR Node"},
            "netguard_rohit_77/attacker": {"device_id": "esp32_3", "description": "Attacker Node"}
        },
        "output_directory": "./collected_datasets",
        "default_label": "NORMAL"
    }

BROKER = config.get("broker", "broker.hivemq.com")
PORT = config.get("port", 1883)
TOPIC_MAP = config.get("topics", {})
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), config.get("output_directory", "./collected_datasets")))

# CSV schema matching ML training system
CSV_COLUMNS = [
    "timestamp_utc",     # ISO-8601 timestamp
    "topic",             # MQTT topic
    "device",            # device identifier from payload
    "mode",              # mode / state reported by device
    "seq",               # sequence number (or -1 if none)
    "temp",              # temperature (DHT only, else -1)
    "humidity",          # humidity (DHT only, else -1)
    "light",             # light value (LDR only, else -1)
    "inter_arrival_ms",  # ms since last packet from SAME device
    "label"              # ground-truth target class (NORMAL, DOS_FLOOD, etc.)
]

# ── Global State ──────────────────────────────────────────────────────────────
is_logging = True
label_mode = "AUTO"  # "AUTO" (from attacker payload) or "MANUAL" (user hotkeys)
current_label = "NORMAL"  # Active label for manual mode
total_packets = 0
last_seen = {}       # device_id -> float epoch seconds
device_stats = {}    # device_id -> dict of stats (packet_count, rate, last_values)
recent_logs = []     # list of strings for bottom scrolling terminal log
stats_lock = threading.Lock()
csv_file_path = ""
session_start_time = datetime.now()

# ── Setup Logging Session ─────────────────────────────────────────────────────
def start_new_session():
    global csv_file_path, session_start_time, total_packets
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session_start_time = datetime.now()
    timestamp = session_start_time.strftime("%Y%m%d_%H%M%S")
    csv_file_path = os.path.join(OUTPUT_DIR, f"telemetry_session_{timestamp}.csv")
    
    with open(csv_file_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
    
    total_packets = 0
    with stats_lock:
        device_stats.clear()
        last_seen.clear()
    
    add_log(f"Started new session: {os.path.basename(csv_file_path)}")

def add_log(msg):
    with stats_lock:
        recent_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        if len(recent_logs) > 6:
            recent_logs.pop(0)

# ── MQTT Client Callbacks ─────────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        add_log(f"Connected to MQTT Broker ({BROKER}:{PORT})")
        client.subscribe("netguard_rohit_77/#", 0)
        add_log("Subscribed to wildcard topic → netguard_rohit_77/#")
    else:
        add_log(f"Connection failed with code {rc}")

def on_message(client, userdata, msg):
    global total_packets, current_label
    
    now = time.time()
    ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    topic = msg.topic
    
    try:
        payload_raw = msg.payload.decode("utf-8", errors="ignore")
        payload = json.loads(payload_raw)
    except Exception:
        # Skip malformed payloads
        return

    # Map topic to device config
    device_config = TOPIC_MAP.get(topic, {})
    device = payload.get("device", device_config.get("device_id", topic.split("/")[-1]))
    
    # Calculate Inter-arrival Time
    with stats_lock:
        prev_time = last_seen.get(device)
        last_seen[device] = now
    
    if prev_time is None:
        ia_ms = -1
    else:
        ia_ms = int((now - prev_time) * 1000)
    
    # Parse payload fields
    mode = payload.get("mode", "NORMAL")
    seq = payload.get("seq", -1)
    temp = payload.get("temp", -1)
    hum = payload.get("humidity") if payload.get("humidity") is not None else payload.get("hum", -1)
    light = payload.get("light", -1)
    
    # Determine Ground Truth Label
    if label_mode == "AUTO":
        # Check if the payload mode represents an active attack
        if mode in ["DOS_FLOOD", "REPLAY_ATTACK", "SLOW_RATE_ATTACK", "DATA_POISON", "TOPIC_BOMB", "EVASION_ATTACK"]:
            lbl = mode
            current_label = mode # Keep manual synced for display
        elif topic == "netguard_rohit_77/attacker":
            lbl = mode
            current_label = mode
        else:
            # If standard node and no payload mode matches, check if attacker state is active
            lbl = current_label
    else:
        lbl = current_label

    # Save to Session CSV
    if is_logging:
        row = {
            "timestamp_utc": ts_str,
            "topic": topic,
            "device": device,
            "mode": mode,
            "seq": seq,
            "temp": temp,
            "humidity": hum,
            "light": light,
            "inter_arrival_ms": ia_ms,
            "label": lbl
        }
        
        try:
            with open(csv_file_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                writer.writerow(row)
            
            with stats_lock:
                total_packets += 1
        except Exception as e:
            add_log(f"CSV Write Error: {str(e)}")

    # Update Statistics
    with stats_lock:
        if device not in device_stats:
            device_stats[device] = {
                "count": 0,
                "first_seen": now,
                "rates": [],
                "last_values": {}
            }
        
        d_stat = device_stats[device]
        d_stat["count"] += 1
        
        # Keep track of last metrics
        if temp != -1: d_stat["last_values"]["temp"] = f"{temp}°C"
        if hum != -1: d_stat["last_values"]["humidity"] = f"{hum}%"
        if light != -1: d_stat["last_values"]["light"] = f"{light} LUX"
        if seq != -1: d_stat["last_values"]["seq"] = f"#{seq}"
        if mode != "NORMAL": d_stat["last_values"]["mode"] = mode

# ── Render Console Dashboard ──────────────────────────────────────────────────
def render_dashboard(client_connected):
    # Calculate screen output lines
    lines = []
    lines.append(f"{BOLD}{GREEN}========================================================================={RESET}")
    lines.append(f"{BOLD}                 NETGUARD AI — REAL-TIME IoT DATA COLLECTOR              {RESET}")
    lines.append(f"{BOLD}{GREEN}========================================================================={RESET}")
    
    # Connection details
    conn_status = f"{GREEN}CONNECTED{RESET}" if client_connected else f"{RED}DISCONNECTED{RESET}"
    lines.append(f"  {BOLD}Broker:{RESET} {BROKER}:{PORT}   |   {BOLD}Status:{RESET} {conn_status}")
    lines.append(f"  {BOLD}Session File:{RESET} {os.path.basename(csv_file_path)}")
    
    # Session statistics
    elapsed = str(datetime.now() - session_start_time).split('.')[0]
    log_status = f"{GREEN}REC{RESET}" if is_logging else f"{YELLOW}PAUSED{RESET}"
    lines.append(f"  {BOLD}Logged Packets:{RESET} {total_packets:<6}   |   {BOLD}Time:{RESET} {elapsed}   |   {BOLD}State:{RESET} [{log_status}]")
    
    # Labeling Mode info
    lbl_src = f"{BLUE}Attacker Node Payload{RESET}" if label_mode == "AUTO" else f"{MAGENTA}Manual Override{RESET}"
    lines.append(f"  {BOLD}Label Mode:{RESET} {label_mode} (Source: {lbl_src})")
    
    # Active Label highlight
    lbl_color = GREEN if current_label == "NORMAL" else (YELLOW if current_label == "SLOW_RATE_ATTACK" else RED)
    lines.append(f"  {BOLD}Active Telemetry Class Label:{RESET} {lbl_color}{BOLD}{current_label}{RESET}")
    lines.append(f"{GREEN}------------------------------------------------------------------------{RESET}")
    
    # Device table header
    lines.append(f"  {BOLD}{'Device ID':<12} | {'Packets':<8} | {'Frequency':<9} | {'Latest Metrics / State':<32}{RESET}")
    lines.append(f"  {'-'*12} | {'-'*8} | {'-'*9} | {'-'*32}")
    
    # Device stats body
    now = time.time()
    with stats_lock:
        devices = sorted(device_stats.keys())
        for dev in devices:
            stat = device_stats[dev]
            
            # Calculate frequency rate (Hz)
            dt = now - stat["first_seen"]
            rate = stat["count"] / dt if dt > 0 else 0.0
            rate_str = f"{rate:.2f} Hz"
            
            # Format values preview
            metrics = []
            for k, v in stat["last_values"].items():
                metrics.append(f"{k}={v}")
            metrics_str = ", ".join(metrics)[:32]
            
            lines.append(f"  {dev:<12} | {stat['count']:<8} | {rate_str:<9} | {metrics_str:<32}")
            
        if not devices:
            lines.append(f"  {'(Waiting for ESP32 packets to arrive...)':^67}")
            
    lines.append(f"{GREEN}------------------------------------------------------------------------{RESET}")
    
    # Command Legend
    lines.append(f"  {BOLD}Controls:{RESET}")
    lines.append(f"    [Space] Pause/Resume Logging    [M] Set Manual Labeling Mode")
    lines.append(f"    [A] Set Auto Labeling Mode      [N] Reset/Start New File Session")
    lines.append(f"    [0] Tag NORMAL       [1] Tag DOS_FLOOD    [2] Tag REPLAY_ATTACK    [3] Tag SLOW_RATE_ATTACK")
    lines.append(f"    [4] Tag DATA_POISON  [5] Tag TOPIC_BOMB   [6] Tag EVASION_ATTACK")
    lines.append(f"    [Q] Quit Safely")
    lines.append(f"{GREEN}------------------------------------------------------------------------{RESET}")
    
    # Scrolling logs window
    lines.append(f"  {BOLD}System Message Logs:{RESET}")
    with stats_lock:
        for log in recent_logs:
            lines.append(f"    {log}")
        # fill gaps
        for _ in range(6 - len(recent_logs)):
            lines.append("")
            
    lines.append(f"{GREEN}========================================================================={RESET}")
    
    # Clear console and write single frame to avoid screen flicker
    clear_screen()
    print("\n".join(lines))

# ── Main Control Thread ───────────────────────────────────────────────────────
def main():
    global is_logging, label_mode, current_label
    
    # Enable color console on Windows
    if os.name == 'nt':
        os.system('color')
        
    start_new_session()
    
    # Initialize MQTT
    client_id = f"NetGuard-RealTime-Collector"
    mqttc = mqtt.Client(client_id=client_id)
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message
    
    mqttc.reconnect_delay_set(min_delay=1, max_delay=30)
    
    try:
        mqttc.connect(BROKER, PORT, keepalive=60)
    except Exception as e:
        add_log(f"Connection error to {BROKER}: {str(e)}")
        
    mqttc.loop_start()
    
    add_log("Starting keyboard listener loop...")
    
    # Main dashboard update loop
    last_render = 0
    try:
        while True:
            # Poll keys via msvcrt (non-blocking)
            if msvcrt.kbhit():
                char = msvcrt.getch()
                # Handle special keys or decode character
                try:
                    key = char.decode('utf-8').lower()
                except Exception:
                    key = ""
                    
                if key == ' ':
                    is_logging = not is_logging
                    add_log(f"Logging {'RESUMED' if is_logging else 'PAUSED'}")
                elif key == 'a':
                    label_mode = "AUTO"
                    add_log("Labeling Mode set to AUTO (reads attacker node payload)")
                elif key == 'm':
                    label_mode = "MANUAL"
                    add_log("Labeling Mode set to MANUAL (keyboard overrides)")
                elif key == 'n':
                    start_new_session()
                elif key == '0':
                    current_label = "NORMAL"
                    add_log("Manual Ground Truth Tag → NORMAL")
                elif key == '1':
                    current_label = "DOS_FLOOD"
                    add_log("Manual Ground Truth Tag → DOS_FLOOD")
                elif key == '2':
                    current_label = "REPLAY_ATTACK"
                    add_log("Manual Ground Truth Tag → REPLAY_ATTACK")
                elif key == '3':
                    current_label = "SLOW_RATE_ATTACK"
                    add_log("Manual Ground Truth Tag → SLOW_RATE_ATTACK")
                elif key == '4':
                    current_label = "DATA_POISON"
                    add_log("Manual Ground Truth Tag → DATA_POISON")
                elif key == '5':
                    current_label = "TOPIC_BOMB"
                    add_log("Manual Ground Truth Tag → TOPIC_BOMB")
                elif key == '6':
                    current_label = "EVASION_ATTACK"
                    add_log("Manual Ground Truth Tag → EVASION_ATTACK")
                elif key == 'q':
                    add_log("Stopping collector loop...")
                    break
            
            # Throttle dashboard rendering (approx. 4 updates a second)
            now = time.time()
            if now - last_render >= 0.25:
                render_dashboard(mqttc.is_connected())
                last_render = now
                
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        pass
    finally:
        mqttc.loop_stop()
        mqttc.disconnect()
        print(f"\n[+] Stopped logging. Dataset saved to:")
        print(f"    {csv_file_path}")

if __name__ == "__main__":
    main()
