import serial
import threading

# MODIFICA QUI: le porte reali degli Arduino
PORTE = ["COM5", "COM8"]  # <-- cambia con le due porte giuste
BAUD = 115200

arduinos = []
ready_events = []

def read_arduino(ser, ready_event):
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                if line == "READY":
                    print(f"[{ser.port}] ✅ Pronta!")
                    ready_event.set()
                elif line in ["STARTED", "STOPPED"]:
                    print(f"[{ser.port}] {line}")
                else:
                    print(f"[{ser.port}] -> {line}")  # debug extra
        except Exception as e:
            print(f"[{ser.port}] Errore lettura: {e}")
            break

# Apri solo le porte scelte
for porta in PORTE:
    try:
        ser = serial.Serial(porta, BAUD, timeout=1)
        arduinos.append(ser)
        event = threading.Event()
        ready_events.append(event)
        threading.Thread(target=read_arduino, args=(ser, event), daemon=True).start()
        print(f"[{porta}] Aperta con successo.")
    except Exception as e:
        print(f"[{porta}] ❌ Errore apertura: {e}")

if not arduinos:
    print("❌ Nessun Arduino aperto!")
    exit()

# Aspetta che siano pronti
print("⌛ Attendo che tutte le GoPro siano pronte...")
for event in ready_events:
    event.wait()
print("✅ Tutte le GoPro sono pronte!")

# Comandi da tastiera
print("👉 Premi 'a' per START, 's' per STOP, 'q' per uscire.")

while True:
    cmd = input().lower().strip()
    if cmd == "a":
        for ser in arduinos:
            print(f"[{ser.port}] 🚀 Invio START...")
            ser.write(b"START\r\n")
            ser.flush
