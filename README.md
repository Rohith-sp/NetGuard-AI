# NetGuard AI — IoT Intrusion Detection System

> Real-time network intrusion detection for ESP32 IoT nodes using Random Forest ML, MQTT telemetry, live SHAP explainability, and a Next.js SOC dashboard.

---

## System Architecture

```
ESP32_1 (DHT11)    ─┐                              ┌─► WebSocket → Next.js Dashboard (port 3000)
ESP32_2 (LDR)      ─┼──► broker.hivemq.com:1883 ──┤
ESP32_3 (Attacker) ─┘       (netguard/#)           └─► FastAPI Backend (port 8000)
                                                               │
                                              ┌────────────────┼────────────────────┐
                                              │                │                    │
                                     Random Forest ML    SHAP Explainer      MQTT Alert Publisher
                                     (netguard_model.pkl)  (per inference)   → netguard/alerts
                                     95.32% accuracy                          → ESP32 buzzer/LED
                                     Inference every 5s
```

---

## Hardware Nodes

| Node | Hardware | MQTT Topic | Role |
|---|---|---|---|
| ESP32_1 | DHT11 sensor | `netguard/device1` | Temperature & Humidity telemetry |
| ESP32_2 | LDR sensor | `netguard/device2` | Ambient light intensity telemetry |
| ESP32_3 | Bare ESP32 | `netguard/attacker` | Simulates network attacks + receives alerts |

ESP32_3 cycles through four attack modes via a physical push button:
- **NORMAL** — Legitimate traffic, ~2–5s intervals
- **DOS_FLOOD** — Rapid fire packets, 0.15–0.35s intervals
- **REPLAY_ATTACK** — Frozen sequence numbers, repeated packets
- **SLOW_RATE_ATTACK** — Ghost packets every 15–30s to evade detection

When the ML model detects an attack, it publishes to `netguard/alerts`. ESP32_1 is subscribed and responds with a red LED flash + buzzer alert.

---

## Machine Learning Pipeline

### Model
- **Algorithm**: Random Forest Classifier (200 trees, scikit-learn)
- **Accuracy**: **95.32%** across 4 classes
- **Training data**: Real hardware telemetry from ESP32 nodes (4,256 packets) + synthetic augmentation for SLOW_RATE_ATTACK class

### Attack Class Performance
| Class | Precision | Recall | F1 |
|---|---|---|---|
| NORMAL | 98% | 93% | 96% |
| DOS_FLOOD | 100% | 83% | 91% |
| REPLAY_ATTACK | 94% | 94% | 94% |
| SLOW_RATE_ATTACK | 91% | **100%** | 96% |

### Feature Engineering
Inference uses a 10-second sliding window over `netguard/attacker` packets, extracting 10 features:

| Feature | Description |
|---|---|
| `packet_count` | Total packets in 10s window |
| `packet_rate` | Packets per second |
| `mean_inter_arrival_ms` | Average time between packets |
| `std_inter_arrival_ms` | Variance in packet timing |
| `min_inter_arrival_ms` | Fastest packet gap |
| `max_inter_arrival_ms` | Slowest packet gap |
| `duplicate_ratio` | Fraction of repeated sequence numbers |
| `seq_increment_mean` | Average sequence number delta |
| `seq_increment_std` | Variance in sequence increments |
| `unique_modes` | Number of distinct modes in window |

**Top drivers learned by the model:**
1. `duplicate_ratio` — 18.6% (detects Replay Attacks via frozen seq numbers)
2. `mean_inter_arrival_ms` — 17.2% (distinguishes DoS flood from normal)
3. `packet_rate` — 15.9% (flood detection)

### Training Files
| File | Purpose |
|---|---|
| `ml_model/train_model.py` | Full retraining from raw CSV using 10-feature windowed schema |
| `ml_model/augment_and_train.py` | Data augmentation for SLOW_RATE + retrain |
| `ml_model/netguard_model.pkl` | Trained model loaded by backend at startup |
| `real_time_collector/real_time_collector.py` | Live MQTT → labelled CSV collector |
| `real_time_collector/collected_datasets/` | Raw training datasets |

---

## Core Dashboard Features

### 📊 Live Sensor Analytics (Default Tab)
Real-time scrolling line charts (via Recharts) for all sensor readings from physical hardware:
- 🌡️ **Temperature** — DHT11 reading from ESP32_1
- 💧 **Humidity** — DHT11 reading from ESP32_1
- ☀️ **Light Intensity** — LDR reading from ESP32_2

Charts update in real-time via WebSocket with session averages and live KPI summary cards.

### 🛡️ Network Overview
- **KPI Row** — Total packets, active alerts, anomaly score, nodes online
- **Node Status Cards** — Live per-node telemetry, trust scores, and online status
- **Temporal Anomaly Graph** — Scrolling line graph of ML threat scores over time
- **Packet Rate Graph** — Per-node packet frequency visualization
- **Live Packet Feed** — Real-time scroll of every MQTT packet received
- **ML Detection Panel** — Current classification label, confidence bar, SHAP feature breakdown
- **Device Heatmap** — Visual health grid per node

### 🕸️ Network Topology
- Interactive SVG topology showing all 3 nodes connected to the MQTT broker
- Live animated packet dots flowing along edges
- Attack state visualization with red glow on ESP32_3 when threat detected

### 🤖 AI Analyst
- RAG-powered chatbot (Groq Llama / Gemini fallback)
- Answers natural language questions about the live network state
- Provides explanations of SHAP feature values and attack classifications

---

## Alert Flow

```
ML model detects attack (every 5s inference cycle)
       ↓
FastAPI backend publishes to netguard/alerts
  Payload: { "source": "NetGuard-AI", "type": "ATTACK_DETECTED",
             "label": "DOS_FLOOD", "confidence": 97.3 }
       ↓
ESP32_1 (DHT11 node) receives alert
       ↓
Red LED flashes + Buzzer sounds for 5 seconds
       ↓
Alert also shown in dashboard (Alert Log + blinking pill)
```

30-second cooldown prevents buzzer spam during sustained attacks.

---

## Quick Start

### Prerequisites
```bash
pip install fastapi uvicorn paho-mqtt scikit-learn numpy joblib shap
```

### Start Backend
```bash
cd dashboard/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### Start Frontend
```bash
cd dashboard/frontend
npm install
npm run dev
```

Open **http://localhost:3000** in your browser.

> **Note:** Make sure your ESP32 nodes are powered and connected to your WiFi hotspot (`ROHITH`) before starting the backend. The system will show "Offline" for nodes that are not transmitting.

---

## Project Structure

```
NetGuard-AI/
├── dashboard/
│   ├── backend/
│   │   ├── main.py              # FastAPI + WebSockets + MQTT + ML Inference + Alert Publisher
│   │   ├── rag.py               # RAG Pipeline (Groq / Gemini / Expert fallback)
│   │   └── node_simulator.py    # Offline demo simulator
│   └── frontend/
│       └── app/
│           ├── page.tsx         # 4-tab SOC Dashboard
│           ├── globals.css      # Design system (CSS variables, all components)
│           ├── components/
│           │   ├── AnalyticsTab.tsx  # Recharts live sensor graphs
│           │   ├── Panels.tsx        # ML, Alert Log, Heatmap, Packet Feed
│           │   ├── Graphs.tsx        # SVG Anomaly & Packet Rate graphs
│           │   └── TopologyTab.tsx   # SVG Network Topology
│           └── hooks/
│               └── useLiveData.ts   # WebSocket state manager + sensor time-series
├── hardware-simulation/
│   ├── NetGuard_DHT_Node/       # ESP32_1 firmware (DHT11 + alert subscriber)
│   ├── NetGuard_LDR_Node/       # ESP32_2 firmware (LDR sensor)
│   └── NetGuard_Attacker_Node/  # ESP32_3 firmware (attack simulator + button)
├── ml_model/
│   ├── train_model.py           # Retraining script (10-feature windowed schema)
│   ├── augment_and_train.py     # Data augmentation + retrain (all 4 classes)
│   └── netguard_model.pkl       # Trained Random Forest (95.32% accuracy, 4 classes)
└── real_time_collector/
    ├── real_time_collector.py   # Live MQTT → labelled CSV data collector
    └── collected_datasets/      # Raw training datasets from hardware
```

---

## Technical Stack

| Layer | Technologies |
|---|---|
| **Frontend** | Next.js 16, React 19, Recharts 2.x, Vanilla CSS |
| **Backend** | FastAPI, Uvicorn, WebSockets, Paho-MQTT |
| **Machine Learning** | scikit-learn (Random Forest), SHAP, NumPy, joblib |
| **AI Analyst** | Groq (Llama 3.3 / Llama 3.1), Gemini Flash (fallback) |
| **Broker** | HiveMQ Public Broker (broker.hivemq.com:1883) |
| **Hardware** | ESP32, DHT11, LDR, PlatformIO, PubSubClient, ArduinoJson |

---

*NetGuard AI — IoT Security Operations Center — Semester IV EL — 2025–26*
