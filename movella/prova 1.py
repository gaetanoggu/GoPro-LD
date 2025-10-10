import asyncio
from bleak import BleakClient, BleakScanner
from datetime import datetime
import os

# ===== UUID principali =====
CONTROL_CHAR_UUID = "15172001-4947-11e9-8646-d663bd873d93"  # scrittura comandi
DATA_CHARS = [
    "15172002-4947-11e9-8646-d663bd873d93",
    "15172003-4947-11e9-8646-d663bd873d93",
    "15172004-4947-11e9-8646-d663bd873d93",
]
CONFIG_CHARS = [
    "15172005-4947-11e9-8646-d663bd873d93",
    "15174001-4947-11e9-8646-d663bd873d93",
    "15174002-4947-11e9-8646-d663bd873d93",
    "15177001-4947-11e9-8646-d663bd873d93",
]

# Comandi
START_CMD = b'\x01\x01\x06'
STOP_CMD  = b'\x01\x00\x06'

# File output
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
output_file = os.path.join(desktop_path, f"movella_data_{timestamp}.txt")

data_received = False

def notification_handler(sender, data):
    """Callback per pacchetti BLE"""
    global data_received
    data_received = True
    hex_data = data.hex(" ")
    with open(output_file, "a") as f:
        f.write(f"{datetime.now().isoformat()} | {hex_data}\n")
    print(f"📡 {datetime.now().strftime('%H:%M:%S')} [{sender}] -> {hex_data}")

async def activate_configuration(client):
    """Prova tutte le caratteristiche di configurazione finché una funziona"""
    for char_uuid in CONFIG_CHARS:
        try:
            await client.write_gatt_char(char_uuid, b'\x01', response=True)
            print(f"⚙️ Configurazione inviata su {char_uuid}")
            return True
        except Exception:
            continue
    print("⚠️ Nessuna caratteristica di configurazione ha funzionato")
    return False

async def find_data_characteristic(client):
    """Prova tutte le caratteristiche dati finché una invia pacchetti"""
    global data_received
    for char_uuid in DATA_CHARS:
        try:
            await client.start_notify(char_uuid, notification_handler)
            print(f"✅ Notifiche attivate su {char_uuid}")
            # Prova start per vedere se arrivano dati
            data_received = False
            await client.write_gatt_char(CONTROL_CHAR_UUID, START_CMD, response=True)
            await asyncio.sleep(3)
            if data_received:
                print(f"✅ Dati ricevuti da {char_uuid}")
                await client.write_gatt_char(CONTROL_CHAR_UUID, STOP_CMD, response=True)
                return char_uuid
            await client.stop_notify(char_uuid)
        except Exception:
            continue
    return None

async def read_user_input(client, data_char):
    """Gestisce input utente asincrono per start/stop con 'a' e 's'"""
    loop = asyncio.get_event_loop()
    
    # Attendere 'a' per avviare acquisizione
    while True:
        cmd = await loop.run_in_executor(None, input, ">>> Digita 'a' per avviare: ")
        if cmd.strip().lower() == "a":
            await client.write_gatt_char(CONTROL_CHAR_UUID, START_CMD, response=True)
            await client.start_notify(data_char, notification_handler)
            print("🏁 Acquisizione avviata...")
            break
        else:
            print("⚠️ Digita 'a' per iniziare l'acquisizione")

    # Loop per fermare con 's' solamente
    while True:
        cmd = await loop.run_in_executor(None, input, ">>> Digita 's' per fermare: ")
        if cmd.strip().lower() == "s":
            await client.write_gatt_char(CONTROL_CHAR_UUID, STOP_CMD, response=True)
            await client.stop_notify(data_char)
            print("🛑 Acquisizione fermata.")
            break
        else:
            print("⚠️ Digita 's' per fermare l'acquisizione")

async def main():
    print("🔍 Scansione dispositivi Movella DOT...")
    devices = await BleakScanner.discover(timeout=6.0)
    dot_device = next((d for d in devices if d.name and "DOT" in d.name), None)

    if not dot_device:
        print("❌ Nessun dispositivo Movella DOT trovato.")
        return

    print(f"✅ Trovato Movella DOT: {dot_device.name} [{dot_device.address}]")

    async with BleakClient(dot_device.address) as client:
        print("🔗 Connessione stabilita!")

        # Attiva configurazione se necessaria
        await activate_configuration(client)

        # Trova caratteristica dati funzionante
        data_char = await find_data_characteristic(client)
        if not data_char:
            print("❌ Nessuna caratteristica dati ha prodotto pacchetti.")
            return

        print(f"💾 Salvataggio dati in tempo reale su '{output_file}'")
        print("⏱️ Gestione start/stop tramite input utente ('a' per start, 's' per stop)")

        await read_user_input(client, data_char)

        print("✅ Raccolta dati terminata.")

asyncio.run(main())
