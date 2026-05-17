#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid        = "Wokwi-GUEST";
const char* password    = "";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient   espClient;
PubSubClient client(espClient);

#define LDR_PIN 34

float         syncedHour  = 13.0f;
bool          timeSynced  = false;
unsigned long syncMs      = 0;
unsigned long lastMsg     = 0;
unsigned long nextInterval= 3000;

// ── Current IST hour ──────────────────────────────────────────────────────────
float currentHour() {
  float elapsed = (float)(millis() - syncMs) / 3600000.0f;
  float h = syncedHour + elapsed;
  while (h >= 24.0f) h -= 24.0f;
  return h;
}

// ── Bangalore light model ─────────────────────────────────────────────────────
// Sunrise: ~6:10am (6.17), Sunset: ~6:25pm (18.42) IST
// Peak: ~3800 LUX at solar noon ~12:20pm
int bangaloreLight(float h) {
  if (h < 6.17f || h > 18.42f) {
    return random(0, 25);   // Night
  }
  float pi     = 3.14159265f;
  float factor = sin((h - 6.17f) * pi / 12.25f);
  if (factor < 0.0f) factor = 0.0f;
  int lux = (int)(factor * 3800.0f) + (int)random(-60, 60);
  if (lux < 0) lux = 0;
  return lux;
}

// ── MQTT Callback ─────────────────────────────────────────────────────────────
void callback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  if (String(topic) == "netguard/timesync") {
    int idx = msg.indexOf("ist_hour");
    if (idx >= 0) {
      int colon = msg.indexOf(':', idx);
      if (colon >= 0) {
        float h = msg.substring(colon + 1).toFloat();
        if (h >= 0.0f && h < 24.0f) {
          syncedHour = h;
          syncMs     = millis();
          timeSynced = true;
          Serial.print("[TimeSync] IST hour anchored: ");
          Serial.println(h);
        }
      }
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    String clientId = "ESP32-LDR-" + String(millis());
    if (client.connect(clientId.c_str())) {
      client.subscribe("netguard/timesync");
      client.publish("netguard/timereq", "{\"device\":\"esp32_2\"}");
      Serial.println("[MQTT] Connected");
    } else {
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  Serial.print("Connecting WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println(" OK");
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  unsigned long now = millis();
  if (now - lastMsg > nextInterval) {
    lastMsg      = now;
    nextInterval = (unsigned long)random(2000, 5000);

    float h   = currentHour();
    int   lux = bangaloreLight(h);

    String payload = String("{") +
      "\"device\":\"esp32_2\"," +
      "\"light\":"    + String(lux) + "," +
      "\"ist_hour\":" + String(h, 2) + "," +
      "\"synced\":"   + (timeSynced ? "true" : "false") +
      "}";

    client.publish("netguard/device2", payload.c_str());
    Serial.println("PUB: " + payload);
  }
}
