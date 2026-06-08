import paho.mqtt.client as mqtt
import time

def on_connect(client, userdata, flags, rc):
    print("Connected to broker.hivemq.com! Subscribing to netguard/# ...")
    client.subscribe("netguard/#")

def on_message(client, userdata, msg):
    print(f"Received message on [{msg.topic}]: {msg.payload.decode('utf-8')}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect("broker.hivemq.com", 1883, 60)

client.loop_start()
print("Listening for MQTT packets for 15 seconds. Please trigger traffic on your ESP32 nodes...")
time.sleep(15)
client.loop_stop()
print("Done listening.")
