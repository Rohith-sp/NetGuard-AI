# NetGuard AI — IoT Intrusion Detection System

> Real-time network intrusion detection for ESP32 IoT nodes using Random Forest ML, MQTT telemetry, and a live Next.js SOC dashboard.

---

## System Architecture

```
ESP32_1 (DHT22)  ─┐
ESP32_2 (LDR)    ─┼──► broker.hivemq.com (MQTT) ──► FastAPI Backend ──► Next.js Dashboard
ESP32_3 (Attacker)┘         netguard/#                  port 8000         port 3000
                                                               │
                                                      Random Forest ML
                                                      (netguard_model.pkl)
                                                      Inference every 5s
                                                      + SHAP explainability
```

---

## Core Features (100% Implemented & Verified)

### 📊 Real-Time SOC Dashboard (Next.js)
- **Interactive SVG Topology Graph** — A stunning, fully scaling network connection map illustrating active hardware nodes, responsive offline detection, and custom-styled CSS/SVG packet animations.
- **Explainable AI Security Analyst (RAG Chatbot)** — A dedicated split-tab SOC chat terminal powered by Llama 3.3 via a dual-key Groq model rotation + Gemini fallback, parsing active telemetry, SHAP weights, and `DATASETS.md` to offer instantaneous natural language risk analysis.
- **Live SHAP Feature Analyzer** — Real-time horizontal bar charts displaying exactly which telemetry features (packet rate, duplicate ratio, sequence gaps) are driving the model's classifications.
- **Device Health & Heatmap Grid** — Interactive visual grid reporting live telemetry states, trust scores, and sensor metrics per node with pulsing security alerts.
- **Temporal Anomaly Graph** — A dynamic, scrolling line graph tracking the continuous threat scores emitted by the ML classifier.
- **Node Status Control Cards** — Complete remote triggers to signal, adjust, and reset simulated attacker vectors via MQTT.

### ⚙️ FastAPI Security Backend
- High-frequency MQTT client subscribing to node telemetry and bridging payload channels to browser WebSocket streams.
- Continuous ML classification evaluating a sliding telemetric window every 5 seconds.
- Multi-fallback RAG router query handler (`rag.py`) supporting live key rotations and offline rule-based expert analysis.
- Automated IST timestamp sync publications sent to active hardware nodes over `netguard/timesync`.

### 🧠 Machine Learning Engine
- **Algorithm**: Random Forest Classifier trained on customized IoT threat vectors.
- **Classifications**: `NORMAL`, `DOS_FLOOD`, `REPLAY_ATTACK`, `SLOW_RATE_ATTACK`.
- **Explainability**: Local SHAP values computed per classification cycle, exposing statistical influence weights for 10 distinct features.

---

## ⚠️ WiFi Workaround — Python Node Simulator

Wokwi's virtual WiFi network (`Wokwi-GUEST`) **does not support outbound TCP on port 1883** to public MQTT brokers. All PlatformIO code compiles perfectly, but cannot publish virtual traffic.

To enable seamless, zero-hardware local demonstrations, we built a high-fidelity **Python Node Simulator** inside the backend:
`dashboard/backend/node_simulator.py`

This simulator initializes concurrent threads that publish realistic Bangalore climate (DHT22) and daylight (LDR) curves to the broker, fully responding to dashboard command Triggers and Resets.

---

## Quick Start

```bash
# Terminal 1 — FastAPI Backend
cd dashboard/backend
python -m uvicorn main:app --port 8000

# Terminal 2 — Node Simulator
cd dashboard/backend
python node_simulator.py

# Terminal 3 — Next.js Frontend
cd dashboard/frontend
npm run dev
```

Open **http://localhost:3000** in your browser!

---

## Project Directory Tree

```
NetGuard-AI/
├── dashboard/
│   ├── backend/
│   │   ├── main.py              # FastAPI + WebSockets + MQTT Client
│   │   ├── rag.py               # RAG Pipeline (Groq / Gemini / Expert)
│   │   └── node_simulator.py    # Multi-threaded node simulation
│   └── frontend/
│       └── app/
│           ├── page.tsx         # Responsive SOC Page
│           ├── globals.css      # Core Theme & Layout styling
│           ├── components/
│           │   ├── Panels.tsx   # ML Analysis & Live Feed modules
│           │   ├── Graphs.tsx   # Realtime temporal anomaly curves
│           │   └── TopologyTab.tsx # SVG Connection Graph
│           └── hooks/
│               └── useLiveData.ts # WebSocket stream manager
├── hardware-simulation/
│   ├── NetGuard_DHT_Node/       # PlatformIO firmware (DHT22 ESP32)
│   ├── NetGuard_LDR_Node/       # PlatformIO firmware (LDR ESP32)
│   └── NetGuard_Attacker_Node/  # PlatformIO firmware (Attacker ESP32)
├── mqtt_collector/
│   ├── collector.py             # Phase 2: raw MQTT → CSV collector
│   ├── feature_extractor.py     # Sliding window feature extractor
│   ├── trainer.py               # ML training script
│   ├── netguard_model.pkl       # Trained Random Forest classifier
│   └── DATASETS.md              # Feature descriptions
├── REMAINING_WORK.txt           # Active feature status checklist
└── README.md
```

---

## Technical Stack

| Layer | Technologies |
|---|---|
| **Frontend** | Next.js 16, React 19, Recharts, Vanilla CSS |
| **Backend** | FastAPI, Uvicorn, WebSockets, Paho-MQTT |
| **Machine Learning** | scikit-learn (Random Forest), SHAP, NumPy |
| **API RAG Engines** | Groq (Llama 3.3 / Llama 3.1), Gemini (Flash) |
| **Broker** | HiveMQ (broker.hivemq.com:1883) |
| **Hardware Firmware** | PlatformIO, Arduino/ESP32 Core, PubSubClient, ArduinoJson |

---
*NetGuard AI — IoT Security Operations Center — 2025–26*
