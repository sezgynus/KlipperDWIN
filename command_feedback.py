"""UI command result tracking; transport acceptance is not physical completion."""
import time
import math


class CommandFeedback:
    def __init__(self, future, label, epoch, expected=None, confirmation_timeout=300.0):
        self.future, self.label, self.epoch, self.expected = future, label, epoch, expected
        # None is reserved for state-driven operations, such as a print
        # cancellation queued behind a blocking START_PRINT M109. Other
        # commands retain bounded acknowledgement/confirmation deadlines.
        self.confirmation_timeout = (None if confirmation_timeout is None
                                     else float(confirmation_timeout))
        if self.confirmation_timeout is None:
            if expected is None:
                raise ValueError('Unbounded feedback requires an expected state')
        elif (not math.isfinite(self.confirmation_timeout)
              or self.confirmation_timeout <= 0):
            raise ValueError('Confirmation timeout must be positive')
        self.started = time.monotonic()
        self.phase = 'waiting'
        self.message = 'Waiting: ' + label

    def update(self, state, unavailable=False):
        if self.phase != 'waiting':
            return self.phase
        if unavailable or not state.ready or state.epoch != self.epoch:
            self.phase, self.message = 'error', 'Connection changed; check printer'
        elif self.confirmation_timeout is None and self.expected():
            # Authoritative state wins even when Moonraker's RPC response is
            # still queued behind the macro. Release the pending RPC slot.
            if not self.future.done():
                self.future.cancel()
            self.phase, self.message = 'accepted', 'Accepted: ' + self.label
        elif (self.confirmation_timeout is not None
              and time.monotonic() - self.started >
              (30 if self.expected is None else self.confirmation_timeout)):
            pending = not self.future.done()
            self.future.cancel()
            self.phase = 'error'
            self.message = ('Result unconfirmed; check printer' if pending or self.expected is None
                            else 'State unconfirmed; check printer')
        elif self.future.done():
            if self.future.cancelled():
                self.phase, self.message = 'error', 'Command cancelled; check printer'
            elif self.future.exception():
                self.phase, self.message = 'error', 'Command failed; check log'
            elif self.expected is None or self.expected():
                self.phase, self.message = 'accepted', 'Accepted: ' + self.label
        return self.phase
