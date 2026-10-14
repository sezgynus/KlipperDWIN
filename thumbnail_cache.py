"""UI-owned volatile SRAM cache with one asynchronous thumbnail loader."""
from collections import OrderedDict
from concurrent.futures import Future
from threading import Thread
import logging
import time

from thumbnail_preview import load_preview
from preview_metadata import PreviewData


class ThumbnailCache:
    capacity = 32768

    def __init__(self, client, loader=None):
        self.client = client
        self.loader = loader or self._load_async
        self.entries = OrderedDict()
        self.details = OrderedDict()
        self.errors = {}
        self.retry_at = {}
        self.valid = set()
        self.priority = ()
        self.epoch = None
        self.generation = 0
        self.job = None
        self.upload = None

    def _load_async(self, key):
        future = Future()
        def work():
            try:
                future.set_result(load_preview(self.client, key[0], size=key[4]) if len(key)>4 else load_preview(self.client, key[0]))
            except Exception as error:
                future.set_exception(error)
        Thread(target=work, name='thumbnail-loader', daemon=True).start()
        return future

    def sync(self, epoch, valid, priority):
        if epoch != self.epoch:
            self.epoch = epoch
            self.generation += 1
            self.entries.clear()
            self.details.clear()
            self.errors.clear()
            self.retry_at.clear()
            self.upload = None
        self.valid = set(valid)
        priority = tuple(key for key in priority if key in self.valid)[:5]
        if priority != self.priority:
            self.errors = {key: value for key, value in self.errors.items() if value != 'LCD cache full'}
        self.priority = priority
        for key in tuple(self.entries):
            if key not in self.valid:
                del self.entries[key]
        self.errors = {key: value for key, value in self.errors.items() if key in self.valid}
        self.details = OrderedDict((key, value) for key, value in self.details.items() if key in self.valid)
        self.retry_at = {key: value for key, value in self.retry_at.items() if key in self.errors}
        if self.upload and self.upload['key'] not in self.valid:
            self.upload = None

    def address(self, key, touch=False):
        entry = self.entries.get(key)
        if entry is not None:
            if touch:
                self.entries.move_to_end(key)
            return entry[0]
        return None

    def has_work(self):
        return bool(self.job or self.upload or any(
            key not in self.entries and key not in self.errors for key in self.priority))

    def _hole(self, size):
        address = 0
        for start, length in sorted(self.entries.values()):
            if start-address >= size:
                return address
            address = start+length
        return address if self.capacity-address >= size else None

    def _reserve(self, key, size, foreground):
        while True:
            address = self._hole(size)
            if address is not None:
                return address
            # Background loading cannot evict an earlier file in the visible order.
            protected = set(self.priority[:self.priority.index(key)]) if key in self.priority else set()
            victim = next((item for item in self.entries if item not in self.priority), None)
            if victim is None:
                victim = next((item for item in reversed(self.priority)
                               if item in self.entries and (foreground or item not in protected)), None)
            if victim is None:
                return None
            del self.entries[victim]
            self.details.pop(victim, None)

    def tick(self, lcd, foreground=None, chunks=2):
        """Transfer at most `chunks` packets; publish only complete SRAM entries."""
        if foreground is not None and (foreground not in self.valid or foreground in self.entries):
            return
        if self.upload:
            key = self.upload['key']
            if (foreground is not None and key != foreground) or (foreground is None and key not in self.priority):
                self.upload = None
        if self.job and self.job[1].done():
            key, future, generation = self.job
            self.job = None
            if generation == self.generation and key in self.valid:
                try:
                    data = future.result()
                    if isinstance(data, PreviewData):
                        self.details[key] = data.details
                        self.details.move_to_end(key)
                        while len(self.details) > 64:
                            victim = next((item for item in self.details if item not in self.entries and item not in self.priority), None)
                            if victim is None:
                                break
                            del self.details[victim]
                        data = data.jpeg
                        if data is None:
                            raise ValueError('No thumbnail')
                    if not isinstance(data, bytes) or not 0 < len(data) <= self.capacity:
                        raise ValueError('Invalid JPEG size')
                    # Drop an obsolete preload before allocating or writing any bytes.
                    if key == foreground or (foreground is None and key in self.priority):
                        address = self._reserve(key, len(data), key == foreground)
                        if address is None:
                            raise ValueError('LCD cache full')
                        self.upload = dict(key=key, data=data, address=address, index=0,
                                           started=time.monotonic())
                except Exception as error:
                    self.errors[key] = str(error)
                    if str(error) != 'LCD cache full':
                        self.retry_at[key] = time.monotonic()+10.0
                    logging.info('Thumbnail cache unavailable %s: %s', key[0], error)
            else:
                # Consume the exception as well as successful stale results.
                try:
                    future.result()
                except Exception:
                    pass
        if self.upload:
            task = self.upload
            stop = min(len(task['data']), task['index']+chunks*128)
            for offset in range(task['index'], stop, 128):
                lcd.write_sram(task['address']+offset, task['data'][offset:min(offset+128, stop)])
            task['index'] = stop
            if stop == len(task['data']):
                self.entries[task['key']] = (task['address'], stop)
                self.errors.pop(task['key'], None)
                self.upload = None
                logging.info('Thumbnail %s: UART JPEG upload %.3fs (%d bytes), SRAM address %d',
                             task['key'][0], time.monotonic()-task['started'], stop, task['address'])
            return
        if self.job is None:
            candidates = (foreground,) if foreground is not None else self.priority
            for key in candidates:
                if key in self.retry_at and time.monotonic() >= self.retry_at[key]:
                    self.errors.pop(key, None)
                    self.retry_at.pop(key, None)
            key = next((key for key in candidates
                        if key not in self.entries and key not in self.errors and key in self.valid), None)
            if key is not None:
                self.job = (key, self.loader(key), self.generation)
