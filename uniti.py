import asyncio
import threading
import time
import serial
from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text
from bleak import BleakScanner, BleakClient
import sys, os

# =============== CONFIGURAZIONE GOPRO ===============
PORTE = ["COM5", "COM15", "COM8"]
BAUD = 115200

# =============== CONFIGURAZIONE MOVELLA ===============
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from movella_dot_py.core.sensor import MovellaDOTSensor
from movella_dot_py.models.data_structures import SensorConfiguration
from movella_dot_py.models.enums import OutputRate, FilterProfile, PayloadMode

# ====================================================
# THREAD DI LETTURA ARDUINO (come nel tuo codice)
# ====================================================
arduinos = []
arduino_states = {}
state_lock = threading.Lock()

def read_arduino(ser):
    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue
            print_formatted_text(f"[COM][{ser.port}] -> {line}")
        except Exception as e:
            print_formatted_text(f"[COM][{ser.port}] ❌ Errore lettura: {e}")
            time.sleep(1)

def send_command(ser_list, cmd):
    for ser in ser_list:
        try:
            ser.write((cmd + "\n").encode())
            ser.flush()
        except Exception as e:
            print_formatted_text(f"[{ser.port}] ❌ Errore invio comando: {e}")

# ====================================================
# CLASSE GESTORE MOVELLA (asincrona)
# ====================================================
class MovellaManager:
    def __init__(self):
        self.sensors = []
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_loop, daemon=True)
        self.thread.start()

    def _start_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _connect_sensors(self):
        print("🔍 Scansione sensori Movella (5s)...")
        devices = await BleakScanner.discover(timeout=5.0)
        dot_devices = [d for d in devices if d.name and "Movella DOT" in d.name][:5]
        if not dot_devices:
            print("❌ Nessun sensore Movella trovato")
            return
        
        config = SensorConfiguration(
            output_rate=OutputRate.RATE_120,
            filter_profile=FilterProfile.DYNAMIC,
            payload_mode=PayloadMode.CUSTOM_MODE_5
        )

        for device in dot_devices:
            try:
                sensor = MovellaDOTSensor(config)
                sensor.client = BleakClient(device.address)
                print(f"🔗 Connessione a {device.name}...")
                await sensor.client.connect()
                await sensor.configure_sensor()
                self.sensors.append(sensor)
                print(f"✅ {device.name} connesso e configurato")
            except Exception as e:
                print(f"⚠️ Errore connessione {device.name}: {e}")

    def connect_sensors(self):
        return asyncio.run_coroutine_threadsafe(self._connect_sensors(), self.loop)

    async def _start_recording(self):
        if not self.sensors:
            print("⚠️ Nessun sensore connesso.")
            return
        print("🎬 Avvio registrazione sensori Movella...")
        await asyncio.gather(*(s.start_recording() for s in self.sensors))

    async def _stop_recording(self):
        if not self.sensors:
            return
        print("🛑 Stop registrazione sensori Movella...")
        await asyncio.gather(*(s.stop_recording() for s in self.sensors))

    def start_recording(self):
        return asyncio.run_coroutine_threadsafe(self._start_recording(), self.loop)

    def stop_recording(self):
        return asyncio.run_coroutine_threadsafe(self._stop_recording(), self.loop)

# ====================================================
# INIZIALIZZAZIONE
# ====================================================
# 1️⃣ Apre le porte seriali Arduino
for porta in PORTE:
    try:
        ser = serial.Serial(porta, BAUD, timeout=1)
        time.sleep(2)
        arduinos.append(ser)
        threading.Thread(target=read_arduino, args=(ser,), daemon=True).start()
        print_formatted_text(f"[PY][{porta}] Aperta con successo.")
    except Exception as e:
        print_formatted_text(f"[PY][{porta}] ❌ Errore apertura: {e}")

if not arduinos:
    print_formatted_text("[PY] ❌ Nessun Arduino aperto!")
    exit()

# 2️⃣ Avvia il gestore Movella
movella = MovellaManager()
movella.connect_sensors()

# ====================================================
# INTERFACCIA COMANDI
# ====================================================
print_formatted_text("[PY] 👉 Comandi: 'a'=START, 's'=STOP, 'q'=USCITA")

with patch_stdout():
    while True:
        cmd = prompt('> ').lower().strip()
        if cmd == "a":
            print_formatted_text("🚀 Avvio GoPro + Movella...")
            send_command(arduinos, "START")
            movella.start_recording()
        elif cmd == "s":
            print_formatted_text("🛑 Stop GoPro + Movella...")
            send_command(arduinos, "STOP")
            movella.stop_recording()
        elif cmd == "q":
            print_formatted_text("🔌 Chiusura...")
            break
        else:
            print_formatted_text("⚠️ Comando non valido.")

# ====================================================
# CHIUSURA
# ====================================================
for ser in arduinos:
    ser.close()
print_formatted_text("[PY] ✅ Connessioni chiuse.")
