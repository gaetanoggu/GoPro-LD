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



def try_connect_wifi(ser, ssid, pwd, timeout=10):
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

def connect_arduino(idx, ser, available_networks, assigned_ssids):
    print_formatted_text(f"[PY][{ser.port}] Inizializzazione connessione WiFi...")
    if idx >= len(available_networks):
        print_formatted_text(f"[PY][{ser.port}] ❌ Nessuna rete disponibile per questa scheda.")
        return

    # Trova una rete non ancora assegnata
    tried = set()
    while True:
        print_formatted_text(f"[PY][{ser.port}] Tentativo di connessione...")
        # Scegli la prima rete non ancora assegnata
        for net_idx, (ssid, pwd) in enumerate(available_networks):
            if ssid not in assigned_ssids and net_idx not in tried:
                break
        else:
            # Se tutte le reti sono già assegnate, scegli quella di default (idx)
            ssid, pwd = available_networks[idx]
            net_idx = idx
        tried.add(net_idx)

        ok = try_connect_wifi(ser, ssid, pwd)
        if ok:
            assigned_ssids.add(ssid)
            # Aggiorna la posizione idx con la rete usata
            available_networks[idx] = (ssid, pwd)
            # save_networks(available_networks)  # RIMOSSO: non scrivere più su file
            break
        else:
            print_formatted_text(f"[PY][{ser.port}] Inserisci nuove credenziali per questa scheda:")
            new_ssid = prompt(f"[{ser.port}] Nuovo SSID: ").strip()
            new_pwd = prompt(f"[{ser.port}] Nuova PASSWORD: ").strip()
            # Aggiorna la lista reti e riprova
            available_networks[idx] = (new_ssid, new_pwd)
            # save_networks(available_networks)  # RIMOSSO: non scrivere più su file
            ssid, pwd = new_ssid, new_pwd
            net_idx = idx
            # Se la nuova rete è già assegnata a un altro Arduino, si riprova
            if ssid in assigned_ssids:
                print_formatted_text(f"[PY][{ser.port}] ⚠️ Questa rete è già assegnata a un altro Arduino. Scegli una rete diversa.")
                continue
            ok = try_connect_wifi(ser, ssid, pwd)
            if ok:
                assigned_ssids.add(ssid)
                break

 

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
for idx, ser in enumerate(arduinos):
    connect_arduino(idx, ser, available_networks, assigned_ssids)



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