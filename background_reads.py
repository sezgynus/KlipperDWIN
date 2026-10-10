"""Bounded background I/O; callers consume Futures on the UI owner."""
from concurrent.futures import Future
from queue import Empty, Full, Queue
from threading import Event, Thread
from moonraker_client import MoonrakerError


class ReadPending(Exception):
    pass


class ReadWorker:
    def __init__(self, timeout=5, capacity=32):
        self.timeout = timeout
        self._queue = Queue(maxsize=capacity)
        self._stop = Event()
        self._thread = Thread(target=self._run, name='moonraker-reads', daemon=True)
        self._thread.start()

    def submit(self, work):
        future = Future()
        if self._stop.is_set():
            future.set_exception(MoonrakerError('Read worker is closed'))
            return future
        try:
            self._queue.put_nowait((future, work))
        except Full:
            future.set_exception(MoonrakerError('Read queue is full'))
        return future

    def _run(self):
        while not self._stop.is_set():
            try:
                future, work = self._queue.get(timeout=.1)
            except Empty:
                continue
            try:
                if not self._stop.is_set() and future.set_running_or_notify_cancel():
                    try:
                        future.set_result(work())
                    except Exception as error:
                        future.set_exception(error)
                elif not future.done():
                    future.cancel()
            finally:
                self._queue.task_done()

    def close(self):
        self._stop.set()
        while True:
            try:
                future, _ = self._queue.get_nowait()
            except Empty:
                break
            future.cancel()
            self._queue.task_done()
        self._thread.join(timeout=self.timeout + 1)
