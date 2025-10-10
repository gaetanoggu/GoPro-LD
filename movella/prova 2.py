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
STOP_CMD = b'\x01\x00\x06'

# Percorso Desktop
desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")


class MovellaDevice:
    def __init__(self, name, address):
        self.name = name
        self.address = address
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = os.path.join(desktop_path, f"{name}_data_{timestamp}.txt")
        self.client = BleakClient(address)
        self.data_char = None
        self.data_received = False

    def notification_handler(self, sender, data):
        """Callback per pacchetti BLE"""
        self.data_received = True
        hex_data = data.hex(" ")
        with open(self.output_file, "a") as f:
            f.write(f"{datetime.now().isoformat()} | {hex_data}\n")
        print(f"📡 {self.name} [{sender}] -> {hex_data}")


async def activate_configuration(device: MovellaDevice):
    client = device.client
    for char_uuid in CONFIG_CHARS:
        try:
            await client.write_gatt_char(char_uuid, b'\x01', response=True)
            print(f"⚙️ Configurazione inviata su {device.name} ({char_uuid})")
            return True
        except Exception:
            continue
    print(f"⚠️ Nessuna caratteristica di configurazione ha funzionato per {device.name}")
    return False


async def find_data_characteristic(device: MovellaDevice):
    client = device.client
    for char_uuid in DATA_CHARS:
        try:
            await client.start_notify(char_uuid, device.notification_handler)
            device.data_received = False
            await client.write_gatt_char(CONTROL_CHAR_UUID, START_CMD, response=True)
            await asyncio.sleep(3)  # attesa per ricevere pacchetti
            if device.data_received:
                print(f"✅ Dati ricevuti da {device.name} ({char_uuid})")
                await client.write_gatt_char(CONTROL_CHAR_UUID, STOP_CMD, response=True)
                await client.stop_notify(char_uuid)
                device.data_char = char_uuid
                return char_uuid
            await client.stop_notify(char_uuid)
        except Exception:
            continue
    print(f"❌ Nessuna caratteristica dati funzionante su {device.name}")
    return None


async def start_device(device: MovellaDevice):
    """Avvia raccolta dati su un singolo dispositivo"""
    if device.data_char is None:
        print(f"⚠️ Nessuna caratteristica dati per {device.name}, impossibile avviare.")
        return
    await device.client.start_notify(device.data_char, device.notification_handler)
    await device.client.write_gatt_char(CONTROL_CHAR_UUID, START_CMD, response=True)
    print(f"🏁 Acquisizione avviata su {device.name}")


async def stop_device(device: MovellaDevice):
    """Ferma raccolta dati su un singolo dispositivo"""
    if device.data_char is None:
        return
    await device.client.write_gatt_char(CONTROL_CHAR_UUID, STOP_CMD, response=True)
    await device.client.stop_notify(device.data_char)
    print(f"🛑 Acquisizione fermata su {device.name}")


async def manage_input(devices):
    loop = asyncio.get_event_loop()

    # Start raccolta dati
    while True:
        cmd = await loop.run_in_executor(None, input, ">>> Digita 'a' per avviare raccolta dati su tutti i dispositivi: ")
        if cmd.strip().lower() == "a":
            await asyncio.gather(*(start_device(dev) for dev in devices))
            break
        else:
            print("⚠️ Digita 'a' per iniziare l'acquisizione")

    # Stop raccolta dati
    while True:
        cmd = await loop.run_in_executor(None, input, ">>> Digita 's' per fermare raccolta dati su tutti i dispositivi: ")
        if cmd.strip().lower() == "s":
            await asyncio.gather(*(stop_device(dev) for dev in devices))
            break
        else:
            print("⚠️ Digita 's' per fermare l'acquisizione")


async def main():
    print("🔍 Scansione dispositivi Movella DOT...")
    devices_found = await BleakScanner.discover(timeout=6.0)
    dot_devices = [d for d in devices_found if d.name and "DOT" in d.name]

    if not dot_devices:
        print("❌ Nessun dispositivo Movella DOT trovato.")
        return

    devices = [MovellaDevice(d.name, d.address) for d in dot_devices]
    print(f"✅ Trovati {len(devices)} dispositivi Movella DOT")

    # Connessione e setup per ciascun dispositivo
    for device in devices:
        await device.client.connect()
        print(f"🔗 Connessione stabilita con {device.name}")

        # Bleak >=0.20 effettua automaticamente la discovery dei servizi
        services = list(device.client.services)
        print(f"📝 {device.name} ha {len(services)} servizi disponibili")

        await activate_configuration(device)
        await find_data_characteristic(device)
        print(f"💾 Dati di {device.name} salvati in '{device.output_file}'")

    # Gestione input start/stop
    await manage_input(devices)

    # Disconnessione
    for device in devices:
        await device.client.disconnect()
        print(f"🔌 Dispositivo {device.name} disconnesso")

    print("✅ Raccolta dati terminata per tutti i dispositivi.")


if __name__ == "__main__":
    asyncio.run(main())
