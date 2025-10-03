/*
========================================================
   Arduino Nano 33 IoT - WiFi + Controllo GoPro
   VERSIONE: senza salvataggio credenziali in flash
========================================================

UTILIZZO:
L'Arduino comunica via porta seriale (115200 baud).
I comandi vanno inviati terminati da newline (\n).

--------------------------------------------------------
COMANDI DISPONIBILI SU PORTA SERIALE:

- SETSSID <nome_rete>
    Imposta l'SSID della rete WiFi a cui connettersi per la sessione corrente.
    Esempio:  SETSSID MyWiFi

- SETPASS <password>
    Imposta la password della rete WiFi per la sessione corrente.
    Esempio:  SETPASS MyPassword123

- CONNECT
    Tenta la connessione alla rete WiFi usando SSID e password impostati.
    ATTENZIONE: le credenziali NON vengono salvate.

- STATUS
    Mostra lo stato della connessione WiFi:
      CONNECTED (con SSID e IP)
      DISCONNECTED (non connesso)

- START
    Invia alla GoPro (IP 10.5.5.9) il comando per
    avviare la registrazione.

- STOP
    Invia alla GoPro (IP 10.5.5.9) il comando per
    fermare la registrazione.

--------------------------------------------------------
NOTE:
- Prima di invocare CONNECT è obbligatorio aver inviato SETSSID e SETPASS.
- Se la connessione cade, il sistema prova a
  riconnettersi automaticamente ogni 10 secondi usando le credenziali correnti (non persistenti).
- La GoPro deve essere accesa e connessa alla stessa
  rete WiFi dell'Arduino (o in WiFi diretto GoPro).

========================================================
*/

#include <SPI.h>
#include <WiFiNINA.h>

char creds_ssid[32] = "";
char creds_pass[64] = "";

int status = WL_IDLE_STATUS;
WiFiClient client;
unsigned long lastConnectAttempt = 0;
const unsigned long reconnectInterval = 10000; // 10 secondi

// timeout in ms per la lettura della risposta HTTP
const unsigned long HTTP_RESPONSE_TIMEOUT = 10000;

void setup() {
  Serial.begin(115200);
  while (!Serial);

  connectWiFi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    unsigned long now = millis();
    if (now - lastConnectAttempt > reconnectInterval && !(creds_ssid[0] == '\0' || (uint8_t)creds_ssid[0] == 0xFF) && !(creds_pass[0] == '\0' || (uint8_t)creds_pass[0] == 0xFF)) {
      connectWiFi();
    }
  }

  // Gestione comandi seriali
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("SETSSID ")) {
      cmd.remove(0, 8);
      cmd.toCharArray(creds_ssid, sizeof(creds_ssid));

      memset(creds_pass, 0, sizeof(creds_pass));

      Serial.println("NO_PASS");
    }
    else if (cmd.startsWith("SETPASS ")) {
      cmd.remove(0, 8);
      cmd.toCharArray(creds_pass, sizeof(creds_pass));

      connectWiFi();
    }
    else if (cmd == "CONNECT") {
      connectWiFi();
    }
    else if (cmd == "START") startRecording();
    else if (cmd == "STOP") stopRecording();
    else if (cmd == "STATUS") {
      if (WiFi.status() == WL_CONNECTED) {
        Serial.println("CONNECTED");
      } else {
        Serial.println("DISCONNECTED");
      }
    }
    else if (cmd == "QUIT") {
      if (client.connected()) {
        client.stop();
        Serial.println("CLOSED");
      }

      if (WiFi.status() == WL_CONNECTED) {
        WiFi.disconnect();
        Serial.println("DISCONNECTED");
      }
    }
    else {
      Serial.println("⚠ Comando non riconosciuto");
    }
  }
}

// Funzione per connettersi al WiFi
bool connectWiFi() {
  lastConnectAttempt = millis();

  // controllo credenziali
  if (creds_ssid[0] == '\0' || (uint8_t)creds_ssid[0] == 0xFF) {
    Serial.println("NO_SSID");
    return false;
  }
  if (creds_pass[0] == '\0' || (uint8_t)creds_pass[0] == 0xFF) {
    Serial.println("NO_PASS");
    return false;
  }

  Serial.println("CONNECTING");

  WiFi.begin(creds_ssid, creds_pass);

  unsigned long start = millis();
  const unsigned long timeout = 10000; // 10s massimo per connettersi
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout) {
    delay(500);
    Serial.print(".");
  }

  status = WiFi.status();
  if (status == WL_CONNECTED) {
    Serial.println("CONNECTED");
    return true;
  } else {
    Serial.println("DISCONNECTED");
    return false;
  }
}

// --- Funzioni GoPro ---
void startRecording() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("DISCONNECT");
    return;
  }
  if (!client.connect("10.5.5.9", 80)) {
    Serial.println("FAILED");
    client.stop();
    return;
  }

  client.println("GET /gp/gpControl/command/shutter?p=1 HTTP/1.1");
  client.println("Host: 10.5.5.9");
  client.println("Connection: close");
  client.println();

  // leggo la risposta con timeout per evitare blocchi
  unsigned long start = millis();
  while (client.connected() || client.available()) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
    }
    if (millis() - start > HTTP_RESPONSE_TIMEOUT) {
      Serial.println("TIMEOUT");
      break;
    }
  }
  client.stop();
  Serial.println("STARTED");
}

void stopRecording() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("DISCONNECT");
    return;
  }
  if (!client.connect("10.5.5.9", 80)) {
    Serial.println("FAILED");
    client.stop();
    return;
  }

  client.println("GET /gp/gpControl/command/shutter?p=0 HTTP/1.1");
  client.println("Host: 10.5.5.9");
  client.println("Connection: close");
  client.println();

  unsigned long start = millis();
  while (client.connected() || client.available()) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
    }
    if (millis() - start > HTTP_RESPONSE_TIMEOUT) {
      Serial.println("TIMEOUT");
      break;
    }
  }
  client.stop();
  Serial.println("STOPPED");
}