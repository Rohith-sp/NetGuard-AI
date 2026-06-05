# NetGuard AI: Comprehensive Behavioral Dataset Analysis

## 1. Executive Summary
This document provides a highly detailed analysis of the **Final Hardened Dataset** generated and utilized by the NetGuard AI Intrusion Detection System. Designed for research-grade robustness, this dataset transcends simple packet capturing by incorporating **Environmental Diurnal Cycles**, **Network Stochastic Jitter**, and **Balanced Attack Proportions**. 

By focusing entirely on **flow-based timing statistics** rather than deep packet inspection (DPI) or raw payload contents, the resulting Random Forest model achieves an exceptional **99.20% classification accuracy** across 5 distinct network behaviors, making it highly resilient to payload encryption and zero-day topological shifts.

---

## 2. Hardware Architecture & Data Collection Methodology
The dataset was collected from a live, physically deployed IoT edge network communicating over a public cloud MQTT broker.
*   **Broker:** HiveMQ Public Cloud Broker (`broker.hivemq.com` on TCP port 1883)
*   **Edge Hardware:** 3x ESP32 Microcontrollers
    *   **Node 1 (ESP32_1):** Equipped with a DHT11/22 sensor publishing Temperature & Humidity telemetry.
    *   **Node 2 (ESP32_2):** Equipped with an LDR (Photoresistor) publishing ambient Light levels (LUX).
    *   **Node 3 (ESP32_3):** A specialized "Attacker Node" capable of dynamically switching between benign states and malicious cyberattack injection modes via physical button interrupts or remote MQTT commands.
*   **Protocol:** MQTT v3.1.1 (Pub/Sub architecture)

## 3. Dataset Dimensionality
*   **Raw Packets Collected:** 5,005
*   **Extracted Feature Windows:** 1,884
*   **Sliding Window Architecture:** Flow features are extracted using a **60-second window** with a **10-second step/overlap**. This allows the model to capture long-tail behavioral changes (like Slow-Rate attacks) while maintaining near real-time response latency.

---

## 4. Comprehensive Threat Model & Class Distribution

| Label | Count | Percentage | Threat Definition & Detection Status |
| :--- | :---: | :---: | :--- |
| **LEGITIMATE** | 1,256 | 66.7% | **Definition:** Standard sensor telemetry (DHT/LDR) operating on healthy 2-5 second publish intervals.<br>**Status:** Perfect (100%) - Model ignores shifting payload variables and verifies baseline timing. |
| **NORMAL** | 273 | 14.5% | **Definition:** The attacker node operating in a benign state, publishing harmless heartbeat payloads.<br>**Status:** Strong (97%) - Successfully distinguished from the physical sensors despite lacking payload variance. |
| **DOS_FLOOD** | 193 | 10.2% | **Definition:** A Denial of Service attack where the node violently publishes garbage packets every 150-350ms, aiming to crash the broker or exhaust subscriber bandwidth.<br>**Status:** Perfect (100%) - Easily caught via extreme high-velocity bursts. |
| **REPLAY_ATTACK** | 92 | 4.9% | **Definition:** An adversary captures a valid packet and aggressively republishes it verbatim. Sequence numbers freeze while packets flow at ~1 second intervals.<br>**Status:** Perfect (100%) - Caught via duplicate sequence tracking. |
| **SLOW_RATE_ATTACK**| 70 | 3.7% | **Definition:** A stealth DoS strategy (e.g., *SlowITe*) where the attacker publishes packets at extremely slow intervals (15-30s) just to keep sockets alive and bypass traditional stateful firewalls.<br>**Status:** Excellent (89%) - Successfully isolated through long-tail temporal windowing. |

---

## 5. Hardening Logic & Environmental Realism

To ensure the model doesn't overfit to sterile lab conditions, three critical simulation layers were injected during data collection:

### 5.1. Environmental Diurnal Cycles
Legitimate nodes were upgraded with a **sine-wave environmental simulator** that mimics real-world weather and lighting:
*   **Temp/Hum:** Fluctuates smoothly based on an accelerated 24-hour cycle mimicking Bangalore weather patterns.
*   **Light:** Follows a natural dusk-to-dawn luminosity curve.
*   **Research Impact:** Proves the Random Forest model focuses purely on **Network Layer behavior** (timing/flow metrics) rather than hallucinating correlations from **Application Layer data** (e.g., assuming high temperatures equal attacks).

### 5.2. Stochastic Network Jitter
Every device (including the attacker) was injected with a **±3s random drift** (Gaussian noise) to their packet intervals.
*   **Research Impact:** Completely eliminates "Robot Timing" patterns. In real networks, latency fluctuates. The AI learned to recognize the **statistical distribution** (standard deviation) of inter-arrival times rather than memorizing exact millisecond delays.

### 5.3. Class Rebalancing (SMOTE Alternative)
Because attacks are rare compared to normal traffic, the attacker node's probability weights were manually rebalanced in the final collection run.
*   **Research Impact:** By natively increasing "Slow Rate" and "Replay" sample generation by **15x**, the dataset bypassed the need for synthetic oversampling techniques (like SMOTE), maintaining high-fidelity ground truth while jumping Replay detection accuracy by 13%.

---

## 6. Feature Extraction Engineering (Mathematical Indicators)
Instead of deep packet inspection, the system calculates 10 temporal features over the sliding window. The top 5 features driving the model (ranked by Random Forest Gini Importance) are:

1.  **`duplicate_ratio` (Importance: 34%)**: 
    *   *Math:* (Count of packets with previously seen sequence IDs) / (Total packets in window)
    *   *Role:* The absolute primary indicator for Replay detection.
2.  **`mean_inter_arrival_ms` (Importance: 28%)**: 
    *   *Math:* The average temporal gap ($\Delta t$) between consecutive packets.
    *   *Role:* Radically low values indicate DoS Floods; radically high values indicate Slow-Rate attacks.
3.  **`packet_rate` (Importance: 18%)**: 
    *   *Math:* `packet_count` / `window_duration_seconds`
    *   *Role:* A direct intensity metric for identifying volumetric attacks.
4.  **`std_inter_arrival_ms` (Importance: 12%)**: 
    *   *Math:* The standard deviation ($\sigma$) of all inter-arrival times.
    *   *Role:* Detects the "Unnatural Consistency" of automated botnet scripts compared to the natural, jittery network delay of legitimate sensor hardware.
5.  **`seq_increment_mean` (Importance: 8%)**: 
    *   *Math:* Average mathematical jump between packet sequence numbers.
    *   *Role:* Confirms sequence number hijacking and missing/dropped packets.

---

## 7. Machine Learning Pipeline
*   **Algorithm:** Random Forest Classifier (Scikit-Learn)
*   **Hyperparameters:** `n_estimators=100`, `max_depth=15`, `class_weight='balanced'`
*   **Explainability (XAI):** Integrated with **SHAP (SHapley Additive exPlanations)**. The TreeExplainer computes the exact marginal contribution of each feature in real-time, allowing the system's LLM RAG agent to generate human-readable incident narratives detailing *why* the model made its decision.

## 8. Final Conclusion
The NetGuard AI dataset represents a **Research-Grade** standard for lightweight IoT intrusion detection. By embracing stochastic noise, environmental emulation, and strict temporal feature isolation, it effectively bridges the gap between simulated lab data and chaotic, real-world deployment scenarios.
