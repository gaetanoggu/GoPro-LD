import asyncio
from bleak import BleakClient, BleakScanner

# UUID dai tuoi dati
DATA_CHARS = [
    "15172002-4947-11e9-8646-d663bd873d93",
    "15172003-4947-11e9-8646-d663bd873d93",
    "15172004-4947-11e9-8646-d663bd873d93",
]
CONFIG_CHAR = "15172005-4947-11e9-8646-d663bd873d93"

# Callback per ricevere i dati
def data_handler(sender, data):
    print(f"Dati ricevuti da {sender}: {data}")

async def main():
    # Scansione dei dispositivi
    print("🔍 Scansione dispositivi Movella DOT...")
    devices = await BleakScanner.discover()
    dot_device = None
    for d in devices:
        if d.name and "Movella DOT" in d.name:
            dot_device = d
            break

    if not dot_device:
        print("❌ Nessun Movella DOT trovato")
        return

    print(f"✅ Trovato dispositivo: {dot_device.name} ({dot_device.address})")

    async with BleakClient(dot_device.address) as client:
        # Controllo connessione
        if not client.is_connected:
            print("❌ Connessione fallita")
            return
        print(f"🔗 Connessione stabilita con {dot_device.name}")

        # Imposta il sensore a 120 Hz
        # Il valore preciso dipende dal dispositivo: qui è un esempio di 1 byte = 120
        freq_value = bytearray([120])  # oppure [0x78] = 120 decimale
        await client.write_gatt_char(CONFIG_CHAR, freq_value)
        print(f"⚙️ Configurazione inviata su {CONFIG_CHAR} (120 Hz)")

        # Abilita notifiche su tutte le caratteristiche dati
        for char_uuid in DATA_CHARS:
            try:
                await client.start_notify(char_uuid, data_handler)
                print(f"✅ Notifiche abilitate su {char_uuid}")
            except Exception as e:
                print(f"❌ Errore notifiche su {char_uuid}: {e}")

        # Attendi qualche secondo per ricevere i dati
        print("📡 Ricezione dati in corso... Premi Ctrl+C per terminare")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("⏹️ Terminata ricezione dati")

        # Disabilita notifiche prima di uscire
        for char_uuid in DATA_CHARS:
            try:
                await client.stop_notify(char_uuid)
            except:
                pass

asyncio.run(main())
