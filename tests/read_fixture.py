"""Immediate deterministic I/O fixture; worker behavior has separate tests."""
from concurrent.futures import Future


class ImmediateReadWorker:
    def __init__(self, *args, **kwargs):
        pass

    def submit(self, work, queue_timeout=None):
        future = Future()
        try:
            future.set_result(work())
        except Exception as error:
            future.set_exception(error)
        return future

    def close(self):
        pass
