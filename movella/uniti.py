import asyncio
import threading
import time
import sys
import os
import serial
from bleak import BleakScanner, BleakClient
from prompt_toolkit import prompt
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import print_formatted_text

# ============================================================
# CONFIGURAZIONE GoPro / Arduino
# ============================================================
PORTE = ["COM5", "COM15", "COM8"]
BAUD = 115200
STATUS_INTERVAL = 5

arduinos = []
arduino_states = {}
state_lock = threading.Lock()

# ============================================================
# CONFIGURAZIONE Movella
# ============================================================
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from movella_dot_py.core.sensor import MovellaDOTSensor
from movella_dot_py.models.data_structures import SensorConfiguration
from movella_dot_py.models.enums import OutputRate, FilterProfile, PayloadMode

# ============================================================
# EVENTI DI SINCRONIZZAZIONE
# ============================================================
start_event = threading.Event()
stop_event = threading.Event()

# ============================================================
# THREAD LETTURA SERIAL
# ============================================================
def read_arduino(ser):
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

# ============================================================
# FILE RETI WIFI
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
                    ssid, pwd = parts
                    nets.append((ssid.strip(), pwd.strip()))
    except FileNotFoundError:
        print_formatted_text(f"❌ File {filename} non trovato.")
    return nets

def connect_arduino(ser, ssid, pwd, timeout=20):
    ser.reset_input_buffer()
    print_formatted_text(f"[PY][{ser.port}] 🔗 Connessione a '{ssid}'...")
    start = time.time()
    last_sent = None
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
            print_formatted_text(f"[PY][{ser.port}] ❌ Connessione fallita")
            return False
        time.sleep(0.2)
    print_formatted_text(f"[PY][{ser.port}] ⏰ Timeout connessione")
    return False

# ============================================================
# APERTURA PORTE SERIAL
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
    sys.exit(1)

available_networks = load_networks()
for idx, ser in enumerate(arduinos):
    if idx >= len(available_networks):
        print_formatted_text(f"[PY][{ser.port}] ⚠ Nessuna rete assegnata.")
        continue
    ssid, pwd = available_networks[idx]
    connect_arduino(ser, ssid, pwd)

# ============================================================
# MOVELLA MANAGER
# ============================================================
async def movella_manager():
    print("\n🔍 Scansione sensori Movella DOT (5s)...")
    devices = await BleakScanner.discover(timeout=5.0)
    dot_devices = [d for d in devices if d.name and "Movella DOT" in d.name]

    if not dot_devices:
        print("❌ Nessun sensore Movella DOT trovato.")
        return

    print(f"📡 Trovati {len(dot_devices)} sensori Movella DOT")

    config = SensorConfiguration(
        output_rate=OutputRate.RATE_120,
        filter_profile=FilterProfile.DYNAMIC,
        payload_mode=PayloadMode.CUSTOM_MODE_5
    )

    sensors = []

    # Connessione in sequenza (più stabile su Windows)
    for device in dot_devices:
        try:
            print(f"\n🔗 Connessione a {device.name} ({device.address})...")
            sensor = MovellaDOTSensor(config)
            sensor.client = BleakClient(device.address)
            await sensor.client.connect()

            # ⚠ attesa critica per stabilizzare il BLE
            await asyncio.sleep(2.5)

            if not sensor.client.is_connected:
                raise Exception("Connessione BLE non riuscita")

            sensor.is_connected = True
            sensor._device_address = device.address
            sensor._device_name = device.name

            # Tentativi multipli di configurazione
            for attempt in range(3):
                try:
                    await sensor.configure_sensor()
                    print(f"✅ {device.name} configurato correttamente.")
                    sensors.append(sensor)
                    break
                except Exception as e:
                    print(f"⚠️ Tentativo {attempt+1} fallito: {e}")
                    await asyncio.sleep(1.5)
            else:
                raise Exception("Configurazione fallita dopo 3 tentativi")

        except Exception as e:
            print(f"❌ Errore connessione {device.name}: {e}")
            try:
                if sensor.client.is_connected:
                    await sensor.client.disconnect()
            except:
                pass

    if not sensors:
        print("❌ Nessun sensore configurato correttamente.")
        return

    print(f"\n✅ {len(sensors)} sensori Movella connessi correttamente.\n")

    # Attesa del comando START
    print("⏳ In attesa di START (tasto 'a')...")
    while not start_event.is_set():
        await asyncio.sleep(0.05)

    print("\n🚀 START simultaneo GoPro + Movella...")
    send_command(arduinos, "START")
    await asyncio.gather(*(s.start_recording() for s in sensors))

    # Attesa comando STOP
    while not stop_event.is_set():
        await asyncio.sleep(0.05)

    print("\n🛑 STOP simultaneo...")
    send_command(arduinos, "STOP")
    await asyncio.gather(*(s.stop_recording() for s in sensors))

    print("\n🔌 Disconnessione sensori...")
    for s in sensors:
        try:
            if s.client.is_connected:
                await s.client.disconnect()
        except Exception as e:
            print(f"Errore disconnessione {s._device_name}: {e}")

    print("✅ Tutti i sensori disconnessi.")

# ============================================================
# INTERFACCIA COMANDI
# ============================================================
def command_interface():
    print_formatted_text("[PY] 👉 Comandi: 'a'=START, 's'=STOP, 'q'=USCITA")
    with patch_stdout():
        while True:
            cmd = prompt("> ").lower().strip()
            if cmd == "a":
                print("[PY] 🚀 Avvio simultaneo richiesto...")
                start_event.set()
            elif cmd == "s":
                print("[PY] 🛑 Stop simultaneo richiesto...")
                stop_event.set()
                break
            elif cmd == "q":
                print("[PY] 🔌 Uscita forzata.")
                break
            else:
                print("[PY] ⚠ Comando non valido.")

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    cli_thread = threading.Thread(target=command_interface, daemon=True)
    cli_thread.start()
    asyncio.run(movella_manager())
    for ser in arduinos:
        ser.close()
    print("[PY] ✅ Tutto chiuso correttamente.")
