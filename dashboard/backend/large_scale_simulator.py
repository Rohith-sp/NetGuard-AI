"""
NetGuard AI — 50-Node Large-Scale IoT Network Simulator
Generates a realistic hierarchical network topology using NetworkX and simulates
telemetry traffic for 50 virtual IoT devices over MQTT.

Features:
- Event-driven non-blocking simulation loop (handles 50 nodes on a single thread).
- Publishes hierarchical graph structure (nodes & edges) to `netguard_50node/topology`.
- Subscribes to `netguard_50node/cmd` to command active attack simulations.
- Simulates all 7 attack vectors (DoS, Replay, Slow Rate, Data Poison, Topic Bomb, Evasion).
- Isolated topic namespace (`netguard_50node/`) to avoid polluting real ESP32 traffic.
"""
import json
import time
import math
import random
import threading
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt
import networkx as nx

BROKER = "broker.hivemq.com"
PORT = 1883
IST = timezone(timedelta(hours=5, minutes=30))

# ── Sensor Modeling Helpers ──────────────────────────────────────────────────
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

# ── Network Topology Generation ──────────────────────────────────────────────
# Generate a clustered topology
G = nx.Graph()
G.add_node(0, label="Gateway", type="gateway")

# Add cluster heads
G.add_node(1, label="DHT Cluster Head", type="router")
G.add_node(2, label="LDR Cluster Head", type="router")
G.add_node(3, label="PIR Cluster Head", type="router")
G.add_edge(0, 1)
G.add_edge(0, 2)
G.add_edge(0, 3)

# DHT Nodes (Node 4 to 20)
for idx in range(4, 21):
    G.add_node(idx, label=f"esp32_{idx}", type="dht")
    # Connect to DHT Cluster Head or hierarchically
    parent = 1 if idx < 12 else random.randint(4, idx-1)
    G.add_edge(parent, idx)

# LDR Nodes (Node 21 to 35)
for idx in range(21, 36):
    G.add_node(idx, label=f"esp32_{idx}", type="ldr")
    parent = 2 if idx < 28 else random.randint(21, idx-1)
    G.add_edge(parent, idx)

# PIR/Attacker Nodes (Node 36 to 50)
for idx in range(36, 51):
    G.add_node(idx, label=f"esp32_{idx}", type="pir")
    parent = 3 if idx < 43 else random.randint(36, idx-1)
    G.add_edge(parent, idx)

TOPOLOGY_DATA = {
    "nodes": [{"id": n, "label": G.nodes[n]["label"], "type": G.nodes[n]["type"]} for n in G.nodes],
    "links": [{"source": u, "target": v} for u, v in G.edges]
}

# ── Simulator State ─────────────────────────────────────────────────────────
sim_attack_mode = "NORMAL"
compromised_node_id = 45  # Default target PIR node
poison_node_id = 5        # Default target DHT node
attacker_seq = 0
replay_frozen_payload = None

# Individual node publish schedulers
node_states = {}
for n in G.nodes:
    if n == 0 or G.nodes[n]["type"] == "router":
        continue
    
    node_states[n] = {
        "device": f"esp32_{n}",
        "type": G.nodes[n]["type"],
        "seq": 0,
        "next_pub": time.time() + random.uniform(1.0, 5.0),
        "last_pub": 0.0,
        "status": "NORMAL"
    }

# ── MQTT Client Setup ───────────────────────────────────────────────────────
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "netguard-large-simulator")

def on_connect(c, u, flags, rc, p=None):
    print(f"[MQTT] Simulator connected with result code {rc}")
    c.subscribe("netguard_50node/cmd")
    # Publish topology layout immediately
    publish_topology()

def on_message(c, u, msg):
    global sim_attack_mode, replay_frozen_payload, compromised_node_id, poison_node_id
    try:
        payload = json.loads(msg.payload.decode())
        cmd = payload.get("command")
        if cmd == "SET_MODE":
            sim_attack_mode = payload.get("mode", "NORMAL").upper()
            # Allow targeting specific nodes
            if "target_node" in payload:
                target = int(payload["target_node"])
                if target in node_states:
                    ntype = node_states[target]["type"]
                    if ntype == "pir":
                        compromised_node_id = target
                    elif ntype == "dht":
                        poison_node_id = target
            replay_frozen_payload = None
            print(f"[CMD] Simulator Attack Mode set to: {sim_attack_mode} (compromised={compromised_node_id}, poison={poison_node_id})")
        elif cmd == "RELEASE":
            sim_attack_mode = "NORMAL"
            replay_frozen_payload = None
            print("[CMD] Simulator Attack Mode released to: NORMAL")
    except Exception as e:
        print(f"[CMD] Error parsing command: {e}")

client.on_connect = on_connect
client.on_message = on_message

def publish_topology():
    payload = json.dumps({"topic": "netguard_50node/topology", **TOPOLOGY_DATA})
    client.publish("netguard_50node/topology", payload, retain=True)
    print(f"[Topology] Published network map with {len(G.nodes)} nodes and {len(G.edges)} edges.")

def trigger_attack(node_id: int, mode: str):
    """Programmatically trigger an attack on a specific node via MQTT command."""
    cmd = {"command": "SET_MODE", "mode": mode.upper(), "target_node": node_id}
    client.publish("netguard_50node/cmd", json.dumps(cmd))
    print(f"[TRIGGER] Attack {mode} on node {node_id}")

# ── Simulation Tick Loop ────────────────────────────────────────────────────
def run_simulation_loop():
    global attacker_seq, replay_frozen_payload
    print("[Simulator] Starting event-driven simulation loop...")
    
    # Send topology periodically
    last_topo_time = 0.0

    while True:
        now = time.time()
        
        # 1. Periodically republish topology map
        if now - last_topo_time > 15.0:
            publish_topology()
            # Also publish node status summary
            status_summary = {}
            for nid, state in node_states.items():
                is_compromised = (state["type"] == "pir" and nid == compromised_node_id and sim_attack_mode != "NORMAL")
                is_poisoned = (state["type"] == "dht" and nid == poison_node_id and sim_attack_mode == "DATA_POISON")
                if is_compromised:
                    status_summary[str(nid)] = sim_attack_mode
                elif is_poisoned:
                    status_summary[str(nid)] = "DATA_POISON"
                else:
                    status_summary[str(nid)] = "NORMAL"
            client.publish("netguard_50node/status", json.dumps({
                "topic": "netguard_50node/status",
                "mode": sim_attack_mode,
                "compromised": compromised_node_id,
                "poison": poison_node_id,
                "node_states": status_summary
            }))
            last_topo_time = now

        # 2. Check scheduled publishes for each node
        for nid, state in node_states.items():
            if now >= state["next_pub"]:
                device = state["device"]
                node_type = state["type"]
                state["seq"] += 1
                
                # Check if this node is compromised or poisoned under the active attack mode
                is_compromised = (node_type == "pir" and nid == compromised_node_id)
                is_poisoned = (node_type == "dht" and nid == poison_node_id)
                
                # Default timings
                min_delay, max_delay = 4.0, 8.0 # Slower baseline to protect broker
                
                if is_compromised and sim_attack_mode != "NORMAL":
                    # Compromised node attack execution
                    if sim_attack_mode == "DOS_FLOOD":
                        min_delay, max_delay = 0.15, 0.35
                        payload = json.dumps({
                            "device": device, "mode": "DOS_FLOOD",
                            "seq": state["seq"], "manual": True
                        })
                        client.publish("netguard_50node/attacker", payload)
                        
                    elif sim_attack_mode == "REPLAY_ATTACK":
                        min_delay, max_delay = 0.8, 1.5
                        payload = json.dumps({
                            "device": device, "mode": "REPLAY_ATTACK",
                            "seq": 520, "manual": True # Frozen sequence
                        })
                        client.publish("netguard_50node/attacker", payload)
                        
                    elif sim_attack_mode == "SLOW_RATE_ATTACK":
                        min_delay, max_delay = 15.0, 30.0
                        payload = json.dumps({
                            "device": device, "mode": "SLOW_RATE_ATTACK",
                            "seq": state["seq"], "manual": True
                        })
                        client.publish("netguard_50node/attacker", payload)
                        
                    elif sim_attack_mode == "TOPIC_BOMB":
                        min_delay, max_delay = 0.05, 0.10
                        payload = json.dumps({
                            "device": device, "mode": "TOPIC_BOMB",
                            "seq": state["seq"], "manual": True
                        })
                        # Bomb random junk topics
                        junk_topic = f"netguard_50node/junk_{random.randint(100000, 999999)}"
                        client.publish(junk_topic, payload)
                        
                    elif sim_attack_mode == "EVASION_ATTACK":
                        # High jitter delay
                        min_delay, max_delay = 0.15, 3.5
                        payload = json.dumps({
                            "device": device, "mode": "EVASION_ATTACK",
                            "seq": state["seq"], "manual": True
                        })
                        client.publish("netguard_50node/attacker", payload)
                        
                    else:
                        # Fallback / Normal
                        payload = json.dumps({
                            "device": device, "mode": "NORMAL",
                            "seq": state["seq"], "manual": False
                        })
                        client.publish("netguard_50node/attacker", payload)
                        
                elif is_poisoned and sim_attack_mode == "DATA_POISON":
                    # Data poisoning sensor execution
                    h = ist_hour()
                    payload = json.dumps({
                        "device": device, "temp": 999.0, "humidity": -100.0,
                        "ist_hour": round(h, 2), "synced": True, "mode": "DATA_POISON"
                    })
                    client.publish(f"netguard_50node/device{nid}", payload)
                    print(f"[POISON] {device} -> Spoofed temperature published!")
                    
                else:
                    # NORMAL Sensor/PIR Execution
                    h = ist_hour()
                    if node_type == "dht":
                        temp = bangalore_temp(h)
                        hum = bangalore_hum(h)
                        payload = json.dumps({
                            "device": device, "temp": temp, "humidity": hum,
                            "ist_hour": round(h, 2), "synced": True, "mode": "NORMAL"
                        })
                        client.publish(f"netguard_50node/device{nid}", payload)
                        
                    elif node_type == "ldr":
                        lux = bangalore_light(h)
                        payload = json.dumps({
                            "device": device, "light": lux,
                            "ist_hour": round(h, 2), "synced": True, "mode": "NORMAL"
                        })
                        client.publish(f"netguard_50node/device{nid}", payload)
                        
                    elif node_type == "pir":
                        payload = json.dumps({
                            "device": device, "mode": "NORMAL",
                            "seq": state["seq"], "manual": False
                        })
                        client.publish("netguard_50node/attacker", payload)

                # Reschedule next publish
                state["last_pub"] = now
                state["next_pub"] = now + random.uniform(min_delay, max_delay)

        # Non-blocking tiny sleep to keep CPU usage at 0%
        time.sleep(0.01)

# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print(" NetGuard AI — Large-Scale 50-Node Network Simulator")
    print(f" Connecting to MQTT Broker: {BROKER}:{PORT}")
    print(f" Topic Namespace: netguard_50node/*")
    print("=" * 60)

    try:
        client.connect(BROKER, PORT, 60)
        # Start command listening thread
        client.loop_start()
        
        # Start event simulation loop (blocking main thread)
        run_simulation_loop()
        
    except KeyboardInterrupt:
        print("\n[SIM] Stopping simulator...")
        client.loop_stop()
        print("[SIM] Stopped.")
