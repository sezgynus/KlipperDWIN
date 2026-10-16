# Class to monitor a rotary encoder and update a value using gpiozero + LGPIOFactory.
from gpiozero import Device, RotaryEncoder
from gpiozero.pins.lgpio import LGPIOFactory
from threading import Lock

# Use LGPIO as pin factory to avoid RPi.GPIO edge detection issues

class Encoder:

    def __init__(self, leftPin, rightPin, callback=None):
        if Device.pin_factory is None:
            Device.pin_factory = LGPIOFactory()
        self.value = 0
        self.state = '00'
        self.direction = None
        self.callback = callback
        self._right_events = self._left_events = 0
        self.lock = Lock()  # thread-safe update

        # Rotary encoder
        self.encoder = RotaryEncoder(a=leftPin, b=rightPin, max_steps=0)
        self.encoder.when_rotated = self._rotated

    def _rotated(self):
        with self.lock:
            value = self.encoder.steps
            delta = value - self.value
            if not delta:
                return
            if delta>0:
                self._right_events = getattr(self,'_right_events',0)+delta
            else:
                self._left_events = getattr(self,'_left_events',0)-delta
            self.direction = 'R' if delta > 0 else 'L'
            self.value = value
            # Callback only enqueues input, and retains event ordering.
            if self.callback is not None:
                self.callback(value)

    # Keep for compatibility, not used in gpiozero
    def transitionOccurred(self, channel):
        pass

    def getValue(self):
        with self.lock:
            return self.value

    def diagnostics(self):
        with self.lock:
            return {'gpio_positive_steps':getattr(self,'_right_events',0),
                    'gpio_negative_steps':getattr(self,'_left_events',0)}

    def close(self):
        self.callback = None
        self.encoder.close()
