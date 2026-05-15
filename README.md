<h1 align="center">NetGuard AI: Behavioral IoT Intrusion Detection System</h1>

<p align="center">
  <strong>A comprehensive Machine Learning Intrusion Detection System (IDS) that identifies DoS, Replay, and ultra-stealthy Slow-Rate attacks in IoT environments using behavioral network signatures.</strong>
</p>

---

## 🌟 Executive Summary
NetGuard AI transcends traditional packet-inspection security by analyzing the **behavior and cadence** of IoT devices. Instead of looking at payloads (which are often encrypted), NetGuard AI monitors timing variance, sequence anomalies, and traffic density over a 60-second sliding window. 

The project features a full **Hardware Simulation Layer** (via Wokwi), a mathematically calibrated **Threat Simulator**, and a **Random Forest AI Core** that achieved a **99.20% classification accuracy** on a highly chaotic, realistic dataset.

---

## 🏗️ Project Architecture

The repository is divided into distinct operational layers:

### 1. Phase 1 Simulation (`Phase 1 Simulation/`)
The foundational prototype of the project. It features a standalone, web-based (HTML/JS) network visualization to prove the underlying concepts of packet sniffing and anomaly detection before moving to physical/simulated hardware.

### 2. Hardware Simulation Layer (`hardware-simulation/`)
Because physical ESP32 boards were not used, this layer relies on the **Wokwi Simulator** and **PlatformIO** to virtualize identical hardware conditions. These nodes communicate over the public internet using the MQTT protocol via `broker.hivemq.com`.

*   **NetGuard_DHT_Node:** Legitimate environmental sensor. It runs a **Diurnal Cycle Engine** (a sine-wave simulator) that realistically fluctuates temperature and humidity based on an accelerated 24-hour day/night cycle. It also acts as the network actuator (flashing LEDs/Buzzer on alert).
*   **NetGuard_LDR_Node:** Legitimate light sensor running a mathematically simulated dawn-to-dusk light curve.
*   **NetGuard_Attacker_Node:** A Wokwi C++ node capable of mimicking the Python attacker script, allowing hardware-only simulation of network intrusions.

### 3. AI & Data Core (`mqtt_collector/`)
The Python-based brain of the operation. This layer handles telemetry, feature engineering, and AI training.

---

## 🥷 Threat Model & The "Time Warp" Calibration
To ensure the AI is ready for real-world deployment, the network traffic is artificially injected with **Stochastic Jitter** (random timing noise ±3s) and packet loss (3%). The attacker operates in 4 distinct modes:

1.  **NORMAL (Stealth Mode):** The attacker perfectly mimics the 5-second interval of the legitimate DHT/LDR sensors. *Goal: Hide in plain sight.*
2.  **DOS_FLOOD:** Rapid-fire bursts of 0.15s - 0.35s. *Goal: Resource exhaustion.*
3.  **REPLAY_ATTACK:** Captures a valid sequence number and repeats the packet every 0.8s - 1.5s. *Goal: Bypass authentication.*
4.  **SLOW_RATE_ATTACK (The Ghost):** Sends packets every 15s - 30s. *Goal: Keep a malicious session alive while being too slow to trigger standard IDS volume thresholds.*

---

## 🧠 Machine Learning Pipeline & Results

Raw MQTT packets are captured by `collector.py` and aggregated by `feature_extractor.py` using a **60-second sliding window with a 10-second step**. 

### Extracted Behavioral Features:
*   `packet_rate` & `packet_count`
*   `mean_inter_arrival_ms` & `std_inter_arrival_ms`
*   `duplicate_ratio` (Primary Replay indicator)
*   `seq_increment_mean`

### Training Results (Random Forest Classifier):
The model (`netguard_model.pkl`) was trained on **1,884 behavioral windows** (derived from 5,005 raw packets). It utilizes `max_depth=10` to prevent overfitting.

*   **Overall Accuracy:** `99.20%`
*   **Cross-Validation:** 5-Fold Stratified CV confirmed a variance of only `±0.34%`. 
*   **Train-Test Gap:** Only `0.80%` (Proving excellent generalization with zero data leakage).

#### Class-Specific Detection:
*   ✅ **LEGITIMATE (100%):** Immune to environmental changes; the AI learned to ignore sensor values and focus purely on timing signatures.
*   ✅ **DOS_FLOOD (100%):** Caught instantly via traffic density spikes.
*   ✅ **REPLAY_ATTACK (100%):** Caught instantly via the `duplicate_ratio` feature.
*   ✅ **SLOW_RATE_ATTACK (89% F1-Score):** Successfully isolated "ghost" packets from standard network idle time.

---

## 🚀 Quick Start Guide

### Step 1: Run the Hardware Simulation
1. Install the **Wokwi Extension** in VS Code.
2. Open `hardware-simulation/NetGuard_DHT_Node/diagram.json` and start the simulation.
3. Repeat for the LDR node. They will automatically connect to HiveMQ.

### Step 2: Run the AI Data Pipeline
1. Navigate to the `mqtt_collector/` directory:
   ```bash
   cd mqtt_collector
   ```
2. Install Python dependencies:
   ```bash
   pip install paho-mqtt pandas scikit-learn matplotlib seaborn
   ```
3. Start capturing data:
   ```bash
   python collector.py
   ```
4. Start the autonomous attacker in a separate terminal:
   ```bash
   python attacker_simulator.py
   ```
5. Once you have collected sufficient traffic, generate features:
   ```bash
   python feature_extractor.py --window 60 --step 10
   ```
6. Train the AI model and generate validation plots:
   ```bash
   python trainer.py
   ```

---
*Developed for IoT Security Research. Powered by ESP32, MQTT, and Scikit-Learn.*
