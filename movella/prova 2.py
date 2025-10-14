import asyncio
from bleak import BleakClient, BleakScanner
from datetime import datetime
import os
import struct

# ===== UUID principali =====
CONTROL_CHAR_UUID = "15172001-4947-11e9-8646-d663bd873d93"
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

START_CMD = b'\x01\x01\x06'
STOP_CMD = b'\x01\x00\x06'

desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")


class MovellaDevice:
    def __init__(self, name, address):
        self.name = name
        self.address = address
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_address = address.replace(":", "")
        self.output_file = os.path.join(desktop_path, f"{name}_{safe_address}_data_{timestamp}.csv")
        self.client = BleakClient(address)
        self.data_char = None
        self.recording = False  # <--- nuova variabile
        self.data_received = False

        # Scriviamo l'intestazione delle colonne se il file non esiste
        if not os.path.exists(self.output_file):
            with open(self.output_file, "w") as f:
                f.write("timestamp,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n")

    def notification_handler(self, sender, data):
        self.data_received = True
        if not self.recording:  # <--- ignora dati se non registriamo
            return
        try:
            float_values = struct.unpack('<' + 'f'*(len(data)//4), data)
            with open(self.output_file, "a") as f:
                f.write(f"{datetime.now().isoformat()},{','.join(map(str, float_values))}\n")
            print(f"📡 {self.name} [{sender}] -> {float_values}")
        except struct.error:
            print(f"⚠️ Errore nel decodificare i dati da {self.name}")


async def activate_configuration(device: MovellaDevice):
    for char_uuid in CONFIG_CHARS:
        try:
            await device.client.write_gatt_char(char_uuid, b'\x01', response=True)
            print(f"⚙️ Configurazione inviata su {device.name} ({char_uuid})")
            return True
        except Exception:
            continue
    print(f"⚠️ Nessuna caratteristica di configurazione ha funzionato per {device.name}")
    return False


async def find_data_characteristic(device: MovellaDevice):
    for char_uuid in DATA_CHARS:
        try:
            # In questa fase testiamo la ricezione senza registrazione
            await device.client.start_notify(char_uuid, lambda s, d: setattr(device, 'data_received', True))
            await device.client.write_gatt_char(CONTROL_CHAR_UUID, START_CMD, response=True)
            await asyncio.sleep(3)
            if device.data_received:
                await device.client.write_gatt_char(CONTROL_CHAR_UUID, STOP_CMD, response=True)
                await device.client.stop_notify(char_uuid)
                device.data_char = char_uuid
                print(f"✅ Dati ricevuti da {device.name} ({char_uuid})")
                return char_uuid
            await device.client.stop_notify(char_uuid)
        except Exception:
            continue
    print(f"❌ Nessuna caratteristica dati funzionante su {device.name}")
    return None


async def start_device(device: MovellaDevice):
    if device.data_char is None:
        print(f"⚠️ Nessuna caratteristica dati per {device.name}")
        return
    device.recording = True  # <--- iniziamo registrazione
    await device.client.start_notify(device.data_char, device.notification_handler)
    await device.client.write_gatt_char(CONTROL_CHAR_UUID, START_CMD, response=True)
    print(f"🏁 Acquisizione avviata su {device.name}")


async def stop_device(device: MovellaDevice):
    if device.data_char is None:
        return
    await device.client.write_gatt_char(CONTROL_CHAR_UUID, STOP_CMD, response=True)
    await device.client.stop_notify(device.data_char)
    device.recording = False  # <--- fermiamo registrazione
    print(f"🛑 Acquisizione fermata su {device.name}")


async def manage_input(devices):
    loop = asyncio.get_event_loop()

    while True:
        cmd = await loop.run_in_executor(None, input, ">>> Digita 'a' per avviare raccolta dati su tutti i dispositivi: ")
        if cmd.strip().lower() == "a":
            await asyncio.gather(*(start_device(d) for d in devices))
            break
        print("⚠️ Digita 'a' per iniziare")

    while True:
        cmd = await loop.run_in_executor(None, input, ">>> Digita 's' per fermare raccolta dati su tutti i dispositivi: ")
        if cmd.strip().lower() == "s":
            await asyncio.gather(*(stop_device(d) for d in devices))
            break
        print("⚠️ Digita 's' per fermare")


async def main():
    print("🔍 Scansione dispositivi Movella DOT...")
    devices_found = await BleakScanner.discover(timeout=6.0)
    dot_devices = [d for d in devices_found if d.name and "DOT" in d.name]

    if not dot_devices:
        print("❌ Nessun dispositivo Movella DOT trovato.")
        return

    devices = [MovellaDevice(d.name, d.address) for d in dot_devices]
    print(f"✅ Trovati {len(devices)} dispositivi Movella DOT")

    for device in devices:
        await device.client.connect()
        print(f"🔗 Connessione stabilita con {device.name}")
        services = list(device.client.services)
        print(f"📝 {device.name} ha {len(services)} servizi disponibili")
        await activate_configuration(device)
        await find_data_characteristic(device)
        print(f"💾 Dati di {device.name} salvati in '{device.output_file}'")

    await manage_input(devices)

    for device in devices:
        await device.client.disconnect()
        print(f"🔌 Dispositivo {device.name} disconnesso")

    print("✅ Raccolta dati terminata per tutti i dispositivi.")


if __name__ == "__main__":
    asyncio.run(main())
