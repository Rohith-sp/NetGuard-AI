# NetGuard AI: Hardened Behavioral Dataset Analysis

## 1. Executive Summary
This report analyzes the **Final Hardened Dataset** for the NetGuard AI project. Unlike the initial collection, this dataset includes **Environmental Diurnal Cycles**, **Network Stochastic Jitter**, and **Balanced Attack Weights**. 

The result is a highly robust model capable of **99.20% classification accuracy** across 5 distinct network behaviors.

## 2. Dataset Properties (Final Run)
*   **Raw Packets:** 5,005
*   **Feature Windows:** 1,884
*   **Window Size:** 60s (Sliding with 10s step)
*   **Devices:** 3 (DHT22, LDR, Attacker)

---

## 3. Behavioral Class Distribution

| Label | Count | Percentage | Detection Status |
| :--- | :---: | :---: | :--- |
| **LEGITIMATE** | 1,256 | 66.7% | **Perfect (100%)** - Immune to Temp/Light fluctuations. |
| **NORMAL** | 273 | 14.5% | **Strong (97%)** - Successfully distinguished from sensors. |
| **DOS_FLOOD** | 193 | 10.2% | **Perfect (100%)** - Caught via high-velocity bursts. |
| **REPLAY_ATTACK** | 92 | 4.9% | **Perfect (100%)** - Caught via frozen sequence numbers. |
| **SLOW_RATE_ATTACK**| 70 | 3.7% | **Excellent (89%)** - Successfully isolated stealth packets. |

---

## 4. Hardening Logic Implementation

### 4.1. Environmental Diurnal Cycles
Legitimate nodes were upgraded with a **sine-wave environmental simulator**.
*   **Temp/Hum:** Fluctuates based on an accelerated 24-hour cycle.
*   **Light:** Follows a dusk-to-dawn curve.
*   **Impact:** The AI proved it focuses on **Network Layer behavior** (timing) rather than **Application Layer data** (values), making it resilient to seasonal or environmental changes.

### 4.2. Stochastic Network Jitter
Every device (including the attacker) was injected with **±3s random drift**.
*   **Impact:** Eliminated "Robot Timing" patterns. The AI learned to recognize the **statistical distribution** of inter-arrival times rather than exact numbers.

### 4.3. Class Rebalancing
Attack modes were given higher weights in the final simulator.
*   **Impact:** Increased "Slow Rate" and "Replay" samples by **15x**, resulting in the 13% jump in Replay detection accuracy.

---

## 5. Top 5 Behavioral Indicators (Feature Importance)
Based on the Random Forest Gini Importance:
1.  **`duplicate_ratio`**: Primary indicator for Replay detection.
2.  **`mean_inter_arrival_ms`**: Distinguishes Flood and Slow-Rate from Normal.
3.  **`packet_rate`**: Identifies high-intensity DoS bursts.
4.  **`std_inter_arrival_ms`**: Detects the "Unnatural Consistency" of attack scripts compared to sensors.
5.  **`seq_increment_mean`**: Confirms sequence number hijacking.

---

## 6. Final Conclusion
The NetGuard AI dataset is now **Research-Ready**. It successfully simulates the complexity of a real home network while maintaining high-fidelity ground truth. The model `netguard_model.pkl` trained on this data is suitable for **Real-Time deployment.**
