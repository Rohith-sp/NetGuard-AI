#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const char* ssid        = "Wokwi-GUEST";
const char* password    = "";
const char* mqtt_server = "broker.hivemq.com";

WiFiClient   espClient;
PubSubClient client(espClient);

// ── Attack Mode State ─────────────────────────────────────────────────────────
enum AttackMode { NORMAL, DOS_FLOOD, REPLAY_ATTACK, SLOW_RATE_ATTACK };

AttackMode currentMode    = NORMAL;
bool       manualOverride = false;   // true = dashboard locked the mode

unsigned long modeStartTime  = 0;
unsigned long modeDuration   = 0;
unsigned long lastPublishTime= 0;
unsigned long seqNumber      = 0;
String        replayPayload  = "";

unsigned long nextNormalDelay = 3000;
unsigned long nextDosDelay    = 200;
unsigned long nextReplayDelay = 1000;
unsigned long nextSlowDelay   = 15000;

// ── Helpers ───────────────────────────────────────────────────────────────────
String getModeString() {
  switch (currentMode) {
    case NORMAL:           return "NORMAL";
    case DOS_FLOOD:        return "DOS_FLOOD";
    case REPLAY_ATTACK:    return "REPLAY_ATTACK";
    case SLOW_RATE_ATTACK: return "SLOW_RATE_ATTACK";
  }
  return "NORMAL";
}

void applyMode(String mode) {
  if (mode == "NORMAL")            currentMode = NORMAL;
  else if (mode == "DOS_FLOOD")    currentMode = DOS_FLOOD;
  else if (mode == "REPLAY_ATTACK")currentMode = REPLAY_ATTACK;
  else if (mode == "SLOW_RATE_ATTACK") currentMode = SLOW_RATE_ATTACK;
  replayPayload  = "";
  modeStartTime  = millis();
  Serial.print(">> MODE SET: "); Serial.println(getModeString());
}

// ── MQTT Callback — receives dashboard commands ────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.print("[CMD] "); Serial.println(msg);

  // Parse JSON command: {"command":"SET_MODE","mode":"DOS_FLOOD"}
  StaticJsonDocument<200> doc;
  DeserializationError err = deserializeJson(doc, msg);
  if (err) return;

  String cmd = doc["command"] | "";
  if (cmd == "SET_MODE") {
    String mode = doc["mode"] | "NORMAL";
    applyMode(mode);
    if (mode == "NORMAL") manualOverride = false;
    else                  manualOverride = true;
  } else if (cmd == "RELEASE") {
    manualOverride = false;
    Serial.println(">> Auto-switching resumed.");
  }
}

// ── Auto mode picker ──────────────────────────────────────────────────────────
AttackMode pickNewMode() {
  int roll = random(0, 100);
  AttackMode c;
  if      (roll < 30) c = NORMAL;
  else if (roll < 55) c = DOS_FLOOD;
  else if (roll < 80) c = REPLAY_ATTACK;
  else                c = SLOW_RATE_ATTACK;
  if (c == currentMode) c = (AttackMode)((currentMode + 1) % 4);
  return c;
}

void updateMode() {
  if (manualOverride) return;   // dashboard has control
  unsigned long now = millis();
  if (now - modeStartTime >= modeDuration) {
    currentMode  = pickNewMode();
    modeStartTime = now;
    switch (currentMode) {
      case NORMAL:           modeDuration = random(30000, 60000); break;
      case DOS_FLOOD:        modeDuration = random(10000, 20000); break;
      case REPLAY_ATTACK:    modeDuration = random(15000, 30000); break;
      case SLOW_RATE_ATTACK: modeDuration = random(30000, 50000); break;
    }
    replayPayload = "";
    Serial.print(">> AUTO SWITCH: "); Serial.println(getModeString());
  }
}

// ── WiFi + MQTT ───────────────────────────────────────────────────────────────
void setup_wifi() {
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi OK");
}

void reconnect() {
  while (!client.connected()) {
    String id = "ESP32-Attacker-" + String(random(0xffff), HEX);
    if (client.connect(id.c_str())) {
      client.subscribe("netguard/cmd");     // ← Listen for dashboard commands
      Serial.println("[MQTT] Connected, subscribed netguard/cmd");
    } else { delay(5000); }
  }
}

void setup() {
  Serial.begin(115200);
  randomSeed(analogRead(0));
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(mqttCallback);

  currentMode   = NORMAL;
  modeStartTime = millis();
  modeDuration  = random(15000, 30000);
  Serial.println(">> ATTACKER NODE READY — awaiting dashboard or auto-switch");
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
        nextNormalDelay = random(2000, 5000);
      }
      break;
    case DOS_FLOOD:
      if (now - lastPublishTime >= nextDosDelay) {
        shouldPublish = true;
        nextDosDelay = random(150, 350);
      }
      break;
    case REPLAY_ATTACK:
      if (now - lastPublishTime >= nextReplayDelay) {
        shouldPublish = true;
        nextReplayDelay = random(800, 1500);
      }
      break;
    case SLOW_RATE_ATTACK:
      if (now - lastPublishTime >= nextSlowDelay) {
        shouldPublish = true;
        nextSlowDelay = random(15000, 30000);
      }
      break;
  }

  if (shouldPublish) {
    lastPublishTime = now;
    if (currentMode != REPLAY_ATTACK) seqNumber++;

    String payload = "{\"device\":\"esp32_3\",\"mode\":\"" + getModeString() +
                     "\",\"seq\":" + String(seqNumber) +
                     ",\"manual\":" + String(manualOverride ? "true" : "false") + "}";

    if (currentMode == REPLAY_ATTACK && replayPayload != "") {
      payload = replayPayload;
    } else {
      replayPayload = payload;
    }

    client.publish("netguard/attacker", payload.c_str());
    Serial.println("PUB: " + payload);
  }
}
