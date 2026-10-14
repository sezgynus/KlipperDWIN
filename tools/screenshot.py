#!/usr/bin/env python3
"""Capture the running service's completed DWIN framebuffer over local IPC."""
import argparse
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dwin_emulator.runtime import default_socket


def capture(socket_path, file_format='png', frame=False):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect(str(Path(socket_path).expanduser()))
        connection.sendall(json.dumps({'command': 'screenshot', 'format': file_format, 'frame': frame}).encode() + b'\n')
        response = bytearray()
        while not response.endswith(b'\n'):
            chunk = connection.recv(4096)
            if not chunk or len(response) + len(chunk) > 65536:
                raise RuntimeError('Incomplete screenshot response')
            response.extend(chunk)
    result = json.loads(response)
    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'Screenshot failed'))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', default=str(default_socket()))
    parser.add_argument('--format', choices=('png', 'bmp'), default='png')
    parser.add_argument('--frame', action='store_true', help='Include the physical display enclosure')
    args = parser.parse_args()
    try:
        print(capture(args.socket, args.format, args.frame)['path'])
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'{error}. Enable PETREL_EMULATOR and run as the service user.\n')


if __name__ == '__main__':
    main()
