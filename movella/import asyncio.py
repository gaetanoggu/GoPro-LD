import asyncio
from bleak import BleakClient, BleakScanner

async def list_notify_characteristics(client, name):
    print(f"\n🔍 Scansione caratteristiche per {name}")
    # Assicurati di ottenere i servizi prima di iterare
    await client.get_services()
    for service in client.services:
        print(f"Servizio: {service.uuid}")
        for char in service.characteristics:
            props = ",".join(char.properties)
            print(f"  Caratteristica: {char.uuid}  Proprietà: {props}")
            if "notify" in char.properties:
                try:
                    print(f"    ⚡ Provo NOTIFY su {char.uuid} (5s)")
                    def handler(sender, data):
                        print(f"📡 Dati ricevuti da {char.uuid}: {data[:20]}...")  # primi byte
                    await client.start_notify(char.uuid, handler)
                    await asyncio.sleep(5)
                    await client.stop_notify(char.uuid)
                except Exception as e:
                    print(f"    ❌ Errore su {char.uuid}: {e}")

async def main():
    print("🔍 Scansione dispositivi Movella DOT...")
    devices_found = await BleakScanner.discover(timeout=6.0)
    dot_devices = [d for d in devices_found if d.name and "DOT" in d.name]

    if not dot_devices:
        print("❌ Nessun dispositivo Movella DOT trovato.")
        return

    for d in dot_devices:
        print(f"\n🔗 Connessione a {d.name} ({d.address})")
        async with BleakClient(d.address) as client:
            await list_notify_characteristics(client, d.name)

if __name__ == "__main__":
    asyncio.run(main())

 