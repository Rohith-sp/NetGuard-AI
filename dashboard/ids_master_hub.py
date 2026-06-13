import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
from collections import deque
import threading

# ─── CONFIGURATION & PAGE SETUP ───────────────────────────────────────────────
st.set_page_config(page_title="NetGuard AI Master Hub", layout="wide", initial_sidebar_state="collapsed")

# ─── CUSTOM CSS (Phase 1 Aesthetic) ───────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    
    /* Global Styles */
    .stApp {
        background-color: #f0f4f2;
        color: #1a2e22;
        font-family: 'Rajdhani', sans-serif;
    }
    
    /* Typography */
    h1, h2, h3 {
        font-family: 'Orbitron', sans-serif !important;
        color: #00884a !important;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    
    /* Header Box */
    .header-box {
        background: rgba(240, 244, 242, 0.92);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(0, 136, 74, 0.2);
        border-bottom: 2px solid #00884a;
        padding: 15px 30px;
        border-radius: 5px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 30px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    
    /* Metric Cards */
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #c8dece;
        border-left: 4px solid #00884a;
        padding: 20px;
        border-radius: 4px;
        box-shadow: 0 2px 12px rgba(0, 136, 74, 0.05);
        transition: transform 0.3s, box-shadow 0.3s;
        height: 100%;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(0, 136, 74, 0.15);
    }
    .metric-label {
        font-family: 'Orbitron', sans-serif;
        font-size: 0.8rem;
        font-weight: 700;
        color: #00884a;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 5px;
    }
    .metric-value {
        font-family: 'Share Tech Mono', monospace;
        font-size: 2rem;
        color: #1a2e22;
        font-weight: bold;
        margin: 10px 0;
    }
    .metric-sub {
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.8rem;
        color: #7a9a84;
    }
    
    /* Blinking Status Dot */
    .status-dot {
        height: 10px;
        width: 10px;
        background-color: #00884a;
        border-radius: 50%;
        display: inline-block;
        margin-right: 8px;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 136, 74, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 10px rgba(0, 136, 74, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 136, 74, 0); }
    }
    
    /* Card Variants */
    .card-amber { border-left-color: #c07800; }
    .card-amber .metric-label { color: #c07800; }
    
    .card-cyan { border-left-color: #006699; }
    .card-cyan .metric-label { color: #006699; }
    
    .card-red { border-left-color: #cc1122; }
    .card-red .metric-label { color: #cc1122; }
    
    .card-purple { border-left-color: #7744cc; }
    .card-purple .metric-label { color: #7744cc; }
</style>
""", unsafe_allow_html=True)

# ─── GLOBAL STATE (Preserved across Streamlit reruns) ─────────────────────────
if 'packet_buffer' not in st.session_state:
    st.session_state.packet_buffer = deque(maxlen=2000)
    st.session_state.latest_telemetry = {
        'esp32_1': {'temp': 0.0, 'humidity': 0.0, 'last_seen': 'Awaiting Data...'},
        'esp32_2': {'light': 0, 'last_seen': 'Awaiting Data...'},
        'esp32_3': {'mode': 'Awaiting Data...', 'seq': 0, 'last_seen': 'Awaiting Data...'}
    }

# ─── MQTT BACKGROUND THREAD ───────────────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    client.subscribe("netguard_rohit_77/#")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        device = payload.get('device')
        if device in st.session_state.latest_telemetry:
            # Update specific telemetry fields
            for k, v in payload.items():
                if k != 'device':
                    st.session_state.latest_telemetry[device][k] = v
            # Stamp the time we saw it
            st.session_state.latest_telemetry[device]['last_seen'] = time.strftime('%H:%M:%S')
            
            # Add to rolling buffer for global packet rate calculation
            st.session_state.packet_buffer.append(time.time())
    except Exception as e:
        pass

@st.cache_resource
def start_mqtt_listener():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("broker.hivemq.com", 1883, 60)
    thread = threading.Thread(target=client.loop_forever)
    thread.daemon = True
    thread.start()
    return client

start_mqtt_listener()

# ─── UI RENDERING ─────────────────────────────────────────────────────────────

# Header
st.markdown("""
<div class="header-box">
    <div>
        <h2 style="margin:0; font-size:1.5rem;">⬡ NETGUARD AI : MASTER HUB</h2>
        <span style="font-family:'Share Tech Mono'; color:#3a5a44; font-size:0.9rem;">
            Security Operations Center &middot; Phase 5
        </span>
    </div>
    <div style="font-family:'Orbitron'; color:#00884a; font-weight:bold; font-size:0.9rem;">
        <span class="status-dot"></span> LIVE TELEMETRY
    </div>
</div>
""", unsafe_allow_html=True)

# Math: Calculate packets per second
current_time = time.time()
while st.session_state.packet_buffer and st.session_state.packet_buffer[0] < current_time - 1.0:
    st.session_state.packet_buffer.popleft()
pkt_rate = len(st.session_state.packet_buffer)

# Fetch Data
dht = st.session_state.latest_telemetry['esp32_1']
ldr = st.session_state.latest_telemetry['esp32_2']
atk = st.session_state.latest_telemetry['esp32_3']

st.markdown("### 📡 Node Status Board")

# Top Row: Metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">ESP32_1 (Legitimate DHT)</div>
        <div class="metric-value">{dht.get('temp', 0):.1f}°C / {dht.get('humidity', 0):.1f}%</div>
        <div class="metric-sub">Last Seen: {dht['last_seen']}</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card card-cyan">
        <div class="metric-label">ESP32_2 (Legitimate LDR)</div>
        <div class="metric-value">{ldr.get('light', 0)} LUX</div>
        <div class="metric-sub">Last Seen: {ldr['last_seen']}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    # Change color based on attacker mode
    atk_mode = atk.get('mode', 'UNKNOWN')
    if atk_mode == 'NORMAL' or atk_mode == 'Awaiting Data...':
        card_class = "card-amber"
        val_color = "#c07800"
    else:
        card_class = "card-red"
        val_color = "#cc1122"
        
    st.markdown(f"""
    <div class="metric-card {card_class}">
        <div class="metric-label">ESP32_3 (Attacker Node)</div>
        <div class="metric-value" style="color: {val_color}; font-size: 1.5rem; margin-top:15px;">{atk_mode}</div>
        <div class="metric-sub">Seq: {atk.get('seq', 0)} | Last Seen: {atk['last_seen']}</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card card-purple">
        <div class="metric-label">Global Traffic Density</div>
        <div class="metric-value">{pkt_rate} PKT/S</div>
        <div class="metric-sub">Broker: broker.hivemq.com</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Placeholders for future sections
st.markdown("### 📈 Temporal Security Graph (Coming Next)")
st.info("The AI Inference engine and SHAP explainability layer will be integrated here.")

# ─── AUTO-REFRESH LOOP ────────────────────────────────────────────────────────
# Pauses for 1 second, then reruns the entire Streamlit script to update UI.
time.sleep(1)
st.rerun()
