# Installation and configuration

[English](installation.md) · [Türkçe](installation_TR.md) · [Documentation](README.md)

This guide matches Petrel's UI restoration development branch `feature/graphite-theme`; it will merge into `master` when complete. In an existing clean `~/Petrel` checkout, use `git fetch origin` and `git switch feature/graphite-theme` before installation. Update Manager follows `master`, so avoid its update/recovery actions while you intend to retain this development branch. Follow [development-branch updates](#update-the-development-branch) to retain this branch.

## Before installation

Use a compatible DWIN T5UIC1 panel, a Linux SBC with UART/GPIO, Python 3.11+ and a working Klipper/Moonraker setup. Check [LCD compatibility](lcd-assets.md). The installer does not flash LCD kernel firmware or fonts; the application synchronizes Petrel icons automatically at its first LCD connection.

## Wiring and serial setup

| Display connection | Raspberry Pi connection |
|---|---|
| RX | GPIO14 / UART TX |
| TX | GPIO15 / UART RX |
| Encoder A | GPIO21 |
| Encoder B | GPIO19 |
| Encoder button | GPIO20 |
| VCC | 5 V |
| GND | GND |

GPIO numbers are **BCM numbers**. Encoder pins can be changed during configuration. See [wiring illustrations](../images/) for the physical connections.

In `sudo raspi-config`, enable serial hardware and disable the serial login console, then reboot. Confirm which UART device uses GPIO14/15 on your Pi and OS. The installer suggests `/dev/ttyS0`; choose the device appropriate for your installation.

## Install

Run as the user who will own the service. The checkout must be clean and located at `~/Petrel`:

```bash
cd ~
git clone --branch feature/graphite-theme https://github.com/sezgynus/Petrel.git
cd ~/Petrel
./install.sh
```

Press Enter to accept a prompt's default, or enter your own value:

| Setting | Installer default |
|---|---|
| Moonraker URL | `http://127.0.0.1:7125` |
| UART | `/dev/ttyS0` |
| Encoder A/B | `21 19` |
| Encoder button | `20` |
| Moonraker power device | `Printer` |
| Power-on hold | `2000` ms (2 seconds) |

Installation prepares `~/petrel-env`, installs dependencies and enables `Petrel.service`. It keeps settings in `~/.config/Petrel/Petrel.env`, adds a `Petrel.conf` include beside `moonraker.conf` and registers the service for Moonraker updates. Existing settings are preserved when installation is repeated.

For a nonstandard Moonraker configuration location:

```bash
MOONRAKER_CONFIG=/path/to/moonraker.conf ./install.sh
```

## LCD resources and first start

1. [Install the LCD font](lcd-assets.md#lcd-font). The font is installed once from SD; icons and boot artwork are managed automatically over UART.
2. Wait for Petrel startup progress to finish and **Home** to appear.
3. Rotate the encoder and open a menu; check temperatures against the web interface.
4. For wrong text/icons, follow the [LCD resource guide](lcd-assets.md); for connection failures, use the troubleshooting table below.

Moonraker must authorize the Petrel connection. Set `MOONRAKER_API_KEY` if authentication is required. Check the service user's serial/GPIO permissions; the installer configures the `dialout` and `gpio` groups.

## Change settings

```bash
cd ~/Petrel
./configure.sh
```

Current values become the prompt defaults. Your custom `PETREL_SETTINGS_FILE` path and other environment settings, including unprompted font/socket/screenshot-directory options, are preserved without duplicating keys. The file is replaced atomically with private permissions. After saving, accept the offered service restart to apply them. Display brightness/dimming are adjusted on the LCD under **Home → Display**, rather than here.

For settings not prompted by the configurator, edit the external environment file. Use plain `KEY=value` lines, without `export`:

| Setting | Purpose / default |
|---|---|
| `MOONRAKER_URL` | Moonraker address / `http://127.0.0.1:7125` |
| `MOONRAKER_API_KEY` | Authentication key if required / empty |
| `PETREL_REQUEST_TIMEOUT` | Request timeout in seconds / `5` |
| `PETREL_SERIAL_PORT` | Configured UART / installer suggests `/dev/ttyS0` |
| `PETREL_ENCODER_PINS` | Encoder A/B in BCM numbering / `21 19` |
| `PETREL_BUTTON_PIN` | Encoder button in BCM numbering / `20` |
| `PETREL_SETTINGS_FILE` | Local preset fallback / `~/.config/Petrel/presets.json` |
| `PETREL_POWER_DEVICE` | Name of your Moonraker power device / `Printer` |
| `PETREL_POWER_ON_HOLD_MS` | Power-on hold in milliseconds / `2000`; `0` means immediate |
| `PETREL_EMULATOR` | Screenshot capture / `0` disabled, `1` enabled |

Restart after editing: `sudo systemctl restart Petrel.service`. Keep private keys and machine settings outside tracked repository files. See the [emulator guide](ui-emulator.md) for screenshot-specific options.

## Update

### Update the development branch

While using `feature/graphite-theme`, follow this path instead of Update Manager/Info update or recovery. Leave the printer idle and save tracked edits and added files elsewhere. First check:

```bash
cd ~/Petrel
git status --short
git branch --show-current
```

`git status --short` must be empty. Then select the branch and stop the service; pull only a fast-forward update, refresh dependencies/service registration through the installer and restart the running service:

```bash
git switch feature/graphite-theme &&
sudo systemctl stop Petrel.service &&
git pull --ff-only origin feature/graphite-theme &&
./install.sh &&
sudo systemctl restart Petrel.service
```

If a step fails, subsequent steps do not run; do not force-reset files. The service may remain stopped: resolve the cause and finish before restarting it. Check with `sudo systemctl status Petrel.service --no-pager`. Custom environment settings are retained; icons refresh at the first LCD connection. Repeat the [LCD font](lcd-assets.md#lcd-font) step only if the font also changed.

After the branch merges into `master`, use `git fetch origin` and `git switch master` in a clean checkout to return to normal updates; remove these temporary branch notes in the same merge.

### Normal updates and migration from older installations

Existing installations migrate automatically after their next Moonraker update: the old updater downloads this version, and the first service start schedules a separate migration job. It preserves settings, moves the checkout to `~/Petrel`, prepares `~/petrel-env`, installs `Petrel.service` and reloads Moonraker with the new updater. Allow a few minutes for Python dependencies. Automatic migration requires the same passwordless sudo access normally available on the Pi; otherwise run `sudo python3 ~/KlipperDWIN/petrel_migration.py --user "$USER"` once. Migration refuses to overwrite an existing Petrel installation. A failed service switch restores the previous installation; details are in `journalctl -u Petrel-migration.service`.

On a `master` installation, after Moonraker reloads its configuration, use **Mainsail → Machine → Update Manager → Petrel**. Refresh and update; dependencies and the service restart are handled automatically. Update Manager follows `master`.

You can also check and install Petrel updates from **Info** on the LCD while the printer is idle. See [Info and updates](user-guide.md#info-and-updates). Local edits to tracked repository files may block updating; inspect or back them up before recovery discards them.

## Troubleshooting

```bash
sudo systemctl status Petrel.service --no-pager
journalctl -u Petrel.service --since "10 minutes ago" --no-pager
sudo systemctl restart Petrel.service
```

| Symptom | What to check |
|---|---|
| Blank screen or repeated reconnects | Panel power, crossed TX/RX, selected UART, serial login console and permissions |
| Encoder does not respond | BCM pin settings and wiring |
| Startup stays on one stage | Klipper/Moonraker readiness, panel resources and service logs |
| Optional menu missing or locked | Required Klipper/Happy Hare configuration, connection and current printer state |
| Preview image or metadata missing | Slicer thumbnails and metadata available in Moonraker |
| Wi-Fi information unavailable | Wireless connection and availability of Linux `iw` |
| Update blocked | Local repository edits and Moonraker Update Manager status |
| Action failed or timed out | Check the actual printer state in Mainsail before repeating |

For a bug report, include the software revision, Pi/OS, configuration relevant to the problem and the log excerpt. Add a photo or [emulator screenshot](ui-emulator.md) for visual problems; remove credentials before sharing.
