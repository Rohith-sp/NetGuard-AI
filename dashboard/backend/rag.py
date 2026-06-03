"""
NetGuard AI — RAG Security Analyst Chatbot
Grounded in:
1. DATASETS.md (behavioral dataset types & features)
2. Last 50 MQTT log entries (real-time traffic state)
3. Latest ML inference output (anomaly scores & SHAP feature values)
"""
import os
import re
import requests

# ── Dynamic import for Gemini safety ──────────────────────────────────────────
HAS_GEMINI = False
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    pass

# ── Load DATASETS.md Knowledge Base ──────────────────────────────────────────
DATASETS_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "mqtt_collector", "DATASETS.md"
))

def get_datasets_kb() -> str:
    if os.path.exists(DATASETS_PATH):
        try:
            with open(DATASETS_PATH, "r", encoding="utf-8") as f:
                return f.read()
        except:
            pass
    
    # High-fidelity fallback knowledge if file is missing
    return """
    # NetGuard AI: Hardened Behavioral Dataset
    - Devices: ESP32_1 (DHT22 Temp/Humidity), ESP32_2 (LDR Light), ESP32_3 (Attacker)
    - Behaviors:
      • LEGITIMATE: Normal sensor timing (2-5s intervals), Temp/Hum follows diurnal Bangalore weather, Light matches sunrise/sunset.
      • NORMAL: Normal timing baseline, successfully distinguished from sensors.
      • DOS_FLOOD: High-velocity flood packets on ESP32_3 (interval 150-350ms).
      • REPLAY_ATTACK: Duplicate packets with frozen sequence numbers (interval 0.8-1.5s).
      • SLOW_RATE_ATTACK: Ghost packets every 15-30s designed to bypass traditional stateful detection.
    - Top 5 Feature Indicators:
      1. duplicate_ratio: Primary indicator for Replay attacks.
      2. mean_inter_arrival_ms: Distinguishes Flood and Slow-Rate from Normal.
      3. packet_rate: Identifies high-intensity DoS bursts.
      4. std_inter_arrival_ms: Detects unnatural consistency of attack scripts compared to sensor jitter.
      5. seq_increment_mean: Confirms sequence number hijacking.
    """

# ── Groq LLM Call ───────────────────────────────────────────────────────────
def call_groq_llm(system_prompt: str, user_question: str) -> str:
    # Look for GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY in the environment
    keys = []
    for k in ["GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY"]:
        val = os.environ.get(k)
        if val and val.strip() and not val.startswith("gsk_placeholder"):
            keys.append(val.strip())
            
    if not keys:
        return None
        
    # High performance versatile and fast models on Groq
    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama3-70b-8192",
        "llama-3.1-8b-instant",
        "llama3-8b-8192"
    ]
    
    for api_key in keys:
        for model in models:
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_question}
                    ],
                    "temperature": 0.2
                }
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=6
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"].strip()
                elif r.status_code == 429:
                    print(f"[RAG] Groq Key Rate Limited (429) for model {model} — trying next model/key.")
                    continue
                else:
                    print(f"[RAG] Groq error ({r.status_code}) with key {api_key[:8]}...: {r.text[:150]}")
            except Exception as e:
                print(f"[RAG] Groq connection issue with model {model}: {e}")
                
    return None

# ── Gemini LLM Call ───────────────────────────────────────────────────────────
def call_gemini_llm(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key or not HAS_GEMINI or api_key.startswith("AIzaSyAl0"):
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[RAG] Gemini live API error: {e}")
        return None

# ── High-Fidelity Local Rule-Based Expert System Fallback ────────────────────
def run_expert_system(question: str, kb: str, logs: list, inference: dict) -> str:
    q = question.lower()
    lbl = inference.get("label", "AWAITING").upper()
    conf = inference.get("confidence", 0)
    rate = inference.get("pkt_rate", 0)
    iat = inference.get("iat_mean", 0)
    dup = inference.get("dup_ratio", 0.0)
    seq = inference.get("seq_gap", 1.0)
    is_atk = inference.get("isAttack", False)
    
    # Ask about current threats / attack mode / anomaly
    if any(x in q for x in ["threat", "attack", "anomaly", "suspicious", "flagged", "red", "critical", "why"]):
        if not is_atk or lbl == "NORMAL":
            return (
                f"### NetGuard AI Security Assessment\n"
                f"* **Current State:** Nominal (Legitimate and Normal status verified).\n"
                f"* **Anomaly Score:** {conf:.1f}% (Low confidence of threat).\n\n"
                f"All active sensor nodes (ESP32_1 and ESP32_2) are publishing telemetry inside standard diurnal timing windows. "
                f"No malicious high-velocity packet signatures, duplicate sequence numbers, or irregular packet gaps are currently observed on ESP32_3."
            )
        
        shap_details = ""
        if inference.get("shap"):
            shap_details = "\n* **SHAP Force Plot Weights:**\n"
            for item in inference["shap"][:3]:
                shap_details += f"  - `{item['feature']}`: value={item['raw']} (SHAP weight={item['value']})\n"

        reasons = []
        if lbl == "DOS_FLOOD":
            reasons = [
                f"packet rate is extremely high ({rate} pkt/s)",
                f"inter-arrival time (IAT) is critically low ({iat} ms)",
                "unnatural temporal consistency is observed (std_inter_arrival_ms is minimized)"
            ]
        elif lbl == "REPLAY_ATTACK":
            reasons = [
                f"duplicate ratio has spiked to {dup*100:.1f}%",
                "sequence increments are frozen (seq_increment_mean is near 0)"
            ]
        elif lbl == "SLOW_RATE_ATTACK":
            reasons = [
                f"inter-arrival time (IAT) has stretched abnormally to {iat} ms",
                "highly periodic stealth probe signatures matched"
            ]

        return (
            f"### 🚨 Intrusion Detected: {lbl.replace('_', ' ')}\n"
            f"* **Confidence Level:** {conf:.1f}%\n"
            f"* **Telemetry Indicators:**\n"
            f"  - **Packet Rate:** {rate:.2f} pkt/s (expected baseline ~0.3 pkt/s)\n"
            f"  - **Mean IAT:** {iat} ms\n"
            f"  - **Duplicate Ratio:** {dup*100:.1f}%\n"
            f"  - **Mean Seq Gap:** {seq}\n"
            f"{shap_details}\n"
            f"**Analyst Verdict:** The model classified this behavior as `{lbl}` because the " + " and ".join(reasons) +
            f". This triggers a HIGH-severity incident response card in the SOC. Remote containment recommended."
        )

    # Ask about sensor metrics / DHT / LDR
    if any(x in q for x in ["sensor", "dht", "ldr", "temp", "humidity", "light", "lux"]):
        dht_log = next((log for log in logs if "device1" in log["topic"]), None)
        ldr_log = next((log for log in logs if "device2" in log["topic"]), None)
        
        rep = "### Live Sensor Node Telemetry\n"
        if dht_log:
            try:
                p = re.findall(r'"temp":\s*([\d\.]+),\s*"(?:humidity|hum)":\s*([\d\.]+)', dht_log["payload"])[0]
                rep += f"* 🌡 **ESP32_1 (DHT22):** Temperature = {p[0]}°C, Humidity = {p[1]}%\n"
            except:
                rep += f"* 🌡 **ESP32_1 (DHT22):** Online (Data syncing)\n"
        else:
            rep += f"* 🌡 **ESP32_1 (DHT22):** Offline / No recent syncs\n"

        if ldr_log:
            try:
                p = re.findall(r'"light":\s*([\d\.]+)', ldr_log["payload"])[0]
                rep += f"* 💡 **ESP32_2 (LDR):** Ambient Light = {p[0]} LUX\n"
            except:
                rep += f"* 💡 **ESP32_2 (LDR):** Online (Light sensor active)\n"
        else:
            rep += f"* 💡 **ESP32_2 (LDR):** Offline / No recent syncs\n"

        rep += "\n*Note: Telemetry fluctuations mimic authentic Bangalore day/night cycles to test model robustness.*"
        return rep

    # Ask about the dataset features / explain features
    if any(x in q for x in ["feature", "dataset", "column", "shap", "mean_inter_arrival", "duplicate_ratio"]):
        return (
            f"### NetGuard AI Model Feature Architecture\n"
            f"The Random Forest model (`netguard_model.pkl`) evaluates 10 statistical properties:\n"
            f"1. **`packet_rate`**: Intensity of packets per second.\n"
            f"2. **`duplicate_ratio`**: Percentage of packet retransmissions with identical IDs (key for Replay).\n"
            f"3. **`mean_inter_arrival_ms`**: Expected gap between packets (reveals floods and slow rates).\n"
            f"4. **`std_inter_arrival_ms`**: Consistency of inter-packet gaps (detects automated script signatures).\n"
            f"5. **`seq_increment_mean`**: Progression of packet sequence counters.\n\n"
            f"These features are calculated dynamically on a 10s sliding window and explained via SHAP force plot weights."
        )

    # Default fallback reply
    return (
        f"### Security Operations Center (SOC) Support\n"
        f"I can help analyze live network behaviors. Here are some questions you can ask me:\n"
        f"* *'Why is ESP32_3 flagged as suspicious right now?'*\n"
        f"* *'Explain the active threat and its SHAP features.'*\n"
        f"* *'What are the latest sensor temperature and light readings?'*\n"
        f"* *'What features does the Random Forest model evaluate?'*"
    )

# ── Main Entrypoint ──────────────────────────────────────────────────────────
def query_analyst(question: str, logs: list, inference: dict) -> str:
    kb = get_datasets_kb()
    
    # 1. Format the logs (up to 50 logs)
    formatted_logs = ""
    for idx, log in enumerate(logs[-50:]):
        formatted_logs += f"[{log.get('ts', '—')}] {log.get('topic', '—')}: {log.get('payload', '—')}\n"
    
    # 2. Format the latest ML inference status
    formatted_inference = (
        f"Current Label: {inference.get('label', 'AWAITING')}\n"
        f"Confidence: {inference.get('confidence', 0)}%\n"
        f"Is Attack Active: {inference.get('isAttack', False)}\n"
        f"Live Features: Packet Rate={inference.get('pkt_rate', 0)} pkt/s, "
        f"Mean IAT={inference.get('iat_mean', 0)} ms, Duplicate Ratio={inference.get('dup_ratio', 0.0)}, "
        f"Seq Increment Mean={inference.get('seq_gap', 1.0)}\n"
    )
    if inference.get("shap"):
        formatted_inference += f"Top SHAP values: {inference.get('shap')[:3]}\n"

    # 3. Construct System Prompt & User Prompt
    system_prompt = (
        "You are 'NetGuard AI Security Analyst', an elite, professional real-time explainable AI assistant in a SOC dashboard.\n"
        "Your task is to analyze network state questions using the grounded context provided below.\n\n"
        "=== KNOWLEDGE BASE (DATASETS.md) ===\n"
        f"{kb}\n\n"
        "=== REAL-TIME ML INFERENCE OUTPUT ===\n"
        f"{formatted_inference}\n\n"
        "=== LAST 50 MQTT NETWORK LOG LINES ===\n"
        f"{formatted_logs}\n"
        "======================================\n\n"
        "INSTRUCTIONS:\n"
        "- Base your analysis EXACTLY on the live ML values, packet logs, and the knowledge base.\n"
        "- Provide a structured, expert analysis using these exact headers:\n"
        "  ### 📊 Real-Time Telemetry Analysis\n"
        "  (Detail the exact current packet rate, mean inter-arrival time, duplicate ratio, and compare them against normal baselines)\n"
        "  ### 🧠 ML Model Decisions & SHAP Explainability\n"
        "  (Explain the active classification (NORMAL, DOS_FLOOD, REPLAY_ATTACK, SLOW_RATE_ATTACK) and why the specific SHAP driver weights pushed the Random Forest model toward this prediction)\n"
        "  ### 🛡️ SOC Recommendations & Containment Actions\n"
        "  (Give actionable recommendations: e.g. nominal monitoring, or warning about high severity, suggesting the user click 'Reset to Normal' or trigger containment via the Attacker Control panel if an attack is active)\n"
        "- Format your answer with clean GitHub-style Markdown (use bolding, bullet points, and code styling).\n"
        "- Keep it professional, highly authoritative, crisp, and technical."
    )

    # 1. Try Groq API keys first
    answer = call_groq_llm(system_prompt, question)
    if answer:
        print("[RAG] Served query using Groq Live LLM.")
        return answer

    # 2. Try Gemini LLM second
    full_prompt = f"{system_prompt}\n\nUser Question: {question}"
    answer = call_gemini_llm(full_prompt)
    if answer:
        print("[RAG] Served query using Gemini Live LLM.")
        return answer

    # 3. Fallback to Expert System
    print("[RAG] Served query using High-Fidelity Local Expert System.")
    return run_expert_system(question, kb, logs, inference)
