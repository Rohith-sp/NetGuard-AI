#include <WiFi.h>
#include <PubSubClient.h>

// ==========================================
// 1. WiFi & MQTT Configuration
// ==========================================
const char* ssid        = "ROHITH";
const char* password    = "Password";
const char* mqtt_server = "broker.hivemq.com";
const int   mqtt_port   = 1883;

WiFiClient espClient;
PubSubClient client(espClient);

// ==========================================
// 2. Hardware Pins
// ==========================================
const int BUTTON_PIN = 14;

// ==========================================
// 3. Attack Mode State
// ==========================================
enum AttackMode { NORMAL, DOS_FLOOD, REPLAY_ATTACK, SLOW_RATE_ATTACK };
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

// ==========================================
// Helpers
// ==========================================
String getModeString() {
  switch (currentMode) {
    case NORMAL:           return "NORMAL";
    case DOS_FLOOD:        return "DOS_FLOOD";
    case REPLAY_ATTACK:    return "REPLAY_ATTACK";
    case SLOW_RATE_ATTACK: return "SLOW_RATE_ATTACK";
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
}

void applyMode(String modeStr) {
  AttackMode oldMode = currentMode;
  if (modeStr == "NORMAL")            currentMode = NORMAL;
  else if (modeStr == "DOS_FLOOD")    currentMode = DOS_FLOOD;
  else if (modeStr == "REPLAY_ATTACK")currentMode = REPLAY_ATTACK;
  else if (modeStr == "SLOW_RATE_ATTACK") currentMode = SLOW_RATE_ATTACK;
  
  if (currentMode != oldMode) {
    if (currentMode != REPLAY_ATTACK) {
      replayPayload = "";
    }
    // Force immediate packet transmission for the new mode
    lastPublishTime = 0;
    nextPublishDelay = 0;
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
    
    // Cycle to the next mode
    currentMode = (AttackMode)((currentMode + 1) % 4);
    
    // Reset sequence and replay payload cache for the new mode
    if (currentMode != REPLAY_ATTACK) {
       replayPayload = ""; 
    }
    
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
  }

  // --- 3. Publish Payload ---
  if (shouldPublish) {
    lastPublishTime = now;
    
    // In all modes except REPLAY_ATTACK, we generate a fresh packet with a new sequence number
    if (currentMode != REPLAY_ATTACK) {
      seqNumber++;
    }

    // Build the JSON payload string
    String payload = "{\"device\":\"esp32_3\",\"mode\":\"" + getModeString() +
                     "\",\"seq\":" + String(seqNumber) +
                     ",\"manual\":true}";

    // If Replay mode, reuse the exact same string (same sequence number) over and over
    if (currentMode == REPLAY_ATTACK) {
      if (replayPayload == "") {
         replayPayload = payload; // Capture the first payload to replay
      } else {
         payload = replayPayload; // Use the cached payload
      }
    }

    // Send it to the broker!
    client.publish("netguard/attacker", payload.c_str());
    Serial.print("PUB: ");
    Serial.println(payload);
  }
}
