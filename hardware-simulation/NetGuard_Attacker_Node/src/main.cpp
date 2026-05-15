#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid         = "Wokwi-GUEST";
const char* password     = "";
const char* mqtt_server  = "broker.hivemq.com";

WiFiClient espClient;
PubSubClient client(espClient);

enum AttackMode {
  NORMAL,
  DOS_FLOOD,
  REPLAY_ATTACK,
  SLOW_RATE_ATTACK
};

AttackMode currentMode      = NORMAL;
AttackMode previousMode     = NORMAL;

unsigned long modeStartTime    = 0;
unsigned long modeDuration     = 0; 
unsigned long lastPublishTime  = 0;
unsigned long seqNumber        = 0;
String        replayPayload    = "";
unsigned long nextSlowDelay    = 15000;
unsigned long nextNormalDelay  = 3000;
unsigned long nextReplayDelay  = 1000;
unsigned long nextDosDelay     = 200;

String getModeString() {
  switch (currentMode) {
    case NORMAL:           return "NORMAL";
    case DOS_FLOOD:        return "DOS_FLOOD";
    case REPLAY_ATTACK:    return "REPLAY_ATTACK";
    case SLOW_RATE_ATTACK: return "SLOW_RATE_ATTACK";
  }
  return "UNKNOWN";
}

AttackMode pickNewMode() {
  int roll = random(0, 100);
  AttackMode candidate;
  if      (roll < 30) candidate = NORMAL;
  else if (roll < 55) candidate = DOS_FLOOD;
  else if (roll < 80) candidate = REPLAY_ATTACK;
  else                candidate = SLOW_RATE_ATTACK;

  if (candidate == currentMode) {
    candidate = (AttackMode)((currentMode + 1 + random(0, 3)) % 4);
  }
  return candidate;
}

void setup_wifi() {
  delay(10);
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected.");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Attempting MQTT...");
    String clientId = "ESP32-Attacker-" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("connected");
    } else {
      delay(5000);
    }
  }
}

void updateMode() {
  unsigned long now = millis();
  if (now - modeStartTime >= modeDuration) {
    previousMode  = currentMode;
    currentMode   = pickNewMode();
    modeStartTime = now;

    switch (currentMode) {
      case NORMAL:           modeDuration = random(30000, 60000);  break;
      case DOS_FLOOD:        modeDuration = random(10000, 20000);  break;
      case REPLAY_ATTACK:    modeDuration = random(15000, 30000);  break;
      case SLOW_RATE_ATTACK: modeDuration = random(30000, 50000);  break;
    }

    replayPayload = "";
    nextSlowDelay = random(15000, 30000);
    nextNormalDelay = random(2000, 5000);

    Serial.print("\n>> MODE SWITCH: ");
    Serial.print(getModeString());
    Serial.print("  (duration: ");
    Serial.print(modeDuration / 1000);
    Serial.println("s)");
  }
}

void setup() {
  Serial.begin(115200);
  randomSeed(analogRead(0));
  setup_wifi();
  client.setServer(mqtt_server, 1883);

  currentMode   = NORMAL;
  modeStartTime = millis();
  modeDuration  = random(15000, 30000);
  Serial.println(">> MID-SPEED ATTACKER READY");
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  updateMode();
  unsigned long now = millis();
  bool shouldPublish = false;

  switch (currentMode) {
    case NORMAL: 
      if (now - lastPublishTime >= nextNormalDelay) {
        shouldPublish = true;
        nextNormalDelay = random(2000, 5000); // 2s to 5s
      }
      break;

    case DOS_FLOOD:
      if (now - lastPublishTime >= nextDosDelay) {
        shouldPublish = true;
        nextDosDelay = random(150, 350); // 0.15s to 0.35s
      }
      break;

    case REPLAY_ATTACK: 
      if (now - lastPublishTime >= nextReplayDelay) {
        shouldPublish = true;
        nextReplayDelay = random(800, 1500); // 0.8s to 1.5s
      }
      break;

    case SLOW_RATE_ATTACK:
      if (now - lastPublishTime >= nextSlowDelay) {
        shouldPublish = true;
        nextSlowDelay = random(15000, 30000); // 15s to 30s
      }
      break;
  }

  if (shouldPublish) {
    lastPublishTime = now;
    if (currentMode != REPLAY_ATTACK) seqNumber++;

    String payload = "{\"device\":\"esp32_3\",\"mode\":\"" + getModeString() + "\",\"seq\":" + String(seqNumber) + "}";

    if (currentMode == REPLAY_ATTACK && replayPayload != "") {
      payload = replayPayload;
    } else {
      replayPayload = payload;
    }

    Serial.println("Pub: " + payload);
    client.publish("netguard/attacker", payload.c_str());
  }
}
