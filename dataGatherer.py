import asyncio
import struct
import sys
import numpy as np
from bleak import BleakClient, BleakScanner
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import threading

# === UUIDs ===
DEVICE_NAME = "FT-ONE-C"
EMG_DATA_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
STREAMING_UUID = "6d6d871d-1579-467a-9a99-b36622b79a09"
CALIB_STATUS_UUID = "87654321-4321-4321-4321-ba0987654321"

# === Settings ===
WINDOW_SIZE = 1000
REFRESH_MS = 16  # ~60 FPS

latest_value = 0
value_lock = threading.Lock()
loop = None
stop_event = None

class EMGPlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-Time EMG Plot")
        
        # Configure graph
        self.graphWidget = pg.PlotWidget()
        self.setCentralWidget(self.graphWidget)
        self.graphWidget.setBackground("w")
        self.graphWidget.setTitle("EMG Signal", color="k", size="14pt")
        self.graphWidget.setLabel("left", "Amplitude")
        self.graphWidget.setLabel("bottom", "Samples")
        self.graphWidget.showGrid(x=True, y=True)
        self.graphWidget.setYRange(0, 100)
        
        # Initialize data
        self.x = np.arange(WINDOW_SIZE)
        self.y = np.zeros(WINDOW_SIZE, dtype=np.int32)
        
        # Plot line
        pen = pg.mkPen(color=(255, 0, 0), width=1)
        self.data_line = self.graphWidget.plot(self.x, self.y, pen=pen)
        
        # Update timer
        self.timer = QtCore.QTimer()
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.update_plot_data)
        self.timer.start()

    def update_plot_data(self):
        global latest_value
        with value_lock:
            val = latest_value

        # Roll existing data back and append the latest value
        self.y = np.roll(self.y, -1)
        self.y[-1] = val

        # Update the graph
        self.data_line.setData(self.x, self.y)

    def closeEvent(self, event):
        print("Shutting down cleanly...")
        global loop, stop_event
        if loop and stop_event:
            # Signal the ble_task to stop
            loop.call_soon_threadsafe(stop_event.set)
        event.accept()

# === BLE Notification Handlers ===
def notification_handler(sender, data):
    global latest_value
    if len(data) >= 4:
        value = struct.unpack("<i", data[:4])[0]
        with value_lock:
            latest_value = value

def calib_status_handler(sender, data):
    status = data.decode("utf-8").strip('\0')
    print(f"Calibration Status: {status}")

# === BLE Logic ===
async def ble_task():
    global stop_event
    stop_event = asyncio.Event()

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
            await client.start_notify(EMG_DATA_UUID, notification_handler)
            await client.start_notify(CALIB_STATUS_UUID, calib_status_handler)
            await client.write_gatt_char(STREAMING_UUID, b"\x01")
            print("Streaming started")

            # Wait until stopped or disconnected
            done, pending = await asyncio.wait(
                [asyncio.create_task(stop_event.wait()), asyncio.create_task(disconnected_event.wait())],
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

    while not stop_event.is_set():
        try:
            await connect_and_stream()
        except Exception as e:
            print(f"Connection error: {e}")
        if not stop_event.is_set():
            await asyncio.sleep(3)

def main():
    global loop
    app = QtWidgets.QApplication(sys.argv)
    plotter = EMGPlotter()
    plotter.show()

    loop = asyncio.new_event_loop()
    def run_loop():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ble_task())
        finally:
            loop.close()

    ble_thread = threading.Thread(target=run_loop, daemon=False)
    ble_thread.start()

    exit_code = app.exec()
    
    # Ensure the thread finishes before the process exits
    if ble_thread.is_alive():
        # Set stop_event just in case it wasn't set through UI
        if loop and stop_event:
            loop.call_soon_threadsafe(stop_event.set)
        ble_thread.join(timeout=2.0)
        
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
