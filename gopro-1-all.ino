#include <SPI.h>
#include <WiFiNINA.h>
#include <FlashStorage.h>

// Struttura per salvare SSID e password
struct WiFiCredentials {
  char ssid[32];
  char pass[64];
};

// Storage Flash
FlashStorage(wifiStorage, WiFiCredentials);

WiFiCredentials creds;

int status = WL_IDLE_STATUS;
WiFiClient client;
unsigned long lastConnectAttempt = 0;
const unsigned long reconnectInterval = 10000; // 10 secondi

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("Avvio sistema WiFi...");

  // Legge credenziali salvate
  readCredentials();
  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    unsigned long now = millis();
    if (now - lastConnectAttempt > reconnectInterval) {
      Serial.println("⚠️ WiFi caduto, riconnessione...");
      connectWiFi();
    }
  }

  // Gestione comandi seriali
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("SETSSID ")) {
      cmd.remove(0, 8);
      cmd.toCharArray(creds.ssid, sizeof(creds.ssid));
      Serial.print("Nuovo SSID ricevuto: "); Serial.println(creds.ssid);
    } 
    else if (cmd.startsWith("SETPASS ")) {
      cmd.remove(0, 8);
      cmd.toCharArray(creds.pass, sizeof(creds.pass));
      Serial.println("Nuova password ricevuta");
    }
    else if (cmd == "CONNECT") {
      if (connectWiFi()) {
        saveCredentials(); // Salva solo se connessione OK
      }
    }
    else if (cmd == "START") startRecording();
    else if (cmd == "STOP") stopRecording();
    else if (cmd == "STATUS") {
      Serial.println(WiFi.status() == WL_CONNECTED ? "CONNECTED" : "DISCONNECTED");
    }
    else {
      Serial.println("⚠️ Comando non riconosciuto");
    }
  }
}

// Funzione per connettersi al WiFi
bool connectWiFi() {
  lastConnectAttempt = millis();
  if (strlen(creds.ssid) == 0) {
    Serial.println("⚠️ Nessun SSID configurato");
    return false;
  }

  Serial.print("Connessione a WiFi: "); Serial.println(creds.ssid);
  status = WiFi.begin(creds.ssid, creds.pass);

  int attempts = 0;
  while (status != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    status = WiFi.status();
    attempts++;
  }

  if (status == WL_CONNECTED) {
    Serial.println("\n✅ Connesso!");
    Serial.print("IP: "); Serial.println(WiFi.localIP());
    return true;
  } else {
    Serial.println("\n❌ Connessione fallita");
    return false;
  }
}

// Flash storage
void readCredentials() {
  creds = wifiStorage.read();
  if (creds.ssid[0] == 0) {
    strcpy(creds.ssid, "");
    strcpy(creds.pass, "");
  }
  Serial.print("SSID letto da flash: "); Serial.println(creds.ssid);
}

void saveCredentials() {
  wifiStorage.write(creds);
  Serial.println("✅ Credenziali salvate in Flash");
}

// Funzioni GoPro
void startRecording() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi non connesso, impossibile START");
    return;
  }
  if (client.connect("10.5.5.9", 80)) {
    Serial.println("📡 Invio comando START...");
    client.println("GET /gp/gpControl/command/shutter?p=1 HTTP/1.1");
    client.println("Host: 10.5.5.9");
    client.println("Connection: close");
    client.println();
    while (client.connected() || client.available()) {
      if (client.available()) client.readStringUntil('\n');
    }
    client.stop();
    Serial.println("STARTED");
  }
}

void stopRecording() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi non connesso, impossibile STOP");
    return;
  }
  if (client.connect("10.5.5.9", 80)) {
    Serial.println("📡 Invio comando STOP...");
    client.println("GET /gp/gpControl/command/shutter?p=0 HTTP/1.1");
    client.println("Host: 10.5.5.9");
    client.println("Connection: close");
    client.println();
    while (client.connected() || client.available()) {
      if (client.available()) client.readStringUntil('\n');
    }
    client.stop();
    Serial.println("STOPPED");
  }
}
