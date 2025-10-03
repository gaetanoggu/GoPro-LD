/*
========================================================
   Arduino Nano 33 IoT - WiFi + Controllo GoPro
========================================================

UTILIZZO:
L'Arduino comunica via porta seriale (115200 baud).
I comandi vanno inviati terminati da newline (\n).

--------------------------------------------------------
COMANDI DISPONIBILI SU PORTA SERIALE:

- SETSSID <nome_rete>
    Imposta l'SSID della rete WiFi a cui connettersi.
    Esempio:  SETSSID MyWiFi

- SETPASS <password>
    Imposta la password della rete WiFi.
    Esempio:  SETPASS MyPassword123

- CONNECT
    Tenta la connessione alla rete WiFi usando SSID e
    password impostati. Se la connessione riesce, le
    credenziali vengono salvate in flash.

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
- Le credenziali WiFi vengono salvate in flash dopo 
  un CONNECT riuscito, e ricaricate automaticamente 
  all'avvio.
- Se la connessione cade, il sistema prova a 
  riconnettersi automaticamente ogni 10 secondi.
- La GoPro deve essere accesa e connessa alla stessa 
  rete WiFi dell'Arduino (o in WiFi diretto GoPro).

========================================================
*/

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

// timeout in ms per la lettura della risposta HTTP
const unsigned long HTTP_RESPONSE_TIMEOUT = 3000;

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
      if (WiFi.status() == WL_CONNECTED) {
        Serial.print("CONNECTED to: ");
        Serial.println(WiFi.SSID());
        Serial.print("IP: "); Serial.println(WiFi.localIP());
      } else {
        Serial.println("DISCONNECTED");
      }
    }
    else {
      Serial.println("⚠️ Comando non riconosciuto");
    }
  }
}

// Funzione per connettersi al WiFi
bool connectWiFi() {
  lastConnectAttempt = millis();

  // controllo credenziali
  if (creds.ssid[0] == '\0' || (uint8_t)creds.ssid[0] == 0xFF) {
    Serial.println("⚠️ Nessun SSID configurato");
    return false;
  }

  Serial.print("Connessione a WiFi: "); Serial.println(creds.ssid);

  // In alcuni casi WiFi.begin restituisce uno status ma preferisco controllare WiFi.status()
  WiFi.begin(creds.ssid, creds.pass);

  unsigned long start = millis();
  const unsigned long timeout = 10000; // 10s massimo per connettersi
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout) {
    delay(500);
    Serial.print(".");
  }

  status = WiFi.status();
  if (status == WL_CONNECTED) {
    Serial.println("\n✅ Connesso!");
    printConnectionInfo();
    return true;
  } else {
    Serial.println("\n❌ Connessione fallita");
    // opzionale: mostra codice errore
    Serial.print("WiFi status: "); Serial.println(status);
    return false;
  }
}

void printConnectionInfo() {
  Serial.print("SSID: "); Serial.println(WiFi.SSID());
  Serial.print("IP: "); Serial.println(WiFi.localIP());
}

// Flash storage
void readCredentials() {
  creds = wifiStorage.read();
  if (creds.ssid[0] == '\0' || (uint8_t)creds.ssid[0] == 0xFF) {
    creds.ssid[0] = '\0';
    creds.pass[0] = '\0';
  }
  Serial.print("SSID letto da flash: "); 
  Serial.println(creds.ssid[0] ? creds.ssid : "<vuoto>");
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
  if (!client.connect("10.5.5.9", 80)) {
    Serial.println("❌ Impossibile connettersi alla GoPro (start)");
    client.stop();
    return;
  }

  Serial.println("📡 Invio comando START...");
  client.println("GET /gp/gpControl/command/shutter?p=1 HTTP/1.1");
  client.println("Host: 10.5.5.9");
  client.println("Connection: close");
  client.println();

  // leggo la risposta con timeout per evitare blocchi
  unsigned long start = millis();
  while (client.connected() || client.available()) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
      // opzionale: mostra la risposta
      // Serial.println(line);
    }
    if (millis() - start > HTTP_RESPONSE_TIMEOUT) {
      Serial.println("⚠️ Timeout nella lettura della risposta START");
      break;
    }
  }
  client.stop();
  Serial.println("STARTED");
}

void stopRecording() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️ WiFi non connesso, impossibile STOP");
    return;
  }
  if (!client.connect("10.5.5.9", 80)) {
    Serial.println("❌ Impossibile connettersi alla GoPro (stop)");
    client.stop();
    return;
  }

  Serial.println("📡 Invio comando STOP...");
  client.println("GET /gp/gpControl/command/shutter?p=0 HTTP/1.1");
  client.println("Host: 10.5.5.9");
  client.println("Connection: close");
  client.println();

  unsigned long start = millis();
  while (client.connected() || client.available()) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
      // opzionale: mostra la risposta
      // Serial.println(line);
    }
    if (millis() - start > HTTP_RESPONSE_TIMEOUT) {
      Serial.println("⚠️ Timeout nella lettura della risposta STOP");
      break;
    }
  }
  client.stop();
  Serial.println("STOPPED");
}