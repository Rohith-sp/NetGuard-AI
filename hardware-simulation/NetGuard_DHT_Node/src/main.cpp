#include <WiFi.h>
#include <PubSubClient.h>
#include <DHTesp.h>

const char* ssid        = "Wokwi-GUEST";
const char* password    = "";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient   espClient;
PubSubClient client(espClient);
DHTesp       dhtSensor;

#define DHT_PIN    15
#define BUZZER_PIN 13
#define LED_R      25
#define LED_G      26
#define LED_B      27

// ── Time Sync ─────────────────────────────────────────────────────────────────
float         syncedHour  = 13.0;   // Default: 1pm IST until backend syncs
bool          timeSynced  = false;
unsigned long syncMs      = 0;

unsigned long lastMsg      = 0;
unsigned long nextInterval = 3000;

// ── Current simulated IST hour ─────────────────────────────────────────────────
float currentHour() {
  float elapsed = (float)(millis() - syncMs) / 3600000.0f;
  float h = syncedHour + elapsed;
  while (h >= 24.0f) h -= 24.0f;
  return h;
}

// ── Bangalore climate model ───────────────────────────────────────────────────
// Temp: min ~20°C at 5am, max ~33°C at 1pm
float bangaloreTemp(float h) {
  float pi    = 3.14159265f;
  float base  = 26.5f + 6.5f * sin((h - 5.5f) * pi / 12.0f);
  if (base < 18.0f) base = 18.0f;
  if (base > 38.0f) base = 38.0f;
  float noise = (float)(random(-4, 4)) / 10.0f;
  return base + noise;
}

// Humidity: high at night ~75%, low at midday ~38%
float bangaloreHum(float h) {
  float pi   = 3.14159265f;
  float base = 57.0f - 19.0f * sin((h - 5.5f) * pi / 12.0f);
  if (base < 25.0f) base = 25.0f;
  if (base > 90.0f) base = 90.0f;
  if (h < 5.5f || h > 17.5f) base += 8.0f;  // Extra humid at night
  if (base > 90.0f) base = 90.0f;
  float noise = (float)(random(-3, 3)) / 10.0f;
  return base + noise;
}

// ── MQTT Callback ──────────────────────────────────────────────────────────────
void callback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  String t = String(topic);

  // Time sync from backend: {"type":"timesync","ist_hour":13.75}
  if (t == "netguard/timesync") {
    int idx = msg.indexOf("ist_hour");
    if (idx >= 0) {
      // Find the colon after "ist_hour" and parse the number
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

  // IDS alert — flash red LED
  if (t == "netguard/alerts") {
    digitalWrite(LED_R, HIGH);
    digitalWrite(LED_G, LOW);
    digitalWrite(LED_B, LOW);
    // Simple buzzer via GPIO (no tone() needed)
    for (int i = 0; i < 3; i++) {
      digitalWrite(BUZZER_PIN, HIGH); delay(100);
      digitalWrite(BUZZER_PIN, LOW);  delay(100);
    }
    Serial.println("[ALERT] Intrusion detected!");
  }
}

void reconnect() {
  while (!client.connected()) {
    String clientId = "ESP32-DHT-" + String(millis());
    if (client.connect(clientId.c_str())) {
      client.subscribe("netguard/alerts");
      client.subscribe("netguard/timesync");
      // Request time sync immediately
      client.publish("netguard/timereq", "{\"device\":\"esp32_1\"}");
      digitalWrite(LED_G, HIGH);
      Serial.println("[MQTT] Connected");
    } else {
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  dhtSensor.setup(DHT_PIN, DHTesp::DHT22);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  digitalWrite(LED_G, HIGH);

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

    float h    = currentHour();
    float temp = bangaloreTemp(h);
    float hum  = bangaloreHum(h);

    String payload = String("{") +
      "\"device\":\"esp32_1\"," +
      "\"temp\":"     + String(temp, 1) + "," +
      "\"humidity\":" + String(hum,  1) + "," +
      "\"ist_hour\":" + String(h,    2) + "," +
      "\"synced\":"   + (timeSynced ? "true" : "false") +
      "}";

    client.publish("netguard/device1", payload.c_str());
    Serial.println("PUB: " + payload);
  }
}