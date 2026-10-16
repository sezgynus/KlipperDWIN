# Emulator screenshots

[English](ui-emulator.md) · [Türkçe](ui-emulator_TR.md) · [Contributing](../CONTRIBUTING.md)

## What it is for

The optional emulator captures the screens drawn by the running Petrel service. Use it to review layouts, refresh documentation and report visual bugs as original-size images. It follows the real LCD UI; it is not a standalone printer simulator. A separate opt-in live browser viewer is described below. Navigate with the physical encoder, then request a capture over SSH.

## Enable or disable

Dependencies are included in normal installation and Moonraker updates. In `~/.config/Petrel/Petrel.env`, change the default:

```ini
PETREL_EMULATOR=1
```

Then restart:

```bash
sudo systemctl restart Petrel.service
```

To disable, set `PETREL_EMULATOR=0` and restart again. Re-running installation/configuration preserves an existing enabled value. `./configure.sh` also retains your custom font, socket and screenshot-directory settings. For an older installation missing dependencies:

```bash
cd ~/Petrel
~/petrel-env/bin/python -m pip install -r requirements.txt
```

## Capture over SSH

1. Open the desired screen on the LCD and wait for it to finish drawing.
2. In SSH, run **as the service user, without sudo**:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py
```

The command prints the saved path. By default images go to `~/Petrel-screenshots/` with timestamped, unique filenames. Output is lossless **272×480 RGB PNG**, without resizing. No screenshots are saved automatically.

For BMP output:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --format bmp
```

Copy images to your computer for review. Repository screenshots belong in `docs/assets/screens/` with names describing the screen/state.

## Optional settings

Set these in the same external environment file and restart the service:

| Variable | Purpose |
|---|---|
| `PETREL_SCREENSHOT_DIRECTORY` | Custom output directory |
| `PETREL_EMULATOR_SOCKET` | Custom local capture socket; default `~/.cache/Petrel-emulator/control.sock` |
| `PETREL_EMULATOR_FONT` | Font file matching a customized physical panel |

For a custom socket, use the same path in the capture command:

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --socket /path/to/control.sock
```

## Troubleshooting and limits

| Problem | What to do |
|---|---|
| Cannot connect or permission denied | Check `PETREL_EMULATOR=1`, restart the service, run as its user and check the socket path |
| Capture rejected | Check panel connection, loaded assets and the service log; wait for a completed screen |
| Text/icons differ from the panel | Compare the font/icon files; see [emulator assets](../assets/emulator/README.md) |
| Dimming is not visible in the image | Captures show screen pixels, not physical backlight brightness |

The emulator mirrors drawing instructions rather than reading the LCD's memory. Fonts, JPEG decoding and QR patterns can differ from a physical panel. For those issues, provide both a screenshot and a photo; a capture alone does not prove physical display accuracy.

## Render documentation screens offline

In a development checkout, regenerate every documentation screen using the real UI drawings. This tool supplies example printer and MMU data, connects to no physical printer and needs no running service or UART connection. Normal installation dependencies are sufficient; the repository’s `tests/` directory must be present.

```bash
cd ~/Petrel
~/petrel-env/bin/python tools/render_docs_screenshots.py --frame
```

Images in `docs/assets/screens/` are replaced only after every screen renders successfully. Preserve existing filenames; forum posts may link to them. For a new screen, add its sample state and captions in both languages to the tool’s scene list. The same list regenerates both galleries.

To review output without changing repository files:

```bash
~/petrel-env/bin/python tools/render_docs_screenshots.py --output-directory /tmp/petrel-docs-screens
```

See the [gallery](screenshots.md) for sample values and available screens. When reporting an actual bug, use the live-service capture procedure above.

Optional `--frame` places the screenshot inside the physical display enclosure. Without it, the 272×480 output is unchanged.

```bash
~/petrel-env/bin/python ~/Petrel/tools/screenshot.py --frame
```

### Refresh PNGs, frames and GIFs

Regenerate all outputs from the same checkout in one production session:

```bash
~/petrel-env/bin/python tools/render_docs_screenshots.py --frame
~/petrel-env/bin/python tools/render_print_controls.py
~/petrel-env/bin/python tools/render_print_controls.py --frame
~/petrel-env/bin/python tools/render_docs_workflows.py
```

The first command produces native 272×480 panel PNGs plus 528×900 presentation copies in `docs/assets/screens/framed/`; the UI pixels are placed in the enclosure without resampling. Both galleries regenerate from one scene registry in the same menu order. The default repository destination refreshes framed copies even without `--frame`. Existing panel files are replaced only after all scenes and presentation frames finish successfully. A custom `--output-directory` produces frames only when `--frame` is requested. The original 76 filenames remain; new scenes are added.

The second/third commands produce the successful Print/Tune walkthrough as native/framed GIF. The final command produces both forms of power hold/cancel/blocking, two red rejection blinks, long MMU error scrolling and 0/1/50/100% panel-native fan animation. Native GIFs go in `docs/assets/`, presentation copies in `docs/assets/framed/`. The PNG command does not refresh these GIFs.

All states use the real UI/driver with example data and no physical printer connection. Error replies are supplied by test doubles. The clock is 12:34 and animations are sampled at controlled elapsed times. Missing preview/layers, reduced Tune and long errors are included in the gallery. The fan GIF emulates the panel animation commands; it does not validate the physical JPEG decoder.


## Optional live Remote Display (port 8088)

The running DWIN emulator provides an opt-in **live browser mirror**. The scroll wheel produces normal encoder rotation, and **middle-mouse click** sends a short encoder press. The physical LCD/encoder continue working. The remote viewer does not create screenshots on disk.

Enable the feature in `~/.config/Petrel/Petrel.env`:

```ini
PETREL_REMOTE=1
PETREL_REMOTE_HOST=tailscale
PETREL_REMOTE_PORT=8088
```

`PETREL_REMOTE_HOST=tailscale` is the **default**; the extra line may be omitted. On Petrel startup, the program runs `tailscale ip -4` to obtain this device's assigned Tailscale IPv4 address, verifies it belongs to the `100.64.0.0/10` range, and binds **only to that address**, **not** localhost, the LAN address, or all network interfaces. If Tailscale is unavailable, Remote Display stays offline but the physical LCD continues working. An SSH tunnel and Tailscale Serve are **not required**.

When the printer is safely idle, restart Petrel after installing a release with this feature:

```bash
sudo systemctl restart Petrel.service
```

Get the Pi's assigned Tailscale IP:

```bash
tailscale ip -4
```

On a computer or phone signed in to the same authorized tailnet, open `http://<PI_TAILSCALE_IP>:8088`, using the address from the command. Tailscale transports this HTTP traffic over its encrypted private network, and tailnet access rules govern which devices can connect. The remote endpoint has **no additional application-level password** and can control the printer: limit access with Tailscale ACL/grants, never open port 8088 on the router, and never publish it through Tailscale Funnel. The application checks the exact Tailscale IP in the HTTP Host and Origin headers to resist cross-origin requests. If an IP changes, restart Petrel to rebind.

For explicitly **localhost-only** access, set `PETREL_REMOTE_HOST=127.0.0.1` and restart. Wildcard/LAN binding (including `0.0.0.0`) is deliberately unsupported. `PETREL_REMOTE_PORT` changes the port if needed. The browser requests native 272×480 JPEG frames about every 250 ms while visible. Mouse input passes through Petrel's normal epoch-guarded UI queue and is rejected when unavailable; middle-button hold does **not** emulate a power long-press. Viewing a fan, buzzer, or light setting does not prove physical operation.

Set `PETREL_REMOTE=0` and restart Petrel to disable. `PETREL_REMOTE=1` automatically enables the existing emulator; `PETREL_EMULATOR=1` is not additionally needed. The private Unix screenshot service continues to work independently.
