<div align="center">

# NetGuard AI
### Real-Time IoT Intrusion Detection System

**Semester IV Elective Lab — IoT Security Operations Center**

[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.8-orange?style=flat-square&logo=scikit-learn)](https://scikit-learn.org)
[![SHAP](https://img.shields.io/badge/SHAP-0.51-purple?style=flat-square)](https://shap.readthedocs.io)
[![MQTT](https://img.shields.io/badge/MQTT-HiveMQ-green?style=flat-square)](https://www.hivemq.com)

</div>

---

## Overview

NetGuard AI is a complete, end-to-end IoT intrusion detection system built on real ESP32 hardware. It monitors network traffic from three physical nodes in real time, uses a trained Random Forest classifier to detect cyberattacks (supporting six distinct attack modes in hardware), explains every decision using SHAP values, and presents everything in a live Next.js SOC dashboard.

The system is fully explainable — every classification comes with a breakdown of which network features drove the decision, an auto-generated natural language incident report, and an AI chatbot that can answer questions about the current network state in plain English.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HARDWARE LAYER                                      │
│                                                                             │
│  ESP32_1 (DHT11)          ESP32_2 (LDR)          ESP32_3 (Attacker)        │
│  • Temperature sensor     • Light sensor          • Attack simulator        │
│  • Alert subscriber       • Publishes LUX         • 7 attack/sim modes      │
│  • LED + Buzzer on alert    netguard/device2      • I2C 16x2 LCD Display    │
│  • Publishes to                                   • Button/MQTT controlled  │
│    netguard/device1                               • Publishes to            │
│                                                     netguard/attacker       │
└──────────────┬───────────────────┬───────────────────┬──────────────────────┘
               │                   │                   │
               └───────────────────┴───────────────────┘
                                   │
                                   ▼  MQTT (port 1883)
                    ┌──────────────────────────────┐
                    │   broker.hivemq.com (Public) │
                    │   Topic namespace: netguard/# │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
          ┌─────────────────────────────────────────────────────┐
          │              FASTAPI BACKEND  (port 8000)           │
          │                                                     │
          │  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  │
          │  │ MQTT Client │  │  ML Inference │  │   SHAP   │  │
          │  │  (Paho)     │  │  Every 5s     │  │ Explainer│  │
          │  └──────┬──────┘  └──────┬───────┘  └────┬─────┘  │
          │         │                │                │        │
          │  ┌──────▼────────────────▼────────────────▼──────┐ │
          │  │          WebSocket Bridge  /ws/live            │ │
          │  └──────────────────────────┬────────────────────┘ │
          │                             │                      │
          │  ┌──────────────────────────▼────────────────────┐ │
          │  │  RAG Analyst  (Groq LLM / Gemini / Fallback)  │ │
          │  └───────────────────────────────────────────────┘ │
          │                                                     │
          │  Alert Publisher → netguard/alerts (ESP32 buzzer)  │
          └──────────────────────────┬──────────────────────────┘
                                     │  WebSocket
                                     ▼
          ┌─────────────────────────────────────────────────────┐
          │           NEXT.JS DASHBOARD  (port 3000)            │
          │                                                     │
          │  Live Analytics │ Overview │ Topology │ AI Analyst  │
          └─────────────────────────────────────────────────────┘
```

---

## Hardware Nodes

### ESP32_1 — DHT11 Sensor Node (`arduino_codes/netguard-dht/`)

The primary environmental sensor node. Reads temperature and humidity from a DHT11 sensor and publishes to `netguard/device1` every ~3 seconds. Also subscribes to `netguard/alerts` — when the ML model detects an attack, this node receives the alert and triggers a red LED flash + buzzer for 5 seconds as a physical alarm.

**MQTT Payload:**
```json
{
  "device": "esp32_1",
  "temp": 28.3,
  "humidity": 65.0,
  "seq": 412,
  "ist_hour": 14.52,
  "synced": true
}
```

### ESP32_2 — LDR Sensor Node (`arduino_codes/netguard-ldr/`)

Ambient light sensor using an LDR (Light Dependent Resistor). Publishes light intensity in LUX to `netguard/device2`. Values follow a natural day/night curve aligned to IST (Indian Standard Time) via the timesync system.

**MQTT Payload:**
```json
{
  "device": "esp32_2",
  "light": 847,
  "seq": 201,
  "ist_hour": 14.52,
  "synced": true
}
```

### ESP32_3 — Attacker Node (`arduino_codes/netguard-attacker/`)

A standalone ESP32 that simulates six distinct cyberattack patterns (plus a normal mode). The active mode can be cycled using a physical push button on the board or triggered remotely from the dashboard via MQTT. It also outputs status messages and attack modes on an attached **16x2 I2C LCD screen** (SDA ➔ GPIO 21, SCL ➔ GPIO 22).

| Mode | Button Cycle | Behavior | IAT | Packet Rate | Target Topic |
|---|---|---|---|---|---|
| `NORMAL` | Mode 1 | Mimics legitimate sensor | 2–5 seconds | ~0.3 pkt/s | `netguard/attacker` |
| `DOS_FLOOD` | Mode 2 | Rapid burst flooding | 150–350 ms | ~4 pkt/s | `netguard/attacker` |
| `REPLAY_ATTACK` | Mode 3 | Frozen sequence numbers replayed | 800–1500 ms | ~1 pkt/s | `netguard/attacker` |
| `SLOW_RATE_ATTACK` | Mode 4 | Ghost packets to evade detection | 15–30 seconds | ~0.05 pkt/s | `netguard/attacker` |
| `DATA_POISON` | Mode 5 | Spoofs DHT node with poisoned data | 2–5 seconds | ~0.3 pkt/s | `netguard/device1` |
| `TOPIC_BOMB` | Mode 6 | Floods broker with random topics | 50–100 ms | ~15 pkt/s | `netguard/junk_X` |
| `EVASION_ATTACK` | Mode 7 | Evasion flood with randomized delays | Staggered | ~4 pkt/s | `netguard/attacker` |

---

## Machine Learning Pipeline

### Data Collection (`real_time_collector/real_time_collector.py`)

A live MQTT subscriber that records all packets from the three nodes into a labelled CSV file. Supports auto-labelling from the attacker node's payload mode field.

**Running the collector:**
```bash
cd real_time_collector
python real_time_collector.py
```

The collector runs interactively with a live terminal dashboard showing:
- Packets logged per device
- Current frequency per device
- Label mode (AUTO from attacker payload)
- Session elapsed time

**Output:** `collected_datasets/telemetry_session_YYYYMMDD_HHMMSS.csv`

### Feature Engineering

The ML model does not train on raw packet fields. Instead, it operates on a **10-second sliding window** over attacker packets, computing 10 statistical features:

| Feature | Description | Key For |
|---|---|---|
| `packet_count` | Total packets in 10s window | All classes |
| `packet_rate` | Packets per second | DOS detection |
| `mean_inter_arrival_ms` | Average gap between packets | DoS vs Slow Rate |
| `std_inter_arrival_ms` | Variance in packet timing | Automated script detection |
| `min_inter_arrival_ms` | Fastest packet gap | DoS flood signature |
| `max_inter_arrival_ms` | Slowest packet gap | Slow Rate signature |
| `duplicate_ratio` | Fraction of repeated sequence numbers | Replay Attack |
| `seq_increment_mean` | Average sequence number delta | Replay (frozen = 0) |
| `seq_increment_std` | Variance in sequence increments | Consistency check |
| `unique_modes` | Distinct modes in window | Mode switching detection |

**Single-packet window handling:** When the window contains only one packet (as in Slow Rate Attack where packets arrive every 15–30 seconds), the IAT is set to the full window duration (10,000 ms) — this is the distinguishing signature that allows the model to correctly classify Slow Rate even with sparse data.

### Model Training (`ml_model/train_model.py`)

Trains a 200-tree Random Forest Classifier on windowed feature vectors from the collected CSV.

```bash
cd ml_model
python train_model.py
```

**Training pipeline:**
1. Load raw CSV from `real_time_collector/collected_datasets/`
2. Fix labels — only `esp32_3` (attacker node) can have attack labels; sensor nodes are always NORMAL
3. Build 10-second sliding windows with 5-second stride
4. 80/20 stratified train/test split
5. Train RandomForestClassifier with 200 trees
6. Evaluate and print classification report
7. Save model to `ml_model/netguard_model.pkl`

### Data Augmentation (`ml_model/augment_and_train.py`)

Because Slow Rate Attack sends only one packet every 15–30 seconds, the raw dataset rarely contains enough windowed samples for this class. This script generates 200 synthetic Slow Rate packets with statistically matching characteristics (IAT = 15–35s, incrementing sequence numbers), merges them with the real dataset, and retrains the model.

```bash
cd ml_model
python augment_and_train.py
```

### Model Performance

**Overall Accuracy: 95.32%** across 4 classes

| Class | Precision | Recall | F1 Score | Key Features |
|---|---|---|---|---|
| NORMAL | 98% | 93% | 96% | Low rate, regular IAT |
| DOS_FLOOD | 100% | 83% | 91% | High packet_rate, low IAT |
| REPLAY_ATTACK | 94% | 94% | 94% | High duplicate_ratio, frozen seq |
| SLOW_RATE_ATTACK | 91% | 100% | 96% | Very low rate, huge IAT |

*Note: The Attacker Node has been upgraded to support three additional advanced attacks (Data Poisoning, Topic Bombing, and Adversarial Evasion), allowing collection of new datasets and model expansion to 7 classes.*

**Top model-learned features (global importance):**
1. `duplicate_ratio` — Primary indicator for Replay Attacks (frozen seq numbers)
2. `mean_inter_arrival_ms` — Distinguishes DoS flood from normal timing
3. `packet_rate` — Identifies high-intensity burst attacks
4. `packet_count` — Total volume in window
5. `min_inter_arrival_ms` — Minimum gap (catches flood signatures)

---

## Backend (`dashboard/backend/main.py`)

A FastAPI application that bridges MQTT → WebSocket and runs the ML inference loop.

### MQTT → WebSocket Bridge

Subscribes to all `netguard/#` topics. On each incoming packet:
- Parses JSON payload
- Appends to a rolling log of the last 20 messages
- Buffers attacker packets for the ML inference window
- Broadcasts structured JSON to all connected WebSocket clients

### ML Inference Loop

Runs every **5 seconds** as an async task:

1. Takes the last 10 seconds of attacker packets from `packet_buffer`
2. Calls `extract_features()` to compute the 10-feature vector
3. Runs `model.predict()` and `model.predict_proba()` on the feature vector
4. Computes **SHAP values** using `shap.TreeExplainer` for the predicted class
5. Updates `latest_inference` dict and broadcasts via WebSocket as `netguard/inference`

**Single-packet window note:** If only one attacker packet is in the window (Slow Rate scenario), `extract_features()` uses the full window duration as the IAT — exactly matching the augmented training data.

### SHAP Explainability

Every inference cycle produces per-feature SHAP values for the predicted class:

```python
EXPLAINER = shap.TreeExplainer(model)
sv = EXPLAINER.shap_values(X)
# Returns signed importance weights for each of the 10 features
# Positive = pushed toward attack classification
# Negative = pushed toward normal classification
```

SHAP values are included in every `netguard/inference` WebSocket message as a sorted list from most to least influential.

### Alert Publisher

When the model detects an attack (`isAttack = True`):
- Publishes to `netguard/alerts` via MQTT
- **30-second cooldown** prevents buzzer spam during sustained attacks
- Payload includes attack type and confidence level
- ESP32_1 receives this and triggers LED + buzzer

### Auto-Generated Incident Narrative

When an attack is detected, a background async task generates a 3-sentence human-readable SOC report:
1. Formats SHAP values + live features into a structured prompt
2. Calls **Groq (Llama 3.3 70B)** → **Gemini Flash** → **deterministic fallback** in order
3. Broadcasts the narrative as `netguard/incident` WebSocket topic
4. **60-second cooldown** — generates at most once per minute

**Example generated narrative:**
> *"A DOS FLOOD attack was detected at 14:32:11 IST with 97.3% model confidence. The primary driver was packet_rate=8.2 pkt/s (SHAP: +0.68), which is 27× above the normal baseline of 0.3 pkt/s, supported by a collapsed mean_inter_arrival_ms of 245ms (SHAP: +0.52). Recommend isolating the attacker node immediately and monitoring for follow-up Replay or Slow Rate probing activity."*

### RAG AI Security Analyst (`dashboard/backend/rag.py`)

A Retrieval-Augmented Generation chatbot that answers natural language questions about the live network state. The context injected into every query includes:
- **Knowledge base** — Feature descriptions, attack signatures, device roles
- **Last 50 MQTT log entries** — Real-time traffic context
- **Latest ML inference output** — Current label, confidence, SHAP values, feature readings

**LLM fallback chain:**
```
Groq API Key 1 (Llama 3.3 70B Versatile)
    ↓ (rate limited or unavailable)
Groq API Key 2 (same models, different quota)
    ↓ (both unavailable)
Gemini Flash (if GEMINI_API_KEY set in .env)
    ↓ (all LLMs offline)
Local Expert System (rule-based, always works)
```

The local expert system has hardcoded logic for the most common question types (threat analysis, sensor readings, feature explanations) and produces structured markdown responses even without any internet connection.

### API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `WS` | `/ws/live` | WebSocket stream — receives all live data |
| `POST` | `/chat` | AI Analyst chatbot query |
| `POST` | `/simulate` | Inject synthetic attack packets for demo |
| `POST` | `/attacker/mode` | Send mode command to ESP32_3 via MQTT |
| `GET` | `/incident` | Latest auto-generated incident narrative |
| `GET` | `/feature-importance` | Global model feature importances |
| `GET` | `/health` | Backend health check |
| `GET` | `/debug` | Last 20 MQTT messages + latest inference |

### IST Time Synchronization

The backend publishes IST timestamps to `netguard/timesync` every 5 minutes. ESP32 nodes use this to align their sensor readings to the correct local time, enabling accurate day/night light curves and seasonal temperature patterns.

---

## Frontend Dashboard (`dashboard/frontend/`)

A Next.js 16 + React 19 dashboard with four tabs, all fed from a single persistent WebSocket connection managed by the `useLiveData` hook.

### Data Hook (`app/hooks/useLiveData.ts`)

The single source of truth for all live data. Maintains:
- **`nodes`** — Per-device state (telemetry, online status, packet rate, trust score)
- **`packets`** — Rolling feed of last 120 MQTT packets
- **`alerts`** — Alert log with severity classification
- **`temporal`** — 60-point anomaly score time series
- **`sensorTemporal`** — 80-point sensor history for analytics charts
- **`ml`** — Current ML classification, confidence, SHAP values
- **`incident`** — Latest RAG-generated incident narrative
- **`wsReady`** — WebSocket connection status

Auto-reconnects with 3-second retry on disconnect.

---

### Tab 1: Live Sensor Analytics (Default)

Real-time scrolling charts of environmental sensor data from the physical hardware.

**Three Recharts area charts:**
- 🌡️ **Temperature** — DHT11 reading from ESP32_1, red gradient, auto-scaling Y axis
- 💧 **Humidity** — DHT11 reading from ESP32_1, blue gradient, 60% reference line
- ☀️ **Light Intensity** — LDR reading from ESP32_2, amber gradient, LUX scale

Each chart shows the last 80 readings and updates in real time as packets arrive. Summary KPI cards above each chart show the latest reading and session average.

A **Node Status strip** shows whether ESP32_1 (DHT11) and ESP32_2 (LDR) are online. The attacker node is deliberately excluded — this tab focuses purely on legitimate sensor telemetry.

---

### Tab 2: Network Overview

The main SOC dashboard view.

#### KPI Row
Four at-a-glance metrics:
- **Total Packets** — All packets received since session start
- **Active Alerts** — Count of detected attack events in this session
- **Anomaly Score** — Current ML confidence that traffic is malicious (0–100%)
- **Nodes Online** — Count of active ESP32 nodes

#### Demo Mode Bar
A control strip for offline demonstrations. Four buttons inject synthetic packets that match each attack class's statistical signature. The ML model detects and classifies them within 5 seconds. A pulsing `SIMULATING` badge shows while demo mode is active.

#### Device Status Cards
One card per ESP32 node showing:
- Online/offline status (greyed out if no packet in last 15s)
- Latest sensor readings or attack mode
- Packet rate
- Trust score (degrades when attack detected)
- Last seen timestamp

#### Temporal Anomaly Graph (SVG)
A scrolling line graph of the ML model's anomaly score over the last 60 inference cycles. Above 70% = red zone, 30–70% = amber, below 30% = green. Shows the security posture of the network over time.

#### Packet Rate Graph (SVG)
Per-node packet frequency over time. Three color-coded lines for ESP32_1, ESP32_2, and ESP32_3.

#### Live Packet Feed
A real-time scrolling log of every MQTT packet received, with device, timestamp, and label color coding. Pauses automatically when hovered for readability.

#### ML Detection Panel
Shows the current model output:
- Classification label with color-coded badge (green = NORMAL, red = attack)
- Confidence percentage with animated bar
- Live feature readout (packet rate, mean IAT, duplicate ratio, sequence gap)
- **SHAP Force Plot** — Horizontal bars for the top 5 features with signed importance weights. Red bars push toward attack; green bars push toward normal. Raw feature values shown alongside each bar.

#### AI Incident Report
Appears automatically when an attack is detected. Shows the RAG-generated 3-sentence narrative with:
- Attack type color coding
- Pulsing `AUTO-GENERATED · SHAP-GROUNDED · RAG ANALYST` badge
- Timestamp of detection

#### Global Feature Importance Chart
A static ranked bar chart loaded from `/feature-importance` on page load. Shows which of the 10 features the Random Forest model relies on globally across all 4 attack classes, with color coding by signal type (duplicate, sequence, rate, timing).

#### Device Heatmap
A visual health grid for all three nodes with color intensity based on trust score, packet rate, and current anomaly state.

#### Alert Log
A scrolling log of all attack detections in the current session, with severity badges (CRITICAL / HIGH / MEDIUM), timestamps, and raw feature readings at time of detection.

---

### Tab 3: Network Topology

An interactive SVG network map showing all nodes connected to the MQTT broker.

- **Nodes** pulse with a glow when active and sending packets
- **Animated packet dots** flow along the connection edges in real time
- **Color coding** — ESP32_3 turns red when an attack is detected
- **Side panel** — Click any node to see its live telemetry, current classification, and top SHAP drivers
- **Connection lines** show latency and packet flow direction
- **Tab State Persistence** — Attack simulation selection is lifted to the page-level (`page.tsx`) so that changing tabs does not reset the attack animations.
- **Global Warning Badge** — A red status pill `⚠ <ATTACK> ACTIVE` is displayed in the page title row on all tabs when an attack is active.

---

### Tab 4: AI Security Analyst

A split-panel SOC chatbot interface.

**Left pane — System Context:**
Live context injected into every query:
- Current ML classification and confidence
- Whether an attack is active
- Latest feature readings (packet rate, IAT, duplicate ratio)
- Top 3 SHAP drivers
- IST timestamp

**Right pane — Chat interface:**
Type any natural language security question. Examples:
- *"Why is the network flagged as suspicious right now?"*
- *"Explain the active threat and its SHAP features."*
- *"What are the current temperature and humidity readings?"*
- *"What features does the Random Forest model evaluate?"*
- *"How does a Replay Attack differ from a DoS Flood?"*

Responses are formatted in markdown with headers, code blocks, and bullet points.

---

## Explainable AI (XAI) Stack

NetGuard AI implements three layers of explainability:

### Layer 1 — Local SHAP (Per-Inference)
Every 5-second inference cycle produces signed SHAP importance weights for all 10 features. These explain *why this specific packet window was classified as this specific attack type*. Visualized as a force plot with red (toward attack) and green (toward normal) bars.

### Layer 2 — Global Feature Importance
Computed once from `model.feature_importances_` across all 200 trees and all training samples. Shows which features the model relies on *in general* across all attack classes. Displayed as a ranked bar chart in the Overview tab.

### Layer 3 — Natural Language Narrative (RAG)
When an attack is detected, the backend automatically generates a human-readable 3-sentence SOC report grounded in the SHAP values and live feature readings. Uses Groq's Llama 3.3 70B with a SHAP-aware prompt, falling back to deterministic rules if the LLM is unavailable.

---

## Alert Flow

```
ML inference detects attack (every 5 seconds)
           │
           ├── WebSocket broadcast: netguard/inference
           │     ↳ Dashboard updates ML panel, anomaly graph, alert log
           │
           ├── MQTT publish: netguard/alerts (30s cooldown)
           │     ↳ ESP32_1 receives → LED flashes red + buzzer sounds 5s
           │
           └── RAG narrative generation (60s cooldown, async)
                 ↳ Groq/Gemini generates 3-sentence incident report
                 ↳ WebSocket broadcast: netguard/incident
                 ↳ IncidentReport card appears in dashboard
```

---

## Quick Start

### Prerequisites

```bash
# Python dependencies
pip install fastapi uvicorn paho-mqtt scikit-learn numpy joblib shap requests

# Optional (for AI chatbot LLM responses)
pip install google-generativeai

# Frontend
npm install   # inside dashboard/frontend/
```

### Configuration

Create `dashboard/backend/.env`:
```env
GROQ_API_KEY_1=gsk_your_first_groq_key_here
GROQ_API_KEY_2=gsk_your_second_groq_key_here
GEMINI_API_KEY=AIza_your_gemini_key_here    # optional
```

Get a free Groq API key at [console.groq.com](https://console.groq.com) — the free tier (14,400 requests/day) is sufficient for all demo and lab use.

### Start Backend

```bash
cd dashboard/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Watch for:
```
[ML] Model loaded from ...netguard_model.pkl
[ML] Classes: ['DOS_FLOOD' 'NORMAL' 'REPLAY_ATTACK' 'SLOW_RATE_ATTACK']
[MQTT] Connected rc=0
[ML] Inference loop started
```

### Start Frontend

```bash
cd dashboard/frontend
npm run dev
```

Open **http://localhost:3000**

### Flash Arduino Code

1. Open each sketch in Arduino IDE
2. Replace `YOUR_WIFI_SSID` and `YOUR_WIFI_PASSWORD` with your hotspot credentials
3. Install libraries: `PubSubClient`, `ArduinoJson`, `DHT sensor library`
4. Flash to the corresponding ESP32 board

---

## Retraining the Model

If you collect new data or want to retrain from scratch:

```bash
# Collect new data (run while operating ESP32 nodes)
cd real_time_collector
python real_time_collector.py

# Train on collected data
cd ml_model
python train_model.py

# Or: augment + train (adds synthetic Slow Rate data)
python augment_and_train.py
```

The new `netguard_model.pkl` is automatically loaded by the backend on next startup.

---

## Project Structure

```
NetGuard-AI/
│
├── arduino_codes/                    # Real Arduino sketches (.ino)
│   ├── netguard-dht/
│   │   └── netguard-dht.ino          # ESP32_1 — DHT11 + alert subscriber
│   ├── netguard-ldr/
│   │   └── netguard-ldr.ino          # ESP32_2 — LDR light sensor
│   └── netguard-attacker/
│       └── netguard-attacker.ino     # ESP32_3 — Attack simulator (button-controlled)
│
├── dashboard/
│   ├── backend/
│   │   ├── main.py                   # FastAPI + MQTT bridge + ML inference + alerts
│   │   ├── rag.py                    # RAG chatbot (Groq / Gemini / Expert fallback)
│   │   ├── node_simulator.py         # Offline demo node simulator
│   │   └── .env                      # API keys (gitignored — never committed)
│   │
│   └── frontend/
│       └── app/
│           ├── page.tsx              # Main 4-tab SOC dashboard
│           ├── globals.css           # Full design system (CSS variables + all styles)
│           ├── layout.tsx            # Root layout + metadata
│           ├── components/
│           │   ├── AnalyticsTab.tsx  # Live sensor charts (Recharts)
│           │   ├── GlobalImportanceChart.tsx  # Model feature importance bar chart
│           │   ├── IncidentReport.tsx         # RAG-generated incident narrative card
│           │   ├── Graphs.tsx        # SVG anomaly + packet rate graphs
│           │   ├── Panels.tsx        # ML panel, alert log, heatmap, packet feed, KPI
│           │   └── TopologyTab.tsx   # SVG network topology map
│           └── hooks/
│               └── useLiveData.ts    # WebSocket state manager (single source of truth)
│
├── ml_model/
│   ├── train_model.py                # Full retraining script (10-feature windowed schema)
│   ├── augment_and_train.py          # Data augmentation + retrain (all 4 classes)
│   └── netguard_model.pkl            # Trained model (95.32% accuracy, 4 classes)
│
├── real_time_collector/
│   ├── real_time_collector.py        # Live MQTT → labelled CSV data collector
│   ├── extractor.py                  # Feature extraction utilities
│   ├── config.json                   # Collector configuration
│   ├── README.md                     # Collector usage guide
│   └── collected_datasets/
│       └── telemetry_session_*.csv   # Raw training data from hardware
│
├── hardware-simulation/              # PlatformIO Wokwi simulation projects
│   ├── NetGuard_DHT_Node/            # Wokwi ESP32 DHT simulation
│   ├── NetGuard_LDR_Node/            # Wokwi ESP32 LDR simulation
│   └── NetGuard_Attacker_Node/       # Wokwi ESP32 attacker simulation
│
├── index.html                        # Phase 1 simulation (GitHub Pages)
├── .gitignore
└── README.md
```

---

## Technical Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| **Frontend Framework** | Next.js | 16 | React SSR + routing |
| **UI Library** | React | 19 | Component model |
| **Charts** | Recharts | 2.13 | Sensor analytics charts |
| **Styling** | Vanilla CSS | — | Design system (CSS variables) |
| **Backend** | FastAPI | 0.115 | REST API + WebSocket |
| **ASGI Server** | Uvicorn | — | Async request handling |
| **MQTT Client** | Paho-MQTT | — | ESP32 broker communication |
| **ML Model** | scikit-learn | 1.8 | Random Forest Classifier |
| **Explainability** | SHAP | 0.51 | TreeExplainer + force plots |
| **Numerics** | NumPy | 2.4 | Feature array operations |
| **Model Persistence** | joblib | 1.5 | Model serialization |
| **AI Chatbot** | Groq API | — | Llama 3.3 70B LLM |
| **AI Fallback** | Gemini API | — | Gemini Flash LLM |
| **MQTT Broker** | HiveMQ | — | Public broker (port 1883) |
| **Hardware** | ESP32 | — | Tensilica Xtensa LX6 |
| **Firmware** | Arduino Core | — | ESP32 Arduino framework |
| **MQTT Library** | PubSubClient | 2.8 | ESP32 MQTT client |
| **JSON Library** | ArduinoJson | 7.x | ESP32 JSON parsing |
| **Sensor Library** | DHT sensor library | — | DHT11 driver |

---

## MQTT Topic Reference

| Topic | Publisher | Subscriber | Description |
|---|---|---|---|
| `netguard/device1` | ESP32_1 | Backend | Temperature + humidity telemetry |
| `netguard/device2` | ESP32_2 | Backend | Light intensity telemetry |
| `netguard/attacker` | ESP32_3 | Backend | Attack mode packets |
| `netguard/alerts` | Backend | ESP32_1 | Attack alert → LED + buzzer |
| `netguard/timesync` | Backend | All ESP32s | IST timestamp broadcast |
| `netguard/timereq` | All ESP32s | Backend | Time sync request |
| `netguard/cmd` | Backend | ESP32_3 | Mode control command |

---

## Security Notes

- WiFi credentials (`YOUR_WIFI_SSID` / `YOUR_WIFI_PASSWORD`) in Arduino sketches are placeholders — replace before flashing
- API keys go in `dashboard/backend/.env` which is gitignored and never committed
- The MQTT broker (`broker.hivemq.com`) is a public broker — suitable for lab use, not production
- No TLS/authentication on MQTT (public broker limitation) — for production, use a private broker with client certificates

---

*NetGuard AI — IoT Security Operations Center — Semester IV EL — 2025–26*
