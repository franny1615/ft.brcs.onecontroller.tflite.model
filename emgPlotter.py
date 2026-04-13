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
        with self.data_source.value_lock:
            val = self.data_source.latest_value

        # Roll existing data back and append the latest value
        self.y = np.roll(self.y, -1)
        self.y[-1] = val

        # Update the graph
        self.data_line.setData(self.x, self.y)

    def closeEvent(self, event):
        print("Shutting down cleanly...")
        loop = self.data_source.loop
        stop_event = self.data_source.stop_event
        if loop and stop_event:
            # Signal the ble_task to stop
            loop.call_soon_threadsafe(stop_event.set)
        event.accept()
