"""Bounded background I/O; callers consume Futures on the UI owner."""
from concurrent.futures import Future
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic
import math
from moonraker_client import MoonrakerError


class ReadPending(Exception):
    pass


class ReadWorker:
    def __init__(self, timeout=5, capacity=32, queue_timeout=None):
        self.timeout = timeout
        self.queue_timeout = timeout if queue_timeout is None else queue_timeout
        self._queue = Queue(maxsize=capacity)
        self._stop = Event()
        self._thread = Thread(target=self._run, name='moonraker-reads', daemon=True)
        self._thread.start()

    def submit(self, work, queue_timeout=None):
        """Expire stale queued work before starting I/O; execution has its own timeout."""
        future = Future()
        wait = self.queue_timeout if queue_timeout is None else queue_timeout
        if not math.isfinite(wait) or wait < 0:
            future.set_exception(MoonrakerError('Invalid read admission timeout'))
            return future
        if self._stop.is_set():
            future.set_exception(MoonrakerError('Read worker is closed'))
            return future
        try:
            deadline = monotonic() + wait
            self._queue.put_nowait((future, work, deadline))
        except Full:
            future.set_exception(MoonrakerError('Read queue is full'))
        return future

    def _run(self):
        while not self._stop.is_set():
            try:
                future, work, deadline = self._queue.get(timeout=.1)
            except Empty:
                continue
            try:
                if not self._stop.is_set() and future.set_running_or_notify_cancel():
                    try:
                        if monotonic() >= deadline:
                            raise MoonrakerError('Read expired before execution')
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
                future, _, _ = self._queue.get_nowait()
            except Empty:
                break
            future.cancel()
            self._queue.task_done()
        self._thread.join(timeout=self.timeout + 1)
