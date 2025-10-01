
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
                    print_formatted_text(f"[{ser.port}] ✅ Pronta!")
                elif line in ["STARTED", "STOPPED"]:
                    print_formatted_text(f"[{ser.port}] {line}")
                elif line in ["CONNECTED", "DISCONNECTED"]:
                    print_formatted_text(f"[{ser.port}] Stato WiFi: {line}")
                else:
                    print_formatted_text(f"[{ser.port}] -> {line}")  # debug extra
        except Exception as e:
            print_formatted_text(f"[{ser.port}] ❌ Errore lettura: {e}")
            break

# -----------------------
# FUNZIONE PER INVIAR COMANDO
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
# APERTURA PORTE
# -----------------------
for porta in PORTE:
    try:
        ser = serial.Serial(porta, BAUD, timeout=1)
        arduinos.append(ser)
        threading.Thread(target=read_arduino, args=(ser,), daemon=True).start()
        print_formatted_text(f"[{porta}] Aperta con successo.")
    except Exception as e:
        print_formatted_text(f"[{porta}] ❌ Errore apertura: {e}")

if not arduinos:
    print_formatted_text("❌ Nessun Arduino aperto!")
    exit()

# -----------------------
# THREAD MONITOR STATUS
# -----------------------
threading.Thread(target=monitor_status, args=(arduinos,), daemon=True).start()

# -----------------------
# COMANDI DA TASTIERA
# -----------------------

print_formatted_text("👉 Comandi disponibili: 'a' = START, 's' = STOP, 'q' = USCITA, 'status' = Mostra stato WiFi")

# Usa patch_stdout per evitare che le print si sovrappongano all'input
with patch_stdout():
    while True:
        cmd = prompt('> ', bottom_toolbar="Scrivi un comando: 'a'=START, 's'=STOP, 'status', 'q'=USCITA").lower().strip()
        if cmd == "a":
            print_formatted_text("🚀 START tutte le GoPro...")
            send_command(arduinos, "START")
        elif cmd == "s":
            print_formatted_text("🛑 STOP tutte le GoPro...")
            send_command(arduinos, "STOP")
        elif cmd == "status":
            send_command(arduinos, "STATUS")
        elif cmd == "q":
            print_formatted_text("🔌 Chiusura connessioni...")
            break
        else:
            print_formatted_text("⚠️ Comando non valido. Usa 'a', 's', 'status' o 'q'.")

# -----------------------
# CHIUSURA SERIALI
# -----------------------
for ser in arduinos:
    ser.close()
print_formatted_text("✅ Connessioni chiuse.")
