#include <WiFi.h>
#include <PubSubClient.h>

// ==========================================
// 1. WiFi & MQTT Configuration
// ==========================================
const char* ssid        = "wifi-name";
const char* password    = "wifi-password";
const char* mqtt_server = "broker.hivemq.com";
const int   mqtt_port   = 1883;

WiFiClient espClient;
PubSubClient client(espClient);

// ==========================================
// 2. Hardware Pins
// ==========================================
// The D0 pin from the LDR module is connected to GPIO 32
const int LDR_PIN = 32;

// ==========================================
// 3. Timing and Payload variables
// ==========================================
unsigned long lastPublishTime = 0;
unsigned long nextPublishDelay = 3000;
unsigned long seqNumber = 0;

// ==========================================
// Helpers
// ==========================================
void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected.");
}

void reconnect() {
  while (!client.connected()) {
    String clientId = "ESP32-LDR-" + String(random(0xffff), HEX);
    Serial.print("Attempting MQTT connection...");
    
    if (client.connect(clientId.c_str())) {
      Serial.println("Connected!");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" try again in 5 seconds");
      delay(5000);
    }
  }
}

// ==========================================
// Setup
// ==========================================
void setup() {
  Serial.begin(115200);
  
  // FIX 1: Set as INPUT_PULLUP to prevent floating pin issue on GPIO 32
  pinMode(LDR_PIN, INPUT_PULLUP);
  
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  
  Serial.println("\n==============================================");
  Serial.println(">> LDR SENSOR NODE READY (esp32_2)");
  Serial.println("==============================================\n");
}

// ==========================================
// Main Loop
// ==========================================
void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long now = millis();

  // Send a packet randomly every 2 to 5 seconds (Normal behavior)
  if (now - lastPublishTime >= nextPublishDelay) {
    lastPublishTime = now;
    nextPublishDelay = random(2000, 5000);
    seqNumber++;

    // FIX 2: Use digitalRead to read the D0 pin (outputs 0 or 1)
    int lightValue = digitalRead(LDR_PIN);

    // Build the JSON payload string matching the expected format
    String payload = "{\"device\":\"esp32_2\",\"sensor\":\"LDR\",\"light\":" + String(lightValue) +
                     ",\"seq\":" + String(seqNumber) + "}";

    // Publish to the device2 topic
    client.publish("netguard_rohit_77/device2", payload.c_str());
    
    Serial.print("PUB: ");
    Serial.println(payload);
  }
}
