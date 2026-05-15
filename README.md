# NetGuard AI: IoT Intrusion Detection System

NetGuard AI is a comprehensive, machine-learning-powered Intrusion Detection System (IDS) designed for IoT environments. It utilizes behavioral analysis to detect sophisticated network attacks such as DoS Floods, Replay Attacks, and ultra-stealthy Slow-Rate attacks over the MQTT protocol.

## 🌟 Project Architecture

This project is divided into two primary layers:

### 1. Hardware Simulation (`hardware-simulation/`)
Simulated ESP32 IoT nodes using the Wokwi simulator. These nodes generate the realistic network traffic (both legitimate and malicious).
*   **NetGuard_DHT_Node**: Legitimate environmental sensor with a dynamic diurnal cycle. Acts as the network actuator (Buzzer/LED alerts).
*   **NetGuard_LDR_Node**: Legitimate light sensor with a realistic day/night curve.
*   **NetGuard_Attacker_Node**: Malicious node capable of executing DoS floods, Replays, and Slow-Rate stealth attacks.

### 2. IDS Core (`mqtt_collector/`)
The Python-based brain of the operation. This layer collects telemetry, engineers behavioral features, and trains the AI model.
*   `collector.py`: Listens to MQTT traffic and logs raw telemetry.
*   `attacker_simulator.py`: A Python implementation of the attacker for rapid dataset generation (includes stochastic jitter).
*   `feature_extractor.py`: Converts raw packets into 60-second sliding behavioral windows.
*   `trainer.py`: Trains a Random Forest Classifier and generates Kaggle-style validation plots.
*   `DATASETS.md`: A comprehensive analysis of the generated ML dataset.

---

## 🚀 Quick Start

### Step 1: Hardware Simulation
1. Open the folders inside `hardware-simulation/` using VS Code and the Wokwi extension.
2. Ensure you have the `DHTesp` and `PubSubClient` libraries installed in your `platformio.ini`.
3. Start the Wokwi simulation for the nodes. They will automatically connect to `broker.hivemq.com` and begin publishing data.

### Step 2: Data Collection & Training
1. Navigate to the `mqtt_collector/` directory.
2. Install dependencies:
   ```bash
   pip install paho-mqtt pandas scikit-learn matplotlib seaborn
   ```
3. Run `python collector.py` to start capturing network traffic.
4. (Optional) Run `python attacker_simulator.py` to generate rapid, high-fidelity attack traffic.
5. Once sufficient data is collected, extract features:
   ```bash
   python feature_extractor.py --window 60 --step 10
   ```
6. Train the AI model:
   ```bash
   python trainer.py
   ```

---

## 📊 AI Performance
The current Random Forest model achieves **99.20% accuracy** on the dataset. It is highly resistant to overfitting, validated via 5-Fold Cross Validation.

*   **Legitimate Nodes:** 100% Detection
*   **DoS Floods:** 100% Detection
*   **Replay Attacks:** 100% Detection
*   **Slow-Rate (Stealth):** 89% Detection (F1-Score)

---

## 🛡️ License
MIT License. See `LICENSE` for more information.
