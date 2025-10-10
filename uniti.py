import subprocess
import threading
import sys
import time
import keyboard

# Frasi chiave per riconoscere quando i due script sono pronti
READY_MOVELLA = ">>> Digita 'a' per avviare"
READY_ARDUINO = "Comandi: 'a'=START"

movella_ready = False
arduino_ready = False

def reader(process, name):
    """Legge continuamente l'output di un processo e mostra su console"""
    global movella_ready, arduino_ready

    for line in iter(process.stdout.readline, b''):
        decoded = line.decode(errors="ignore").rstrip()
        print(f"[{name}] {decoded}")

        # Controlla se i processi sono pronti
        if READY_MOVELLA in decoded:
            movella_ready = True
        if READY_ARDUINO in decoded:
            arduino_ready = True

        # quando entrambi pronti -> notifica
        if movella_ready and arduino_ready:
            print("\n✅ Entrambi gli script sono pronti! Premi 'a' per avviare!\n")

# Avvia entrambi gli script come sottoprocessi con output catturato
movella = subprocess.Popen(
    ["python", "prova 1.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    stdin=subprocess.PIPE,
)

arduino = subprocess.Popen(
    ["python", "goproManager.py"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    stdin=subprocess.PIPE,
)

# Thread per leggere gli output in tempo reale
threading.Thread(target=reader, args=(movella, "MOVELLA"), daemon=True).start()
threading.Thread(target=reader, args=(arduino, "ARDUINO"), daemon=True).start()

print("🚀 Avvio in corso... Attendi che entrambi dicano che puoi premere 'a'.")

try:
    while True:
        # Quando entrambi pronti, permetti di premere 'a' o 's'
        if movella_ready and arduino_ready:
            if keyboard.is_pressed('a'):
                print("🏁 Avvio simultaneo inviato!")
                for p in [movella, arduino]:
                    p.stdin.write(b"a\n")
                    p.stdin.flush()
                movella_ready = False
                arduino_ready = False  # reset
                time.sleep(1)

            elif keyboard.is_pressed('s'):
                print("🛑 Stop simultaneo inviato!")
                for p in [movella, arduino]:
                    p.stdin.write(b"s\n")
                    p.stdin.flush()
                time.sleep(1)

        time.sleep(0.2)

except KeyboardInterrupt:
    print("\n🔌 Interruzione manuale, chiusura processi...")
    movella.terminate()
    arduino.terminate()
    sys.exit(0)
