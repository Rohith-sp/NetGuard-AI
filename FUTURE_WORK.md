# NetGuard-AI: Future Work & Architectural Expansion

This document outlines the top three high-priority attack vectors slated for future implementation. While NetGuard-AI currently excels at detecting volumetric floods and temporal anomalies (Replay/Slow-Rate), introducing these advanced attacks will test the system's payload validation, broker resource limits, and the absolute limits of the underlying Machine Learning model.

---

## 1. False Data Injection (Payload Poisoning)

### Concept
Instead of disrupting the network flow, the attacker masquerades as a legitimate sensor and publishes mathematically valid but physically impossible data (e.g., changing a temperature reading from `30°C` to `900°C`). 

### Required System Changes
*   **ESP32 Attacker Code:** Create a new `DATA_POISON` mode. The attacker node will subscribe to `netguard/device1`, read the legitimate JSON format, and publish corrupted values back to the same topic.
*   **Backend Machine Learning (`main.py`):** 
    *   Our current Random Forest model only evaluates *Temporal Flow* (timing). It ignores payloads.
    *   We must implement a **Layer-2 ML Model** (e.g., an Isolation Forest or Autoencoder) that strictly parses the `payload` JSON and flags statistical outliers based on historical Bangalore weather data.
*   **Dashboard UI (`page.tsx`):** Add a secondary "Payload Integrity" metric to the Analytics tab, clearly separating "Network Flow Anomalies" from "Data Anomalies".

---

## 2. Subscription Bombing (Broker Memory Exhaustion)

### Concept
Rather than flooding a single topic, the attacker rapidly creates and publishes to thousands of randomly generated, unique MQTT topics (e.g., `netguard/junk_01` to `netguard/junk_99`). This specifically targets the IoT Broker's routing memory and subscriber wildcard handling, often causing broker crashes.

### Required System Changes
*   **ESP32 Attacker Code:** Add a `TOPIC_BOMB` mode. Use a random string generator inside the Arduino loop to constantly shift the publish destination: `client.publish("netguard/" + randomString, "garbage")`.
*   **Feature Engineering (`main.py` / `extract_features`):** 
    *   Add a new mathematical feature to the sliding window: `unique_topics_per_window`.
    *   Normally, this value is `3` (Device 1, Device 2, Attacker). During a bomb attack, it will spike to `50+`.
*   **Random Forest Model (`netguard_model.pkl`):** Retrain the model on the updated dataset containing the new `unique_topics_per_window` feature.
*   **Dashboard UI:** Update the Network Topology map to dynamically spawn red nodes or show a "Broker Memory Warning" when the unique topic count explodes.

---

## 3. Adversarial Evasion Attack (Attacking the AI)

### Concept
An advanced attacker reverse-engineers the NetGuard-AI Random Forest model. Knowing that the model flags "unnatural consistency" (`std_inter_arrival_ms`), the attacker launches a DoS flood but intentionally forces the ESP32 to drop random packets and sleep at irregular intervals. The goal is to perfectly mimic the stochastic jitter of benign sensor traffic, tricking the AI into classifying the flood as `NORMAL`.

### Required System Changes
*   **ESP32 Attacker Code:** Add an `EVASION_ATTACK` mode. Program a dynamic delay loop: `delay(random(100, 3000))`. The attacker will monitor its own outgoing packet rate to ensure it stays just below the ML trigger threshold while still congesting the network.
*   **Explainable AI Dashboard (`rag.py` / SHAP):** 
    *   This attack is designed to be highly visual. In the dashboard, the SHAP force plot will explicitly show *how* the attacker tricked the system (e.g., showing the `std_inter_arrival_ms` weight pushing the decision toward `NORMAL`).
*   **Backend Machine Learning:** Implement **Adversarial Training**. After proving the AI can be tricked, we generate a new dataset containing these evasion samples and retrain the model so it learns the "trick" patterns, patching the vulnerability.

---

### Conclusion
Implementing these three vectors transforms NetGuard-AI from an Intrusion Detection System into a full-scale **Adversarial Machine Learning Research Platform**, demonstrating multi-layered security concepts spanning the Edge (ESP32), the Network (MQTT Broker), and the Cloud (AI Backend).
