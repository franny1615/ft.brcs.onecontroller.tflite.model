import asyncio
import struct
from bleak import BleakClient, BleakScanner

# === UUIDs ===
DEVICE_NAME = "FT-ONE-C"
EMG_DATA_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
RAW_ENVELOPE_UUID = "43218765-4321-4321-4321-1234567890cd"
STREAMING_UUID = "6d6d871d-1579-467a-9a99-b36622b79a09"
CALIB_STATUS_UUID = "87654321-4321-4321-4321-ba0987654321"

# === BLE Notification Handlers ===
def notification_handler(sender, data, data_source):
    if len(data) >= 4:
        value = struct.unpack("<i", data[:4])[0]
        with data_source.value_lock:
            data_source.latest_value = value

def raw_envelope_handler(sender, data, data_source):
    if len(data) >= 4:
        value = struct.unpack("<i", data[:4])[0]
        with data_source.value_lock:
            data_source.latest_raw_value = value

def calib_status_handler(sender, data):
    status = data.decode("utf-8").strip('\0')
    print(f"Calibration Status: {status}")

# === BLE Logic ===
async def ble_task(data_source):
    data_source.stop_event = asyncio.Event()

    print("Scanning for device...")
    device = await BleakScanner.find_device_by_filter(lambda d, ad: d.name == DEVICE_NAME)
    
    if not device:
        print("Device not found.")
        return

    print(f"Connecting to {device.name} ({device.address})")
    
    async def connect_and_stream():
        disconnected_event = asyncio.Event()
        def disconnected_callback(client):
            print("Disconnected!")
            disconnected_event.set()

        async with BleakClient(device.address, disconnected_callback=disconnected_callback) as client:
            print("Connected")
            # Partial binding for the data_source
            handler = lambda s, d: notification_handler(s, d, data_source)
            raw_handler = lambda s, d: raw_envelope_handler(s, d, data_source)
            await client.start_notify(EMG_DATA_UUID, handler)
            await client.start_notify(RAW_ENVELOPE_UUID, raw_handler)
            await client.start_notify(CALIB_STATUS_UUID, calib_status_handler)
            await client.write_gatt_char(STREAMING_UUID, b"\x01")
            print("Streaming started")

            # Wait until stopped or disconnected
            done, pending = await asyncio.wait(
                [asyncio.create_task(data_source.stop_event.wait()), asyncio.create_task(disconnected_event.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()

            print("Stopping stream...")
            try:
                if client.is_connected:
                    await client.write_gatt_char(STREAMING_UUID, b"\x00")
            except:
                pass

    while not data_source.stop_event.is_set():
        try:
            await connect_and_stream()
        except Exception as e:
            print(f"Connection error: {e}")
        if not data_source.stop_event.is_set():
            await asyncio.sleep(3)
