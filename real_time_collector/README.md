# NetGuard AI — Real-time Telemetry Collection Pipeline

This folder contains the complete toolchain required to perform **real-time hardware data collection, labeling, and feature extraction** once you have assembled your physical ESP32 circuit boards.

---

## Architecture Overview

```
[Physical ESP32 Nodes] 
  - Node 1: DHT22 (netguard/device1)
  - Node 2: LDR (netguard/device2)          ──► Local or Public MQTT Broker ──► [real_time_collector.py]
  - Node 3: Pushbutton (netguard/attacker)                                         │
                                                                                   ▼
                                                                        [raw_telemetry_session.csv]
                                                                                   │
                                                                                   ▼
                                                                           [extractor.py]
                                                                                   │
                                                                                   ▼
                                                                           [features_session.csv]
                                                                                   │
                                                                                   ▼
                                                                           [Train ML Model]
```

---

## 📋 Prerequisites & Installation

1. **Install Paho MQTT**:
   Ensure you have the MQTT client library installed on your computer.
   ```bash
   pip install paho-mqtt
   ```

2. **Broker Setup**:
   - By default, the scripts are configured to use the public broker `broker.hivemq.com`.
   - **For local lab environments**, it is highly recommended to run a local broker (e.g., [Mosquitto](https://mosquitto.org/)) on your machine and update the broker IP inside `config.json` to your computer's local IP address (e.g., `192.168.1.50`).

---

## ⚙️ Configuration (`config.json`)

Configure your connection settings, topics, and device mappings in `config.json`:
- `broker`: Hostname or IP of the MQTT Broker.
- `port`: Connection port (default `1883`).
- `topics`: Match these to the topics configured in your ESP32 Arduino/PlatformIO code.

---

## 🚀 Step-by-Step Collection Pipeline

### Step 1: Start physical ESP32 nodes
Power up your ESP32 circuits. Ensure they are successfully connected to the same WiFi network and MQTT broker as your collector PC.

### Step 2: Launch the Real-Time Collector
Run the collector script to open the interactive console dashboard:
```bash
python real_time_collector.py
```

#### 🎮 Interactive Keyboard Controls:
*   **`[Spacebar]`**: Pause or Resume logging to the CSV file.
*   **`[M]` / `[A]`**: Switch between **Manual** labeling (hotkeys control the ground truth state) or **Auto** labeling (reads mode state from the attacker node payload).
*   **`[0]`**: Tag incoming data as **`NORMAL`** (Legitimate).
*   **`[1]`**: Tag incoming data as **`DOS_FLOOD`**.
*   **`[2]`**: Tag incoming data as **`REPLAY_ATTACK`**.
*   **`[3]`**: Tag incoming data as **`SLOW_RATE_ATTACK`**.
*   **`[N]`**: Reset counters and split collection into a new CSV session file.
*   **`[Q]`**: Safely disconnect and quit the collector.

All raw logs are written to the `./collected_datasets/` folder as `telemetry_session_YYYYMMDD_HHMMSS.csv`.

---

## 📊 Step 3: Extract Features

Once you have completed your collection runs, convert the raw packet list into aggregated sliding-window feature rows (which are required for the machine learning classifier model):

```bash
# Processes the latest CSV session automatically:
python extractor.py

# Or specify a target dataset manually:
python extractor.py --file collected_datasets/telemetry_session_2026xxxx_xxxxxx.csv
```

This creates a `features_telemetry_session_*.csv` file containing metrics such as *packet_rate*, *mean_inter_arrival_ms*, *duplicate_ratio*, and *seq_increment_mean*.

---

## 🧠 Step 4: Retrain the ML Model (Optional)

To train a new machine learning model (`netguard_model.pkl`) using your physical circuit features:

1. Copy the generated `features_telemetry_session_*.csv` file to the `mqtt_collector/dataset/` directory.
2. Rename or append it to the baseline `features.csv`.
3. Run the trainer script from the `mqtt_collector/` folder:
   ```bash
   python trainer.py
   ```
4. Copy the newly trained `netguard_model.pkl` to the backend directory `dashboard/backend/` to deploy your custom model to the SOC Dashboard!
