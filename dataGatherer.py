import asyncio
import sys
import threading
from PyQt6 import QtWidgets
from emgPlotter import EMGPlotter
from bleConnector import ble_task

# === Shared State ===
latest_value = 0
value_lock = threading.Lock()
stop_event = None
loop = None

def main():
    global loop
    app = QtWidgets.QApplication(sys.argv)
    
    # Pass this module (containing shared state) to plotter and BLE task
    data_source = sys.modules[__name__]
    plotter = EMGPlotter(data_source)
    plotter.show()

    loop = asyncio.new_event_loop()
    def run_loop():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ble_task(data_source))
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
