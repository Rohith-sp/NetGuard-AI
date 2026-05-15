#include <DHTesp.h>
#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient espClient;
PubSubClient client(espClient);

const int DHT_PIN = 15;
DHTesp dhtSensor;

#define BUZZER_PIN 13
#define LED_R 25
#define LED_G 26
#define LED_B 27

unsigned long lastMsg = 0;
unsigned long nextInterval = 3000; 
float simulatedHour = 19.0; 
unsigned long alertStartTime = 0;
bool alertActive = false;

void setup_wifi() {
  delay(10);
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected");
}

void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Alert received [");
  Serial.print(topic);
  Serial.println("]");
}

void setup() {
  Serial.begin(115200);
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
  dhtSensor.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
}

void loop() {
  if (!client.connected()) {
    while (!client.connected()) {
      if (client.connect("esp32_1")) {
        client.subscribe("netguard/alerts");
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

    float baseTemp = 25.0 + 5.0 * sin((simulatedHour - 8) * 2.0 * 3.14159 / 24.0);
    float baseHum = 50.0 - 10.0 * sin((simulatedHour - 8) * 2.0 * 3.14159 / 24.0);
    float finalTemp = baseTemp + (random(-5, 5) / 10.0);
    float finalHum  = baseHum + (random(-5, 5) / 10.0);

    String payload = "{\"device\":\"esp32_1\",\"temp\":" + String(finalTemp, 2) + ",\"humidity\":" + String(finalHum, 1) + "}";
    client.publish("netguard/device1", payload.c_str());
    Serial.println("Sent: " + payload);
  }
}