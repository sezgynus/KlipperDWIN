"""Observe the printer relay independently of Klipper readiness and UART health."""
import time
from background_reads import ReadWorker


class PowerMonitor:
    def __init__(self, client, device):
        self.client, self.device = client, device.casefold()
        self.worker = ReadWorker(client.timeout, capacity=1)
        self.future = None
        self.next_poll = 0
        self.status = None

    def poll(self):
        if self.future is not None and self.future.done():
            future, self.future = self.future, None
            try:
                devices = future.result().get('result', {}).get('devices', [])
                status = next((item.get('status') for item in devices
                               if str(item.get('device', '')).casefold() == self.device), None)
                self.status = status if status in ('on', 'off') else None
            except Exception:
                # A failed read is unknown, never evidence that power is off.
                self.status = None
        now = time.monotonic()
        if self.future is None and now >= self.next_poll:
            self.future = self.worker.submit(lambda: self.client.get('/machine/device_power/devices'))
            self.next_poll = now + 1.0
        return self.status

    def close(self):
        self.worker.close()
