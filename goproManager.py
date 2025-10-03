import serial
import threading
import time
from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text

# -----------------------
# CONFIGURAZIONE PORTE
# -----------------------
PORTE = ["COM5", "COM8"]  # Modifica con le tue porte
BAUD = 115200
STATUS_INTERVAL = 5  # secondi tra interrogazioni STATUS

arduinos = []

# -----------------------
# FUNZIONE DI LETTURA SERIAL
# -----------------------
def read_arduino(ser):
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()

            print_formatted_text(f"[COM][{ser.port}] Lettura: {line}")  # debug lettura

            if line:
                if line == "READY":
                    print_formatted_text(f"[COM][{ser.port}] ✅ Pronta!")
                elif line in ["STARTED", "STOPPED"]:
                    print_formatted_text(f"[COM][{ser.port}] {line}")
                elif line in ["CONNECTED", "DISCONNECTED"]:
                    print_formatted_text(f"[COM][{ser.port}] Stato WiFi: {line}")
                else:
                    print_formatted_text(f"[COM][{ser.port}] -> {line}")  # debug extra
        except Exception as e:
            print_formatted_text(f"[COM][{ser.port}] ❌ Errore lettura: {e}")
            break

# -----------------------
# FUNZIONE PER INVIARE COMANDO
# -----------------------
def send_command(ser_list, cmd):
    def send_to_one(ser, cmd):
        try:
            ser.write((cmd + "\n").encode())
            ser.flush()
        except Exception as e:
            print_formatted_text(f"[{ser.port}] ❌ Errore invio comando: {e}")

    threads = []
    for ser in ser_list:
        t = threading.Thread(target=send_to_one, args=(ser, cmd), daemon=True)
        t.start()
        threads.append(t)
    # Non aspettiamo join, così i comandi partono in parallelo e il main thread non si blocca

# -----------------------
# THREAD MONITOR STATUS
# -----------------------
def monitor_status(ser_list, interval=STATUS_INTERVAL):
    while True:
        send_command(ser_list, "STATUS")
        time.sleep(interval)

# -----------------------
# ASSEGNAZIONE WIFI: ogni Arduino si collega solo al suo SSID/password da networks.txt, retry immediato su errore
# -----------------------
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
                    if ssid:
                        nets.append((ssid, pwd))
    except FileNotFoundError:
        print_formatted_text(f"❌ File {filename} non trovato. Creane uno con 'ssid,password' per riga.")
    return nets



def try_connect_wifi(ser, ssid, pwd, timeout=15):
    ser.reset_input_buffer()
    # Invia i comandi separati come richiesto dal firmware Arduino
    ser.write(f"SETSSID {ssid}\n".encode())
    ser.flush()
    time.sleep(0.2)  # breve pausa per sicurezza
    ser.write(f"SETPASS {pwd}\n".encode())
    ser.flush()
    print_formatted_text(f"[PY][{ser.port}] Connessione a: {ssid} ...")
    start = time.time()
    while time.time() - start < timeout:
        if ser.in_waiting:
            line = ser.readline().decode(errors="ignore").strip()
            if line == "CONNECTED":
                print_formatted_text(f"[PY][{ser.port}] ✅ Connesso a {ssid}")
                return True
            elif line in ["DISCONNECTED", "NO_SSID"]:
                print_formatted_text(f"[PY][{ser.port}] ❌ Connessione fallita a {ssid} ({line})")
                return False
    print_formatted_text(f"[PY][{ser.port}] ⏰ Timeout connessione a {ssid}")
    return False

def connect_arduino(ser, ssid, pwd, assigned_ssids):
    print_formatted_text(f"[PY][{ser.port}] Inizializzazione connessione WiFi...")
    print_formatted_text(f"[PY][{ser.port}] Tentativo di connessione a SSID: {ssid}")
    ok = try_connect_wifi(ser, ssid, pwd)
    if ok:
        assigned_ssids.add(ssid)
    else:
        print_formatted_text(f"[PY][{ser.port}] ❌ Connessione fallita a {ssid}. Verifica il file networks.txt.")

 

arduinos = []
for porta in PORTE:
    try:
        ser = serial.Serial(porta, BAUD, timeout=1)
        arduinos.append(ser)
        threading.Thread(target=read_arduino, args=(ser,), daemon=True).start()
        print_formatted_text(f"[PY][{porta}] Aperta con successo.")
    except Exception as e:
        print_formatted_text(f"[PY][{porta}] ❌ Errore apertura: {e}")

if not arduinos:
    print_formatted_text("[PY] ❌ Nessun Arduino aperto!")
    exit()

# -----------------------
# CONNESSIONE WIFI PARALLELA
# -----------------------

available_networks = load_networks()
assigned_ssids = set()
threads = []
for idx, ser in enumerate(arduinos):
    ssid, pwd = available_networks[idx]
    t = threading.Thread(target=connect_arduino, args=(ser, ssid, pwd, assigned_ssids))
    t.start()
    threads.append(t)
for t in threads:
    t.join()



# -----------------------
# THREAD MONITOR STATUS
# -----------------------
threading.Thread(target=monitor_status, args=(arduinos,), daemon=True).start()

# -----------------------
# COMANDI DA TASTIERA
# -----------------------

print_formatted_text("[PY] 👉 Comandi disponibili: 'a' = START, 's' = STOP, 'q' = USCITA, 'status' = Mostra stato WiFi")

# Usa patch_stdout per evitare che le print si sovrappongano all'input
with patch_stdout():
    while True:
        cmd = prompt('> ', bottom_toolbar="Scrivi un comando: 'a'=START, 's'=STOP, 'status', 'q'=USCITA").lower().strip()
        if cmd == "a":
            print_formatted_text("[PY] 🚀 START tutte le GoPro...")
            send_command(arduinos, "START")
        elif cmd == "s":
            print_formatted_text("[PY] 🛑 STOP tutte le GoPro...")
            send_command(arduinos, "STOP")
        elif cmd == "status":
            send_command(arduinos, "STATUS")
        elif cmd == "q":
            print_formatted_text("[PY] 🔌 Chiusura connessioni...")
            break
        else:
            print_formatted_text("[PY] ⚠️ Comando non valido. Usa 'a', 's', 'status' o 'q'.")

# -----------------------
# CHIUSURA SERIALI
# -----------------------
for ser in arduinos:
    ser.close()
print_formatted_text("[PY] ✅ Connessioni chiuse.")