"""On-demand TMC register diagnostics, independent of homing and driver enable.

Klipper DUMP_TMC returns actual register reads via gcode_response notifications,
not in the Moonraker script RPC result. Only an exact, bounded, current reply
from a cursor captured BEFORE dispatch may become information evidence.
No motor movement, enables, driver writes, register writes, or physical PASS.
"""
import re

# TMC2660 READRSP selection changes a hardware register, so keep it on the
# original passive status path rather than silently claim a read-only dump.
_DIRECT_CHIPS = frozenset(('tmc2130', 'tmc2208', 'tmc2209',
                           'tmc2240', 'tmc5160', 'tmc5161'))
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}\Z')
_REGISTER = re.compile(r'^\s*(?:(?://|echo:)\s*)?DRV_STATUS:\s*([0-9a-fA-F]{8})(?:\s|$)', re.I)
_FAULT_BITS = (
    ('otpw', 0), ('ot', 1), ('s2ga', 2), ('s2gb', 3),
    ('s2vsa', 4), ('s2vsb', 5), ('t120', 8), ('t143', 9),
    ('t150', 10), ('t157', 11),
)
_OPEN_LOAD = (('ola', 6), ('olb', 7))
_KNOWN_2208_MASK = (sum(1 << bit for _, bit in _FAULT_BITS + _OPEN_LOAD)
                    | (31 << 16) | (1 << 30) | (1 << 31))


def direct_query(device):
    if not isinstance(device, str):
        return None
    chip, separator, stepper = device.partition(' ')
    if not separator or chip not in _DIRECT_CHIPS or not _NAME.fullmatch(stepper):
        return None
    return 'DUMP_TMC STEPPER=' + stepper + ' REGISTER=DRV_STATUS'


def register_evidence(messages, device):
    """Parse one unambiguous direct register reply, never generic console text."""
    if direct_query(device) is None or not isinstance(messages, (tuple, list)):
        return ()
    values = []
    for message in messages[:256]:
        if not isinstance(message, str) or len(message) > 4096:
            return ()
        for line in message.splitlines()[:32]:
            match = _REGISTER.fullmatch(line.strip()) or _REGISTER.match(line)
            if match:
                values.append(int(match.group(1), 16))
                if len(values) > 1:
                    return ()  # Concurrent console dumps cannot be attributed.
    if len(values) != 1:
        return ()
    raw = values[0]
    chip = device.partition(' ')[0]
    evidence = [('register', 'DRV_STATUS'), ('register_hex', '%08X' % raw)]
    if chip == 'tmc2208':
        if raw & ~_KNOWN_2208_MASK:
            return tuple(evidence + [('decode', 'unknown register bits')])
        faults = tuple(name for name, bit in _FAULT_BITS if raw & (1 << bit))
        open_load = tuple(name for name, bit in _OPEN_LOAD if raw & (1 << bit))
        evidence.extend((('fault_count', len(faults)),
                         ('faults', ','.join(faults) or 'none reported'),
                         ('standstill', (raw >> 31) & 1),
                         ('cs_actual', (raw >> 16) & 31),
                         ('stealth', (raw >> 30) & 1)))
        if open_load:
            evidence.append(('open_load_flags', ','.join(open_load)))
    else:
        # Register layouts differ by TMC chip; never reuse 2208 fault masks.
        evidence.append(('decode', 'chip-specific interpretation required'))
    return tuple(evidence)


def register_error(messages):
    """Only recognize firmware communication errors; no raw console exposure."""
    if not isinstance(messages, (tuple, list)):
        return False
    for value in messages[:256]:
        if isinstance(value, str) and len(value) <= 4096 and any(
                phrase in value.lower() for phrase in
                ('unable to read tmc uart', 'unable to read tmc spi',
                 'unknown register name')):
            return True
    return False
