import requests
import json

try:
    r = requests.get("http://localhost:8000/debug")
    if r.status_code == 200:
        data = r.json()
        print("--- LATEST INFERENCE ---")
        print(json.dumps(data.get("latest_inference"), indent=2))
        print("\n--- LAST 20 MQTT MESSAGES ---")
        for idx, msg in enumerate(data.get("last_20_mqtt_messages", [])):
            print(f"[{idx}] {msg.get('ts')} | {msg.get('topic')} | {msg.get('payload')}")
    else:
        print(f"Error: Status code {r.status_code}")
except Exception as e:
    print(f"Error fetching debug: {e}")
