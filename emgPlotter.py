import numpy as np
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg

# === Settings ===
WINDOW_SIZE = 1000
REFRESH_MS = 16  # ~60 FPS


class EMGPlotter(QtWidgets.QMainWindow):
    def __init__(self, data_source):
        super().__init__()
        self.data_source = data_source
        self.setWindowTitle("Real-Time EMG and Raw Envelope Plot")

        # Create a central layout
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        # Configure EMG graph
        self.emgWidget = pg.PlotWidget()
        layout.addWidget(self.emgWidget)
        self.emgWidget.setBackground("w")
        self.emgWidget.setTitle("EMG Signal (Filtered)", color="k", size="14pt")
        self.emgWidget.setLabel("left", "Amplitude")
        self.emgWidget.setLabel("bottom", "Samples")
        self.emgWidget.showGrid(x=True, y=True)
        self.emgWidget.setYRange(0, 100)

        # Configure Raw Envelope graph
        self.rawWidget = pg.PlotWidget()
        layout.addWidget(self.rawWidget)
        self.rawWidget.setBackground("w")
        self.rawWidget.setTitle("Raw Envelope", color="k", size="14pt")
        self.rawWidget.setLabel("left", "Amplitude")
        self.rawWidget.setLabel("bottom", "Samples")
        self.rawWidget.showGrid(x=True, y=True)
        # Enable auto-scaling for raw as it might vary more
        self.rawWidget.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)

        # Initialize data
        self.x = np.arange(WINDOW_SIZE)
        self.y_emg = np.zeros(WINDOW_SIZE, dtype=np.int32)
        self.y_raw = np.zeros(WINDOW_SIZE, dtype=np.int32)

        # Plot lines
        pen_emg = pg.mkPen(color=(255, 0, 0), width=1)
        self.emg_data_line = self.emgWidget.plot(self.x, self.y_emg, pen=pen_emg)

        pen_raw = pg.mkPen(color=(0, 0, 255), width=1)
        self.raw_data_line = self.rawWidget.plot(self.x, self.y_raw, pen=pen_raw)

        # Update timer
        self.timer = QtCore.QTimer()
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.update_plot_data)
        self.timer.start()

    def update_plot_data(self):
        with self.data_source.value_lock:
            val_emg = self.data_source.latest_value
            val_raw = self.data_source.latest_raw_value

        # Update EMG data
        self.y_emg = np.roll(self.y_emg, -1)
        self.y_emg[-1] = val_emg
        self.emg_data_line.setData(self.x, self.y_emg)

        # Update Raw data
        self.y_raw = np.roll(self.y_raw, -1)
        self.y_raw[-1] = val_raw
        self.raw_data_line.setData(self.x, self.y_raw)

    def closeEvent(self, event):
        print("Shutting down cleanly...")
        loop = self.data_source.loop
        stop_event = self.data_source.stop_event
        if loop and stop_event:
            # Signal the ble_task to stop
            loop.call_soon_threadsafe(stop_event.set)
        event.accept()
