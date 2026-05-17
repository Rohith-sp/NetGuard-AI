# NetGuard AI — IoT Intrusion Detection System

> **RV College of Engineering · CS344AI · Semester IV · 2025–26**
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

## Features

### Dashboard (Next.js)
- **Live Telemetry** — DHT22 temp/humidity, LDR light levels, packet rates
- **Temporal Anomaly Graph** — scrolling real-time anomaly score from ML model
- **Packet Rate Chart** — all 3 nodes on a multi-line graph
- **Node Status Cards** — trust score bars, online/offline, last seen
- **Live Packet Feed** — color-coded by traffic type
- **Alert Log** — CRITICAL / HIGH / MEDIUM severity events
- **Network Analyzer** — real ML inference results + SHAP feature importance
- **Attacker Control Tab** — trigger/reset attack modes via MQTT command

### Backend (FastAPI)
- MQTT → WebSocket bridge (HiveMQ → browser)
- **Real ML inference** every 5 seconds using `netguard_model.pkl`
- SHAP values computed per inference cycle (TreeExplainer)
- IST time sync published to ESP nodes via `netguard/timesync`
- Debug endpoint: `GET /debug` — last 20 MQTT messages + latest inference

### ML Pipeline
- **Model**: Random Forest Classifier (scikit-learn)
- **Classes**: `NORMAL`, `DOS_FLOOD`, `REPLAY_ATTACK`, `SLOW_RATE_ATTACK`
- **Features**: packet_rate, mean/std/min/max IAT, duplicate_ratio, seq_increment_mean/std, unique_modes
- **Window**: 10-second sliding window on live MQTT packets
- **Explainability**: SHAP TreeExplainer — shows which features drove each prediction

### Firmware (ESP32 / PlatformIO)
- `NetGuard_DHT_Node` — DHT22 temp/humidity sensor, IST-synced Bangalore climate model
- `NetGuard_LDR_Node` — LDR light sensor, Bangalore sunrise/sunset LUX curve
- `NetGuard_Attacker_Node` — controllable attack node (NORMAL / DoS / Replay / Slow-Rate)

---

## ⚠️ Wokwi Simulation Issue & Workaround

Wokwi's simulated `Wokwi-GUEST` WiFi network **does not support outbound TCP on port 1883** to external MQTT brokers. All 3 ESP32 nodes compile successfully via PlatformIO, but cannot publish data in the virtual environment.

**Workaround — Python Node Simulator:**
`dashboard/backend/node_simulator.py` replaces all 3 Wokwi simulations with Python threads that publish realistic data directly to HiveMQ over the same MQTT topics (`netguard/device1`, `netguard/device2`, `netguard/attacker`).

- DHT node: Bangalore temp/humidity based on real IST system time
- LDR node: Bangalore sunrise/sunset LUX model
- Attacker node: stays `NORMAL` until dashboard "Trigger Attack" is pressed

**With real hardware:** Stop the simulator, update WiFi credentials in each `main.cpp`, and flash with `pio run --target upload`. No other changes needed.

---

## Quick Start

```bash
# Terminal 1 — Backend
cd dashboard/backend
python -m uvicorn main:app --port 8000

# Terminal 2 — Node Simulator (replace Wokwi)
cd dashboard/backend
python node_simulator.py

# Terminal 3 — Frontend
cd dashboard/frontend
npm run dev
```

Open **http://localhost:3000**

---

## Project Structure

```
NetGuard-AI/
├── dashboard/
│   ├── backend/
│   │   ├── main.py              # FastAPI + MQTT bridge + ML inference
│   │   └── node_simulator.py    # Python replacement for Wokwi
│   └── frontend/
│       └── app/
│           ├── page.tsx         # Main dashboard layout
│           ├── globals.css      # Full design system (CSS variables)
│           ├── components/
│           │   ├── Panels.tsx   # KPI, Node cards, ML panel, Alerts, Feed
│           │   └── Graphs.tsx   # Anomaly + Packet Rate recharts
│           └── hooks/
│               └── useLiveData.ts  # WebSocket state management
├── hardware-simulation/
│   ├── NetGuard_DHT_Node/       # ESP32 DHT22 firmware (PlatformIO)
│   ├── NetGuard_LDR_Node/       # ESP32 LDR firmware (PlatformIO)
│   └── NetGuard_Attacker_Node/  # ESP32 attacker firmware (PlatformIO)
├── mqtt_collector/
│   ├── collector.py             # Phase 2: raw MQTT → CSV
│   ├── feature_extractor.py     # Sliding window feature engineering
│   ├── trainer.py               # Random Forest training pipeline
│   ├── netguard_model.pkl       # Trained model (git-ignored)
│   └── DATASETS.md              # Dataset documentation
├── Phase 1 Simulation/          # Static HTML prototype (archived)
├── REMAINING_WORK.txt           # Detailed roadmap for remaining features
└── README.md
```

---

## Hardware Requirements (Real Deployment)

| Node | Hardware | Sensor | MQTT Topic |
|------|----------|--------|------------|
| ESP32_1 | ESP32 DevKit | DHT22 | `netguard/device1` |
| ESP32_2 | ESP32 DevKit | LDR (10kΩ) | `netguard/device2` |
| ESP32_3 | ESP32 DevKit | None (attacker) | `netguard/attacker` |

---

## Remaining Work

See [`REMAINING_WORK.txt`](./REMAINING_WORK.txt) for detailed breakdown:

1. **SHAP Force Plot UI** — bar chart showing which features drove each prediction *(45 min)*
2. **Device Heatmap** — color-coded threat grid per node *(30 min)*
3. **Network Topology Tab** — animated SVG graph of node connections *(1.5 hrs)*
4. **Blynk Mobile Integration** — phone push alerts + live sensor gauges *(1 hr)*
5. **RAG Security Chatbot** — LangChain + LLM Q&A about live network state *(2 hrs)*
6. **PDF Incident Report** — one-click export of attack timeline + SHAP *(1 hr)*

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, Recharts, Vanilla CSS |
| Backend | FastAPI, Uvicorn, Paho-MQTT, WebSockets |
| ML | scikit-learn (Random Forest), SHAP, NumPy |
| Broker | HiveMQ (broker.hivemq.com:1883) |
| Firmware | Arduino / ESP32, PlatformIO, DHTesp, PubSubClient, ArduinoJson |
| Simulation | Python threading (node_simulator.py) |

---

*NetGuard AI — CS344AI IoT Security Project — RVCE 2025–26*
