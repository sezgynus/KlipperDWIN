"""Live software-stack and Raspberry Pi network information."""
import socket
import struct
import os
import re
import subprocess

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux/Raspberry Pi runtime
    fcntl = None

SIOCGIFFLAGS = 0x8913
SIOCGIFADDR = 0x8915
IFF_UP = 0x1
IFF_LOOPBACK = 0x8


def network_info():
    """Return (status, IPv4) for the first active non-loopback IPv4 interface."""
    if fcntl is None:
        return 'Unknown', 'Unavailable'
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for _, name in socket.if_nameindex():
            encoded = name.encode('utf-8')[:15]
            try:
                request = struct.pack('256s', encoded)
                flags = struct.unpack('H', fcntl.ioctl(sock.fileno(), SIOCGIFFLAGS, request)[16:18])[0]
                if not flags & IFF_UP or flags & IFF_LOOPBACK:
                    continue
                address = socket.inet_ntoa(
                    fcntl.ioctl(sock.fileno(), SIOCGIFADDR, request)[20:24])
                return 'Online', address
            except OSError:
                continue
    finally:
        sock.close()
    return 'Offline', 'Unavailable'


def updater_version(version_info, name, full=False):
    item = version_info.get(name, {})
    if not isinstance(item, dict):
        return 'Unavailable'
    if full:
        value = item.get('full_version_string') or item.get('version')
    else:
        value = item.get('version') or item.get('full_version_string')
    return str(value) if value else 'Unavailable'


def host_metrics():
    """Return lightweight Linux host CPU usage and thermal-zone temperature."""
    cpu = None
    temp = None
    try:
        load1 = os.getloadavg()[0]
        count = os.cpu_count() or 1
        cpu = max(0.0, min(100.0, load1 * 100.0 / count))
    except (OSError, AttributeError):
        pass
    for path in ('/sys/class/thermal/thermal_zone0/temp',
                 '/sys/class/hwmon/hwmon0/temp1_input'):
        try:
            with open(path, 'r', encoding='ascii') as stream:
                value = float(stream.read().strip())
            temp = value / 1000.0 if value > 1000 else value
            break
        except (OSError, ValueError):
            continue
    return cpu, temp


def host_memory_usage():
    """Used RAM percentage, excluding reclaimable cache via MemAvailable."""
    try:
        with open('/proc/meminfo', 'r', encoding='ascii') as stream:
            values = {}
            for line in stream:
                key, _, value = line.partition(':')
                if key in ('MemTotal', 'MemAvailable'):
                    values[key] = int(value.split()[0])
        total, available = values['MemTotal'], values['MemAvailable']
        if total <= 0 or not 0 <= available <= total:
            return None
        return (total - available) * 100.0 / total
    except (OSError, UnicodeError, ValueError, KeyError, IndexError):
        return None


def wifi_info():
    """Read associated Wi-Fi SSID/RSSI with bounded commands (worker only)."""
    try:
        devices = subprocess.run(['iw', 'dev'], capture_output=True, text=True,
                                 timeout=1, check=True).stdout
        for name in re.findall(r'^\s*Interface (\S+)', devices, re.MULTILINE):
            link = subprocess.run(['iw', 'dev', name, 'link'], capture_output=True,
                                  text=True, timeout=1, check=True).stdout
            ssid = re.search(r'^\s*SSID: (.*)$', link, re.MULTILINE)
            if ssid:
                signal = re.search(r'^\s*signal: (-?\d+(?:\.\d+)?) dBm', link, re.MULTILINE)
                return ssid.group(1), float(signal.group(1)) if signal else None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return 'Unavailable', None
    return 'Disconnected', None


def wifi_signal_text(rssi):
    """Compact signal description fitting the Info value column."""
    if rssi is None:
        return 'N/A'
    level = 'Strong' if rssi >= -60 else 'Medium' if rssi >= -70 else 'Poor'
    return '{:.0f} dBm ({})'.format(rssi, level)
