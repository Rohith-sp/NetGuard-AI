#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient espClient;
PubSubClient client(espClient);

#define LDR_PIN 34
unsigned long lastMsg = 0;
unsigned long nextInterval = 3000;
float simulatedHour = 19.0;

void setup_wifi() {
  delay(10);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (!client.connected()) {
    while (!client.connected()) {
      if (client.connect("esp32_2")) {
        Serial.println("Connected");
      } else { delay(5000); }
    }
  }
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > nextInterval) {
    lastMsg = now;
    nextInterval = random(2000, 5000); // Mid-speed
    simulatedHour += 0.2; 
    if(simulatedHour >= 24) simulatedHour = 0;

    float lightFactor = 0.0;
    if (simulatedHour > 5 && simulatedHour < 19) {
        lightFactor = sin((simulatedHour - 5) * 3.14159 / 14.0);
    }
    int simulatedLight = (int)(lightFactor * 3500.0) + random(0, 100);
    if (simulatedLight < 50) simulatedLight = 50;

    String payload = "{\"device\":\"esp32_2\",\"light\":" + String(simulatedLight) + "}";
    client.publish("netguard/device2", payload.c_str());
    Serial.println("Sent: " + payload);
  }
}
