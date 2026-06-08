import paho.mqtt.client as mqtt
import sys

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to broker.hivemq.com successfully!")
        print("Subscribed to 'netguard/#' topic tree.")
        print("Listening for MQTT packets. Press [Ctrl+C] to stop...")
        print("="*80)
        client.subscribe("netguard/#")
    else:
        print(f"Connection failed with code {rc}")
        sys.exit(1)

def on_message(client, userdata, msg):
    print(f"[{msg.topic}]: {msg.payload.decode('utf-8', errors='ignore')}")

# Initialize client using latest API version recommendation
try:
    # Try paho-mqtt v2 client initialization
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
except AttributeError:
    # Fallback for paho-mqtt v1
    client = mqtt.Client()

client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect("broker.hivemq.com", 1883, 60)
    client.loop_forever()
except KeyboardInterrupt:
    print("\nStopping listener...")
    client.disconnect()
    print("Disconnected safely.")
except Exception as e:
    print(f"Error: {e}")
