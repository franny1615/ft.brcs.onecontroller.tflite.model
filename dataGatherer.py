import asyncio
import struct
import sys
import numpy as np
from collections import deque
from bleak import BleakClient, BleakScanner

from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import threading

# === UUIDs ===
DEVICE_NAME = "FT-ONE-C"
EMG_DATA_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
STREAMING_UUID = "6d6d871d-1579-467a-9a99-b36622b79a09"
CALIB_STATUS_UUID = "87654321-4321-4321-4321-ba0987654321"

# === Buffer settings ===
WINDOW_SIZE = 500
QUEUE_MAX = 5000
Y_AXIS_MAXIMUM = 100

incoming_queue = deque(maxlen=QUEUE_MAX)

# === Global control ===
loop = None
stop_event = None
ble_thread = None


class EMGPlotter:
    def __init__(self):
        self.app = QtWidgets.QApplication(sys.argv)

        pg.setConfigOptions(useOpenGL=True)

        self.win = pg.GraphicsLayoutWidget(show=True, title="Real-Time EMG")
        self.win.closeEvent = self.on_close  # 🔥 hook close event

        self.plot = self.win.addPlot(title="EMG Signal")

        # Lock axes
        self.plot.setYRange(0, Y_AXIS_MAXIMUM)
        self.plot.setXRange(0, WINDOW_SIZE)
        self.plot.enableAutoRange(False)

        self.curve = self.plot.plot(pen='y')

        # Circular buffer
        self.data = np.zeros(WINDOW_SIZE, dtype=np.int32)
        self.index = 0
        self.full = False

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(30)

    def add_data(self, value):
        self.data[self.index] = value
        self.index = (self.index + 1) % WINDOW_SIZE

        if self.index == 0:
            self.full = True

    def get_ordered_data(self):
        if not self.full:
            return self.data[:self.index]

        return np.concatenate((
            self.data[self.index:],
            self.data[:self.index]
        ))

    def update_plot(self):
        # Drain queue safely in UI thread - Limit drain to avoid UI lockup
        processed = 0
        while incoming_queue and processed < QUEUE_MAX:
            self.add_data(incoming_queue.popleft())
            processed += 1

        if processed > 0:
            self.curve.setData(self.get_ordered_data(), _callSync='off')

    # 🔥 CRITICAL: clean shutdown hook
    def on_close(self, event):
        print("Shutting down cleanly...")

        global loop, stop_event

        try:
            if loop and not loop.is_closed() and stop_event:
                loop.call_soon_threadsafe(stop_event.set)
        except RuntimeError:
            pass

        event.accept()

    def run(self):
        self.app.exec()


plotter = EMGPlotter()


# === BLE Notification Handler ===
def notification_handler(sender, data):
    if len(data) >= 4:
        value = struct.unpack("<i", data[:4])[0]
        incoming_queue.append(value)


def calib_status_handler(sender, data):
    status = data.decode("utf-8").strip('\0')
    print(f"Calibration Status: {status}")


# === BLE Logic ===
async def ble_task():
    global stop_event
    stop_event = asyncio.Event()

    print("Scanning for device...")
    device = None

    while not stop_event.is_set():
        devices = await BleakScanner.discover(timeout=5.0)
        for d in devices:
            if d.name == DEVICE_NAME:
                device = d
                break
        
        if device:
            break
        
        print("Device not found, retrying...")
        await asyncio.sleep(1)

    if stop_event.is_set():
        return

    print(f"Connecting to {device.name} ({device.address})")

    async def connect_and_stream():
        disconnected_event = asyncio.Event()

        def disconnected_callback(client):
            print("Disconnected callback called!")
            disconnected_event.set()

        async with BleakClient(device.address, disconnected_callback=disconnected_callback) as client:
            print("Connected")

            await client.start_notify(EMG_DATA_UUID, notification_handler)
            await client.start_notify(CALIB_STATUS_UUID, calib_status_handler)
            print("Notifications enabled")

            await client.write_gatt_char(STREAMING_UUID, b"\x01")
            print("Streaming started")

            # Wait for either user stop or spontaneous disconnect
            done, pending = await asyncio.wait(
                [
                    asyncio.create_task(stop_event.wait()),
                    asyncio.create_task(disconnected_event.wait())
                ],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in pending:
                task.cancel()

            print("Stopping stream...")
            try:
                if client.is_connected:
                    await client.write_gatt_char(STREAMING_UUID, b"\x00")
                    await client.stop_notify(EMG_DATA_UUID)
                    await client.stop_notify(CALIB_STATUS_UUID)
            except Exception as e:
                print("Cleanup error (likely already disconnected):", e)

    while not stop_event.is_set():
        try:
            await connect_and_stream()
        except Exception as e:
            print(f"Connection error: {e}")
        
        if not stop_event.is_set():
            print("Attempting to reconnect in 3 seconds...")
            await asyncio.sleep(3)


# === Run everything ===
def main():
    global loop, ble_thread

    loop = asyncio.new_event_loop()

    def run_loop():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ble_task())
        finally:
            loop.close()

    ble_thread = threading.Thread(target=run_loop)
    ble_thread.start()

    plotter.run()

    # 🔥 CRITICAL: wait for BLE thread before process exits
    print("Waiting for BLE thread to finish...")
    ble_thread.join(timeout=2)


if __name__ == "__main__":
    main()