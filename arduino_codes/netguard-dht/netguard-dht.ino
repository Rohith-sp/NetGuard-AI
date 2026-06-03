#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>

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
#define DHTPIN 15
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

#define BUZZER_PIN 13
#define BLUE_PIN  27
#define RED_PIN   25
#define GREEN_PIN 26

// ==========================================
// 3. Variables
// ==========================================
unsigned long lastPublishTime = 0;
unsigned long nextPublishDelay = 3000;
unsigned long seqNumber = 0;

// Alarm State Variables (Marked volatile for callback safety)
volatile bool underAttack = false;
volatile unsigned long attackStartTime = 0;
const unsigned long ATTACK_DURATION = 5000; 
unsigned long lastBlinkTime = 0;
bool alarmState = false; 

// ==========================================
// Helpers
// ==========================================
void setLedColor(bool r, bool g, bool b) {
  digitalWrite(RED_PIN, r ? HIGH : LOW);
  digitalWrite(GREEN_PIN, g ? HIGH : LOW);
  digitalWrite(BLUE_PIN, b ? HIGH : LOW);
}

void setup_wifi() {
  delay(10);
  Serial.println("\nConnecting to WiFi: " + String(ssid));
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected.");
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  
  Serial.println("\n WARNING! ALERT RECEIVED: " + msg);
  
  underAttack = true;
  attackStartTime = millis(); 
}

void reconnect() {
  while (!client.connected()) {
    String clientId = "ESP32-DHT-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("Connected to MQTT!");
      client.subscribe("netguard/alerts");
    } else {
      delay(5000);
    }
  }
}

// ==========================================
// Setup
// ==========================================
void setup() {
  Serial.begin(115200);
  
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RED_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(BLUE_PIN, OUTPUT);
  
  dht.begin();
  setup_wifi();
  
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(mqttCallback); 
  
  Serial.println("\n==============================================");
  Serial.println(">> DHT11 NODE READY (esp32_1)");
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

  // --- 1. ALARM LOGIC ---
  if (underAttack) {
    if (now - attackStartTime > ATTACK_DURATION) {
      underAttack = false; 
      Serial.println(">> ALARM FINISHED. Returning to Green.");
    } else {
      // Actively under attack!
      if (now - lastBlinkTime > 250) {
        lastBlinkTime = now;
        alarmState = !alarmState;
        
        if (alarmState) {
          Serial.println("   [DEBUG] Turning RED + BUZZ ON");
          setLedColor(true, false, false); // RED ON
          digitalWrite(BUZZER_PIN, HIGH);  // BUZZER ON
        } else {
          Serial.println("   [DEBUG] Turning OFF");
          setLedColor(false, false, false); // OFF
          digitalWrite(BUZZER_PIN, LOW);    // BUZZER OFF
        }
      }
    }
  } else {
    // Normal, safe state
    setLedColor(false, true, false); // Solid GREEN
    digitalWrite(BUZZER_PIN, LOW);   // BUZZER OFF
  }

  // --- 2. SENSOR LOGIC ---
  if (now - lastPublishTime >= nextPublishDelay) {
    lastPublishTime = now;
    nextPublishDelay = random(2000, 5000);
    seqNumber++;

    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();

    if (!isnan(humidity) && !isnan(temperature)) {
      String payload = "{\"device\":\"esp32_1\",\"temp\":" + String(temperature) +
                       ",\"hum\":" + String(humidity) +
                       ",\"seq\":" + String(seqNumber) + "}";
      client.publish("netguard/device1", payload.c_str());
      Serial.print("PUB: ");
      Serial.println(payload);
    }
  }
}
