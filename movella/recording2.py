import asyncio
import sys
import os
import time
import threading
from bleak import BleakScanner, BleakClient

# Aggiungi il percorso del modulo personalizzato
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from movella_dot_py.core.sensor import MovellaDOTSensor
from movella_dot_py.models.data_structures import SensorConfiguration
from movella_dot_py.models.enums import OutputRate, FilterProfile, PayloadMode

# Variabile condivisa per controllare l'avvio e lo stop del recording
recording_flag = {"recording": False, "stop": False}

def keyboard_listener():
    """Thread che ascolta i tasti 'a' e 's'."""
    print("\nPremi 'a' per iniziare la registrazione, 's' per fermarla.")
    while True:
        key = input().strip().lower()
        if key == 'a':
            if not recording_flag["recording"]:
                print("\n>>> Avvio registrazione richiesto...")
                recording_flag["recording"] = True
            else:
                print("Registrazione già in corso.")
        elif key == 's':
            if recording_flag["recording"]:
                print("\n>>> Stop registrazione richiesto...")
                recording_flag["stop"] = True
                break
            else:
                print("Nessuna registrazione in corso.")
        else:
            print("Premi 'a' per avviare, 's' per fermare.")

async def main():
    # Avvia il thread che ascolta la tastiera
    threading.Thread(target=keyboard_listener, daemon=True).start()

    # Scansione BLE
    print("Scanning for Movella DOT sensors (5 seconds)...")
    devices = await BleakScanner.discover(timeout=5.0)
    dot_devices = [d for d in devices if d.name and "Movella DOT" in d.name]
    
    if not dot_devices:
        print("Nessun sensore Movella DOT trovato")
        return

    max_sensors = 5
    dot_devices = dot_devices[:max_sensors]
    print(f"Trovati {len(dot_devices)} sensori Movella DOT")

    sensors = []
    config = SensorConfiguration(
        output_rate=OutputRate.RATE_120,
        filter_profile=FilterProfile.DYNAMIC,
        payload_mode=PayloadMode.CUSTOM_MODE_5
    )

    # Connessione e configurazione sensori
    for device in dot_devices:
        try:
            sensor = MovellaDOTSensor(config)
            sensor.client = BleakClient(device.address)
            print(f"\nConnessione a {device.name} ({device.address})...")
            await sensor.client.connect()
            sensor.is_connected = True
            sensor._device_address = device.address
            sensor._device_name = device.name

            print("\nLettura informazioni del dispositivo...")
            device_info = await sensor.get_device_info()
            sensor._device_tag = device_info.device_tag
            print(f"MAC: {device_info.mac_address}")
            print(f"Firmware: {device_info.firmware_version}")
            print(f"Serial: {device_info.serial_number}")
            print(f"Product: {device_info.product_code}")
            print(f"Tag: {device_info.device_tag}")
            print(f"Output Rate: {device_info.output_rate} Hz")
            print(f"Filter Profile: {device_info.filter_profile.name}")

            await sensor.identify_sensor()
            await asyncio.sleep(2)

            await sensor.configure_sensor()
            sensors.append(sensor)
            print(f"Connesso e configurato {device.name}")

        except Exception as e:
            print(f"Errore connessione {device.name}: {str(e)}")

    if not sensors:
        print("Nessun sensore connesso correttamente.")
        return

    try:
        # Attendi pressione di 'a' per iniziare la registrazione
        print("\nIn attesa di 'a' per avviare la registrazione...")
        while not recording_flag["recording"]:
            await asyncio.sleep(0.2)

        print("\nAvvio registrazione su tutti i sensori...")
        await asyncio.gather(*(sensor.start_recording() for sensor in sensors))

        # Attendi pressione di 's' per fermare la registrazione
        while not recording_flag["stop"]:
            await asyncio.sleep(0.2)

        print("\nArresto registrazione...")
        await asyncio.gather(*(sensor.stop_recording() for sensor in sensors))

        # Mostra riassunto dei dati
        for sensor in sensors:
            print(f"\n--- Sensor Data Summary ---")
            data = sensor.get_collected_data()
            if data:
                print(f"Device: {data['device_tag']}")
                print(f"MAC: {data['mac_address']}")
                timestamps = data['timestamps']
                euler_angles = data['euler_angles']
                if len(timestamps) > 0:
                    print(f"Campioni raccolti: {len(timestamps)}")
                    print(f"Durata: {(timestamps[-1] - timestamps[0])/1e6:.2f} s")
                    if euler_angles:
                        print(f"Primi euler angles: {euler_angles[0]}")
                        print(f"Ultimi euler angles: {euler_angles[-1]}")
                else:
                    print("Nessun dato raccolto.")

    except Exception as e:
        print(f"Errore durante la registrazione: {str(e)}")
    finally:
        print("\nDisconnessione di tutti i sensori...")
        await asyncio.gather(*(sensor.disconnect() for sensor in sensors))

if __name__ == "__main__":
    asyncio.run(main())
