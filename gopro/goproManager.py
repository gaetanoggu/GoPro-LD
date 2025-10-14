import serial
import threading
import time
from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text

# ============================================================
# CONFIGURAZIONE
# ============================================================
PORTE = ["COM5", "COM15", "COM8"]  # Modifica con le tue porte reali
BAUD = 115200
STATUS_INTERVAL = 5  # secondi tra interrogazioni STATUS

arduinos = []
arduino_states = {}  # stato per ogni COM
state_lock = threading.Lock()

# ============================================================
# THREAD DI LETTURA E GESTIONE EVENTI
# ============================================================
def read_arduino(ser):
    """
    Thread principale che legge dalla porta seriale e aggiorna lo stato.
    """
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            with state_lock:
                state = arduino_states.get(ser.port, {})
                if line == "READY":
                    state["status"] = "READY"
                elif line in ["STARTED", "STOPPED"]:
                    state["last_cmd"] = line
                elif line in ["CONNECTED", "DISCONNECTED", "NO_SSID", "NO_PASS"]:
                    state["wifi"] = line
                else:
                    state["last_msg"] = line
                arduino_states[ser.port] = state

            # Stampa sempre la linea ricevuta
            print_formatted_text(f"[COM][{ser.port}] -> {line}")

        except Exception as e:
            state = arduino_states.get(ser.port, {})
            print_formatted_text(f"[COM][{ser.port}] ❌ Errore lettura: {e}")
            print_formatted_text(f"[COM][{ser.port}] ❌ Errore lettura status: {state}")
            time.sleep(1)

# ============================================================
# INVIO COMANDI SERIAL
# ============================================================
def send_command(ser_list, cmd):
    for ser in ser_list:
        try:
            ser.write((cmd + "\n").encode())
            ser.flush()
        except Exception as e:
            print_formatted_text(f"[{ser.port}] ❌ Errore invio comando: {e}")

# ============================================================
# MONITOR STATO PERIODICO
# ============================================================
def monitor_status(ser_list, interval=STATUS_INTERVAL):
    while True:
        send_command(ser_list, "STATUS")
        time.sleep(interval)

# ============================================================
# LETTURA FILE DI RETI
# ============================================================
def load_networks(filename="networks.txt"):
    nets = []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2:
                    ssid = parts[0].strip()
                    pwd = parts[1].strip()
                    nets.append((ssid, pwd))
    except FileNotFoundError:
        print_formatted_text(f"❌ File {filename} non trovato. Creane uno con 'ssid,password' per riga.")
    return nets

# ============================================================
# CONNESSIONE WIFI LOGICA CORRETTA
# ============================================================
def connect_arduino(ser, ssid, pwd, timeout=20):
    """
    Gestisce la connessione WiFi in modo robusto:
      - NO_SSID  -> invia SSID
      - NO_PASS  -> invia password
      - CONNECTED -> successo
      - DISCONNECTED -> fallimento
    """
    ser.reset_input_buffer()
    print_formatted_text(f"[PY][{ser.port}] 🔗 Tentativo connessione a '{ssid}'...")
    start = time.time()
    last_sent = None

    # Reset stato WiFi locale
    with state_lock:
        arduino_states[ser.port]["wifi"] = "NO_SSID"

    while time.time() - start < timeout:
        with state_lock:
            wifi_status = arduino_states.get(ser.port, {}).get("wifi", "")

        if wifi_status == "NO_SSID" and last_sent != "SSID":
            ser.write(f"SETSSID {ssid}\n".encode())
            ser.flush()
            last_sent = "SSID"
            print_formatted_text(f"[PY][{ser.port}] 📡 Inviato SSID: {ssid}")

        elif wifi_status == "NO_PASS" and last_sent != "PASS":
            ser.write(f"SETPASS {pwd}\n".encode())
            ser.flush()
            last_sent = "PASS"
            print_formatted_text(f"[PY][{ser.port}] 🔑 Inviata password.")

        elif wifi_status == "CONNECTED":
            print_formatted_text(f"[PY][{ser.port}] ✅ Connesso a {ssid}")
            return True

        elif wifi_status == "DISCONNECTED":
            print_formatted_text(f"[PY][{ser.port}] ❌ Connessione fallita (DISCONNECTED)")
            return False

        time.sleep(0.2)

    print_formatted_text(f"[PY][{ser.port}] ⏰ Timeout connessione a {ssid}")
    return False

# ============================================================
# APERTURA DELLE PORTE SERIALI
# ============================================================
for porta in PORTE:
    try:
        ser = serial.Serial(porta, BAUD, timeout=1)
        time.sleep(2)

        arduinos.append(ser)
        with state_lock:
            arduino_states[porta] = {"status": "OPEN", "wifi": "NO_SSID", "last_cmd": None}
        threading.Thread(target=read_arduino, args=(ser,), daemon=True).start()
        print_formatted_text(f"[PY][{porta}] Aperta con successo.")
    except Exception as e:
        print_formatted_text(f"[PY][{porta}] ❌ Errore apertura: {e}")

if not arduinos:
    print_formatted_text("[PY] ❌ Nessun Arduino aperto!")
    exit()

# ============================================================
# CONNESSIONE ALLE RETI WIFI
# ============================================================
available_networks = load_networks()
for idx, ser in enumerate(arduinos):
    if idx >= len(available_networks):
        print_formatted_text(f"[PY][{ser.port}] ⚠ Nessuna rete assegnata, skipping.")
        continue
    ssid, pwd = available_networks[idx]
    print_formatted_text(f"[PY][{ser.port}] 🌐 Configurazione rete: SSID='{ssid}', PASS='{pwd}'")
    connect_arduino(ser, ssid, pwd)

# ============================================================
# INTERFACCIA A COMANDO
# ============================================================
print_formatted_text("[PY] 👉 Comandi: 'a'=START, 's'=STOP, 'status'=stato, 'q'=USCITA")

def print_states():
    with state_lock:
        for port, info in arduino_states.items():
            print_formatted_text(f"[STATE][{port}] {info}")

with patch_stdout():
    while True:
        cmd = prompt('> ', bottom_toolbar="Comandi: 'a'=START, 's'=STOP, 'status', 'q'=USCITA").lower().strip()
        if cmd == "a":
            print_formatted_text("[PY] 🚀 START tutte le GoPro...")
            send_command(arduinos, "START")
        elif cmd == "s":
            print_formatted_text("[PY] 🛑 STOP tutte le GoPro...")
            send_command(arduinos, "STOP")
        elif cmd == "status":
            print_states()
        elif cmd == "q":
            print_formatted_text("[PY] 🔌 Chiusura connessioni...")
            break
        else:
            print_formatted_text("[PY] ⚠️ Comando non valido.")

# ============================================================
# CHIUSURA
# ============================================================
for ser in arduinos:
    ser.close()
print_formatted_text("[PY] ✅ Connessioni chiuse.")
