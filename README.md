# KlipperDWIN

**A local Klipper control panel for your DWIN display.**

Browse files, inspect a print before starting it, adjust your printer and calibrate the bed from the rotary encoder.

<p align="center">
  <a href="README.md">English</a> · <a href="README_TR.md">Türkçe</a>
</p>
<p align="center">
  <a href="https://github.com/sezgynus/KlipperDWIN/tree/v1.0.0"><img alt="v1.0.0" src="https://img.shields.io/badge/version-v1.0.0-0969da"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white">
  <img alt="Klipper / Moonraker" src="https://img.shields.io/badge/Klipper-Moonraker-7d3cff">
  <a href="LICENSE"><img alt="GPL-3.0" src="https://img.shields.io/badge/License-GPL--3.0-blue"></a>
</p>
<p align="center">
  <img src="docs/assets/screens/home.png" width="240" alt="Home">
  <img src="docs/assets/screens/print-preview.png" width="240" alt="Print preview">
</p>

[Features](#features) · [Installation](#installation) · [UI guide](#ui-guide) · [Configuration](#configuration) · [Troubleshooting](#troubleshooting) · [Development](#development)

KlipperDWIN runs on a Raspberry Pi or compatible Linux SBC. It connects to the **272×480 DWIN T5UIC1 display** over UART, reads the encoder through GPIO and uses Moonraker HTTP/WebSocket APIs for printer commands and live status. Klipper and Moonraker are required; Mainsail, Happy Hare and Spoolman provide optional integrations.

The application targets the 4.3-inch panel and asset layout used by the Ender 3 V2. Other panel families and asset packages are not interchangeable; see [LCD compatibility](docs/lcd-assets.md).

## Features

| Workflow | Available in v1.0.0 |
|---|---|
| Find and start a print | Nested folders, Mainsail sorting, JPEG preview, print metadata and Print/Cancel confirmation |
| Fast previews | First-five thumbnail preloading and a volatile LCD SRAM cache |
| Monitor a print | Progress, elapsed/remaining time, Pause/Resume, Stop and Tune |
| Adjust the printer | Homing, Move/Live Jog, heater/fan targets, runtime Z offset and motion limits |
| Calibrate the bed | Four-corner Screws Tilt Adjust, Bed Mesh Calibrate, saved Mesh Viewer and Probe calibration |
| Use integrations | Editable Mainsail temperature presets, Happy Hare gate visualization, Spoolman percentages and M355 case light |
| Inspect the system | Scrollable host, software and MCU information; encoder power on/off |

Menus adapt to detected printer capabilities. The **MMU menu provides full-screen Happy Hare control, live status and recovery**; its Home-screen gate visualization keeps the existing layout. Remaining limitations are listed [below](#scope-and-limitations).

## Installation

### Hardware and wiring

Use a Linux SBC with accessible UART/GPIO, Python 3.11 or newer, a compatible DWIN T5UIC1 panel and a working Klipper/Moonraker installation.

| Display connection | Raspberry Pi connection |
|---|---|
| RX | GPIO14 / UART TX |
| TX | GPIO15 / UART RX |
| Encoder A | GPIO21 |
| Encoder B | GPIO19 |
| Encoder button | GPIO20 |
| VCC | 5 V |
| GND | GND |

GPIO numbers use **BCM numbering**. Encoder pins are installer defaults and can be changed. Wiring examples are in [images/](images/).

Enable serial hardware and disable the serial login console using `sudo raspi-config`, then reboot. Verify the UART device routed to GPIO14/15 for your Pi and OS; `/dev/ttyS0` is the installer default, not a universal mapping.

### Install and configure

Run from the standard checkout location:

```bash
cd ~
git clone https://github.com/sezgynus/KlipperDWIN.git
cd ~/KlipperDWIN
./install.sh
```

The installer installs dependencies, creates `~/klipperdwin-env`, prompts for connection/pin settings and enables **`KlipperDWIN.service`**. Configuration stays outside the checkout in `~/.config/KlipperDWIN/KlipperDWIN.env`.

It also creates `KlipperDWIN.conf` beside `moonraker.conf`, adds the include and registers the service with Moonraker Update Manager. For a custom Moonraker configuration path:

```bash
MOONRAKER_CONFIG=/path/to/moonraker.conf ./install.sh
```

The prompts default to Moonraker `http://127.0.0.1:7125`, UART `/dev/ttyS0`, encoder pins `21 19`, button pin `20`, power device `Printer` and a `2000` ms power-on hold. Enter accepts each default. Re-running the installer preserves existing configuration.

To change settings later:

```bash
cd ~/KlipperDWIN
./configure.sh
```

This uses current values as defaults and offers a service restart after saving. The installer runs the service as the installation user and adds available `dialout`/`gpio` groups.

### Update from Mainsail

After Moonraker reloads the generated configuration, open **Machine → Update Manager**, refresh and update **KlipperDWIN**. Moonraker follows `master`, updates Python requirements when needed and restarts the managed service. No separate dependency installation is needed for a normal Update Manager update.

> [!NOTE]
> Keep hardware settings in the external configuration file. Local edits to tracked repository files prevent the checkout from remaining clean for Update Manager. Tags identify releases; the updater continues following `master` after `v1.0.0`.

## UI guide

Rotate the encoder to navigate, press to select. Display labels remain in English; the Turkish README explains the same menus.

### Home and menu map

Home has four icons per page. Continuing to rotate moves to the next or previous page; empty slots are skipped. The logo/MMU panel and live dashboard stay fixed. Returning from Home’s MMU or Info preserves the selected icon.

| Entry | Destination |
|---|---|
| Print | File browser → Print preview |
| Prepare | Move, Disable steppers, Home, Runtime Z offset, Screws Tilt Adjust, preheat and cooldown |
| Control | Temperature, Motion, Probe calibration, jog recovery, Case Light and Info |
| Leveling | Bed Mesh: Bed Mesh Calibrate and Mesh Viewer |
| MMU | Full-screen gates, filament operations, bypass, live status and recovery |
| Info | Scrollable system information |

With bed mesh, the first page is **Print / Prepare / Control / Leveling** and the second **MMU / Info**. Without bed mesh, MMU takes the fourth slot and Info is on the next page. Optional menu entries appear only when supported.

The dashboard shows available heater temperatures/targets, fan, print-speed factor, flow, runtime Z offset and live XYZ coordinates.

### Files and sorting

<p align="center"><img src="docs/assets/screens/print-file.png" width="260" alt="File browser"></p>

The browser shows the current folder with **folders first**, including empty folders, and only `.gcode` files (case-insensitive). Dot-prefixed files/folders such as `.thumbs` are hidden. Select a folder to enter it; **Back** returns to its parent, or Home at the root. Printing uses the full relative path even though rows show only basenames.

Sorting follows Mainsail’s saved filename, modified-time or size criterion and ascending/descending direction, read from Moonraker every five seconds. The same preference applies at every folder level. Missing, invalid or unsupported preferences fall back to **newest modified first**. The LCD only reads these preferences. Selection is preserved by path where possible; a changed list cannot silently start a different file.

### Print preview

<p align="center"><img src="docs/assets/screens/print-preview.png" width="300" alt="Print preview with model and used filaments"></p>

Selecting a file opens its preview. **Cancel is selected initially** and returns to the same folder/file. **Print** rechecks the file version and waits for command acceptance and printer-status confirmation before opening the printing screen.

| Display label | Moonraker metadata |
|---|---|
| Print time | `estimated_time` |
| Tool changes | `filament_change_count` |
| Total usage | `filament_total` converted from mm to m / `filament_weight_total` in grams |
| Filaments used | Used tool number, `filament_colors`, `filament_type` and `filament_weights` |

The model occupies a 128×128 area at the upper left, summaries sit on its right and up to four used tools appear below. `referenced_tools` determines which rows appear; if absent, positive tool weights or single-material metadata provide a fallback. Tool numbers are slicer tool IDs, **not physical MMU lane assignments**. If more than four tools are used, the heading reports the displayed/total count. Unknown values show placeholders; missing images do not disable metadata or Print/Cancel.

Images and metadata come from Moonraker; the application does not parse G-code. JPEG images are uploaded to volatile LCD SRAM, without writing flash or replacing installed icons. The browser preloads the **first five files in the current sort order**, starting with the first. Unchanged entries survive folder/sort changes; replaced/deleted files and reconnections invalidate stale cache entries. Remaining space caches other selected files using LRU eviction. Space limits can prevent all five images from fitting; earlier files have preload priority, while a selected file can reclaim space.

### Printing and Tune

<p align="center">
  <img src="docs/assets/screens/printing.png" width="240" alt="Printing">
  <img src="docs/assets/screens/tune.png" width="240" alt="Tune">
</p>

The print screen shows filename, progress, elapsed/remaining time and **Tune / Pause or Resume / Stop**. Completion follows Klipper’s `print_stats.state`, not a rounded 100% value. Pause/resume/cancel actions wait for the corresponding subscribed status.

Tune provides print speed, runtime Z offset and available hotend/bed/fan targets. An open editor retains its local target until confirmed; live updates do not overwrite the edit.

### Prepare, Move and calibration

<p align="center">
  <img src="docs/assets/screens/prepare.png" width="240" alt="Prepare">
  <img src="docs/assets/screens/move.png" width="240" alt="Move and Live Jog">
</p>

**Prepare → Move** shows live command-space positions from `gcode_move.position`. Normal editing sends a target when confirmed; **Live Jog** applies encoder movement immediately. Moves require homing, respect travel limits and reject printing/paused states. Extrusion checks temperature and configured distance limits. Relative jogging saves/restores G-code state; an unconfirmed restore blocks further movement and exposes **Control → Restore jog state**.

**Prepare → Screws Tilt Adjust → Calculate** runs `SCREWS_TILT_CALCULATE`, homing missing axes first. It requires a probe and four distinct corner screws configured in `[screws_tilt_adjust]`.

<p align="center"><img src="docs/assets/screens/screws-tilt-success.png" width="280" alt="Screws Tilt Adjust result"></p>

Corners follow configured XY positions and show **Base** or **CW/CCW** with turns:minutes. `01:20` means one full turn plus 20/60 of a turn. Klipper supplies direction/amount; the central instruction selects the largest required adjustment. Success requires a measured peak-to-peak height difference below **0.05 mm** and turns the central message green; required adjustments use neutral white. **Continue** returns to Calculate for another measurement. No configuration save or automatic screw movement occurs.

**Control → Probe calibration** uses `PROBE_CALIBRATE`, explicit `TESTZ` steps, `ACCEPT` and `ABORT`. Saving is a separate guarded `SAVE_CONFIG` action and restarts Klipper. Calibration actions are blocked during printing, incompatible probe sessions or unresolved movement recovery; old results are not presented as fresh success.

### Bed Mesh and saved profiles

**Home → Leveling** opens the **Bed Mesh** menu. These entries are grouped here rather than repeated under Prepare or Control.

| Action | Behavior |
|---|---|
| Bed Mesh Calibrate | With a probe, home missing axes and measure a full mesh using `BED_MESH_CALIBRATE` |
| Measurement view | Draw a grid with available live probe values marked raw Z |
| Result | Show fresh `probed_matrix` heights, colored circles and min/max Z |
| Continue | Return to the menu; keep the measured profile for the current session |
| Save | Confirm profile/restart, recheck pending changes, then persist with `SAVE_CONFIG` |
| Mesh Viewer | List Current Mesh and saved `bed_mesh.profiles`; select a map to view |

Viewer selection **does not load a profile or change the active mesh**. The map places low Y at the bottom. Save uses a generated `lcd_mesh_N` profile and is allowed only when pending changes belong exactly to the measured profile. It does not save unrelated pending settings; a lost restart response is not proof of persistence.

> [!IMPORTANT]
> **Cancel → Stop** during measurement sends an emergency stop and places Klipper in shutdown. The confirmation states this explicitly; use `FIRMWARE_RESTART` to resume. Save also requires a restart, while Continue does not persist the profile.

### Control, temperature and runtime motion

<p align="center">
  <img src="docs/assets/screens/control.png" width="220" alt="Control">
  <img src="docs/assets/screens/temperature.png" width="220" alt="Temperature">
  <img src="docs/assets/screens/motion-runtime.png" width="220" alt="Runtime Motion">
</p>

**Control → Temperature** exposes installed hotend/bed/fan controls. Mainsail preset names and enabled heater targets are discovered through Moonraker’s database and appear dynamically in Prepare and Temperature. LCD preset edits can be saved back to Mainsail. Applying heats the printer; saving preset settings alone does not. Fan settings are not synchronized as temperature presets. If Mainsail presets are unavailable, an external local JSON store provides a fallback; once available, Mainsail becomes authoritative.

**Control → Motion** edits max velocity, max acceleration, square-corner velocity and supported minimum cruise ratio through `SET_VELOCITY_LIMIT`. These are **runtime values** and are not automatically saved to configuration.

### Info

<p align="center">
  <img src="docs/assets/screens/info-overview.png" width="220" alt="System overview">
  <img src="docs/assets/screens/info-software.png" width="220" alt="Software versions">
  <img src="docs/assets/screens/info-mcu-details.png" width="220" alt="MCU details">
</p>

**Home → Info** and **Control → Info** open the same encoder-scrollable overview: machine dimensions, network/IPv4, host CPU load/temperature, installed software versions and each connected MCU’s state/load. MCU temperature requires a matching `temperature_mcu` source; unavailable values show `N/A`. KlipperDWIN uses the full Update Manager Git version when available, including commits after a tag.

## Optional integrations

### Happy Hare and Spoolman

When Happy Hare objects are present, Home’s logo area becomes a live gate panel. It uses `mmu` for gate/material/color/spool state, `mmu_machine` for the unit name and **`unitN_mmu_exit_leds`** for exit-LED colors. Dim colors are normalized for readability; fully off LEDs stay black and lane numbers use contrasting black/white text.

Spoolman percentages come from each gate’s `gate_spool_id` through Moonraker’s Spoolman proxy, rather than a single active spool. Missing Spoolman data does not disable the other gate information. Select **Home → MMU** to open the dedicated full-screen interface. The general motion dashboard is hidden on MMU pages and restored when returning Home.

**Rotate to move focus; press to open or accept.** The upper-left Back arrow is selectable. Long press retains the configured printer-power behavior. Gate browsing and opening details never move filament.

| MMU page | Available behavior |
|---|---|
| Home | Up to four spools on the active gate page, selected tool/gate, filament path, nozzle temperature and six menu entries |
| Gates / gate details | Scrollable physical-gate list; Select only, Load selected, mapped Load/change, Unload, Eject spool, Preload and Check |
| Filament / Assign spool | Name, material, color, spool ID, remaining percentage, temperature and mode; draft ID assignment or explicit clearing |
| Tool map | Draft tool-to-gate editor; press, rotate, press to accept; Save/Cancel |
| EndlessSpool (from Tool map) | Draft enable switch, groups and gate membership; material/color compatibility, Save/Cancel |
| Bypass | Unload the current MMU gate, select bypass, then use extruder-only load/unload |
| Manage / Recover | Recovery, manual state editor, unlock/reheat and Resume; links to maintenance/options |
| Maintenance / Options | Check all gates, single linear-selector Home, supported Grip/Release, loaded-filament gear sync and sensor status |
| LEDs (from Options) | Active-unit enable, animation and exit modes; verified LED configuration |
| Units (from Options) | Read-only unit/gate browsing; separately confirmed selection of a unit’s first global gate |
| Status | Actual action and Bowden-stage progress when available, distinct sensor states, gear sync, nozzle temperature and operation result |

The LCD shows **G1 for Happy Hare `GATE=0`**; tools retain T0-based numbering. A spool mapped to several tools shows `T*`. Load selected uses the current available gate; Load/change chooses an associated logical tool and follows Happy Hare's mapping. Unload parks filament in the MMU; Eject spool explicitly requests removal, including unloading the active gate first when necessary.

Every operation opens a target-specific confirmation with **Cancel initially selected**. State is checked again before dispatch. Missing, disabled, stale or busy MMU state locks operations. Routine movement is disabled during printing and pauses; recovery has its own guards. A running operation remains inside the MMU interface and blocks LCD calibration starts. Commands use completion-tracked WebSocket RPC followed by an actual-state query; a dispatch acknowledgment is never shown as physical completion. Failed or unconfirmed operations require acknowledgment and are never automatically replayed.

An MMU error pause with a reported reason opens Recover directly. Fix the physical problem, recover or report the actual state, unlock/reheat if needed, then choose Resume separately. Manual Apply reports state without loading/unloading filament; it may also correct the tool-to-gate assignment. Resume requires a paused print, unlocked MMU and loaded filament. Sensor `CLEAR`, `TRIGGERED`, `UNKNOWN/OFF` and `ABSENT` are distinct; Bowden percentage describes that stage rather than the whole tool change.

Tool map edits are available only outside printing/pauses while the MMU is idle. Several tools may share one gate. Save confirms the changed rows, sends one bulk `MMU_TTG_MAP MAP=...` command and verifies the actual mapping; Cancel discards the draft. External state changes lock the draft until reopened.

EndlessSpool uses the same idle, off-print guards. Edit the Enabled value by pressing, rotating and pressing again. Open a group and press gates to add them; removing a member gives it a separate group (the final member stays). Group pages show each gate’s material/color and report matching, mixed or unknown metadata; verify physical spool compatibility. Save sends the complete enable/group draft in one `MMU_ENDLESS_SPOOL ENABLE=... GROUPS=...` command and verifies both fields. Back from members retains the draft; Cancel from EndlessSpool discards it.

Filament → Assign spool ID edits a positive numeric ID using press, rotate, press, then Save and confirmation. Clear assignment has its own confirmation; Cancel discards the draft. Local assignments are allowed in known `off`, `readonly` and `push` modes; `pull` and unknown modes stay locked. A complete spool-ID map and known positive integer filament temperature are required. The command preserves that temperature, and confirmation warns when the ID will move off another gate. Actual-state verification checks the entire assignment map, including duplicate removal; it does not validate that a spool record exists or that asynchronous Spoolman synchronization finished.

Maintenance and Options read validated Happy Hare v4 `mmu_machine` unit metadata and live selector state. Unsupported controls are hidden; missing, busy, printing or paused state locks actions. Home is offered only for one known linear selector and confirms the tool selected afterwards. Grip/Release require unloaded filament; release is hidden for always-gripped units. Gear sync requires loaded filament on a known active unit; always-gripped units cannot unsync. Linear-selector drive controls require a known homed state. Each command has a Cancel-first confirmation and live postcondition checks. Check all gates uses global gate indices; metadata remains a capability declaration, not proof of calibration. Verify installed command behavior on hardware.

Options also offers explicit MMU enable/disable and release of all MMU motors, with Cancel-first confirmation. Both require unloaded filament outside printing/pauses. Enabling resets Happy Hare state; a disabled MMU can be re-enabled from this page. Motor release appears only with known driver telemetry and effective MMU stepper configuration; it sends `MMU_MOTORS_OFF UNIT=ALL` and checks every configured MMU driver is off and gear sync is off. Homing may be lost. Driver flags cannot prove servo power or physical motion.

Options → LEDs appears only with validated active-unit `mmu_leds <name>` telemetry. Enable, animation and exit modes (`off`, `gate_status`, `filament_color`, `slicer_color`) use unit-scoped `MMU_LED UNIT=...` commands and query the actual LED object afterwards. The reported configuration does not prove physical LED output. Unsupported or unknown state locks the controls; custom effects and entry/status/logo editing remain in the web UI.

Options → Units appears only for a validated multi-unit gate partition. Browsing units and their gates sends no command and preserves global gate numbers. Select this unit confirms `MMU_SELECT GATE=...` for that unit’s first gate; it may home or move the selector and requires unloaded filament outside printing/pauses. Completion checks both the queried active unit and gate. Single-unit installations omit this browser.

This control implementation follows the [MMU design](https://github.com/sezgynus/KlipperDWIN/tree/docs/mmu-menu-demo/docs/mmu-menu-demo). Use the web UI for calibration and advanced LED configuration. Actual command behavior depends on the installed Happy Hare version and configuration; incomplete telemetry leaves the corresponding action locked.


### Case Light

<p align="center"><img src="docs/assets/screens/case-light.png" width="240" alt="Case Light"></p>

**Control → Case Light** appears when `gcode_macro M355` exists. It provides on/off and 0–100% brightness, converted to a 0–255 macro value. For bidirectional status, the macro must accept the commands and return the query format below:

```text
M355 S0/1
M355 P0..255

Light is ON, Brightness=128
```

### Encoder power control

A Moonraker power device can be switched on by holding the encoder button, even while Klipper or LCD UART is offline. Configure the device name and hold duration with `./configure.sh`. Defaults are `Printer` and **2 seconds**; `0` ms requests power-on immediately on press.

Every menu exposes the same power icon at the top-right. From the first menu item, rotate the encoder counter-clockwise to focus the icon; rotate clockwise to return to the menu. Pressing the focused icon opens a **Turn off printer?** confirmation with **Yes selected by default**. Confirming Yes switches off the configured Moonraker power device only when its reported state is `on`; No returns to the originating menu.

## Configuration

Installed services read `~/.config/KlipperDWIN/KlipperDWIN.env`. This is a systemd EnvironmentFile, not a shell script. `MOONRAKER_API_KEY` and request timeout can be edited there; the interactive configurator preserves them. CLI arguments override environment values.

| Environment variable | CLI argument | Installer setting | Bare `run.py` default |
|---|---|---|---|
| `MOONRAKER_URL` | `--moonraker-url` | `http://127.0.0.1:7125` | Same |
| `MOONRAKER_API_KEY` | Environment only | Empty | Empty |
| `DWIN_REQUEST_TIMEOUT` | `--request-timeout` | 5 seconds | 5 seconds |
| `DWIN_SERIAL_PORT` | `--serial-port` | `/dev/ttyS0` | `/dev/ttyAMA0` |
| `DWIN_ENCODER_PINS` | `--encoder-pins A B` | `21 19` | `21 19` |
| `DWIN_BUTTON_PIN` | `--button-pin` | `20` | `13` |
| `DWIN_SETTINGS_FILE` | `--settings-file` | `~/.config/KlipperDWIN/presets.json` | `$XDG_CONFIG_HOME/dwin-lcd/presets.json` or `~/.config/dwin-lcd/presets.json` |
| `DWIN_POWER_DEVICE` | `--power-device` | `Printer` | `Printer` |
| `DWIN_POWER_ON_HOLD_MS` | `--power-on-hold-ms` | `2000` | `2000` |

Bare defaults apply when no environment file or CLI value is supplied. For manual debugging, stop the service first so only one process owns UART/GPIO. This example explicitly uses the installer’s pins/device:

```bash
sudo systemctl stop KlipperDWIN.service
cd ~/KlipperDWIN
~/klipperdwin-env/bin/python run.py \
  --serial-port /dev/ttyS0 \
  --encoder-pins 21 19 \
  --button-pin 20 \
  --moonraker-url http://127.0.0.1:7125
```

After exiting the manual process, restore the service with `sudo systemctl start KlipperDWIN.service`. Install manual dependency updates using `~/klipperdwin-env/bin/python -m pip install -r requirements.txt`; normal Mainsail updates handle this automatically.

## Troubleshooting

```bash
sudo systemctl status KlipperDWIN.service --no-pager
journalctl -u KlipperDWIN.service --since "10 minutes ago" --no-pager
sudo systemctl restart KlipperDWIN.service
```

| Symptom | Check |
|---|---|
| No screen / UART reconnects | Power, crossed TX/RX, selected UART, serial console and device permissions |
| Encoder does not respond | BCM pin configuration, wiring and gpiochip permissions |
| Missing optional menu | Matching Klipper object/configuration and current Moonraker connection |
| Missing preview data | Moonraker file metadata, slicer-provided fields and thumbnail availability |
| Preview feels slow | `Thumbnail` download/conversion/upload/cache-hit logs; background timing may include time away from the browser |
| Update blocked by local edits | Keep runtime settings outside tracked files; inspect checkout changes |
| Action failed or response was lost | Inspect actual printer state before repeating it |

Transport and action errors are logged, but a clean log cannot prove physical motion, display appearance or persistence. Include a screen photo for visual issues.

## Scope and limitations

- The UI targets compatible 272×480 DWIN T5UIC1 assets; other display families require separate validation.
- MMU calibration and advanced LED effects remain in the web UI. Multi-unit Home needs per-unit live homing telemetry and is not offered. Gates use global Happy Hare indices; the existing Home gate/LED layout is unchanged.
- Preview shows up to four used tools; per-tool lengths, brand names and physical lane mapping are not displayed.
- SRAM cache is volatile and limited to 32 KiB; it is rebuilt after reconnect/restart.
- Screws Tilt requires four distinct corners and uses a fixed 0.05 mm peak-to-peak success threshold.
- Mesh maps support up to 25×25 points. Dense maps omit some labels while drawing every point and including all values in min/max.
- Live mesh progress depends on standard probe console responses. Methods without them can still show the final result.
- Mesh cancellation shuts Klipper down; persistent calibration saves restart Klipper.
- Runtime motion and Z-offset edits are separate from persistent probe/configuration calibration.
- Broader panel, wiring and printer compatibility still needs physical testing.

## Development

### Architecture and command handling

One UI owner thread controls rendering, navigation and UART writes. GPIO callbacks enqueue input events. Moonraker WebSocket subscriptions supply merged immutable state; a serialized HTTP worker handles commands, while long bed-calibration operations use completion-tracked WebSocket RPC.

Connection epochs reject stale input and queued commands. Failed printer commands are **not replayed automatically**. A response-based panel heartbeat detects LCD power cycles even when the Linux UART device remains open; reconnecting redraws the UI and restores volatile atlas/cache state from persistent Picture Flash without rewriting unchanged atlas data. A timeout may mean the printer received a command but its response was lost; inspect actual state before retrying.

| Modules | Responsibility |
|---|---|
| `dwinlcd.py`, `ui_*.py` | Navigation, feature screens and UI event ownership |
| `printerInterface.py`, `printer_state.py`, `printer_capabilities.py` | Printer actions, normalized state and available controls |
| `moonraker_client.py`, `moonraker_subscription.py`, `command_feedback.py` | HTTP/WebSocket transport and command confirmation |
| `screws_tilt.py`, `bed_mesh.py`, `probe_wizard.py` | Calibration state machines and result/config guards |
| `thumbnail_preview.py`, `thumbnail_cache.py`, `preview_metadata.py` | JPEG preparation, SRAM allocation and optional metadata |
| `t5uic1_driver.py`, `encoder.py`, `ui_events.py` | Complete T5UIC1 protocol driver, GPIO input and event loop |
| `preset_store.py`, `motion_settings.py`, `system_info.py` | Preset persistence, runtime limits and system telemetry |

Motion and calibration commands recheck live print, homing and session state when dispatched; stale jog positions are rejected. Jog cleanup uses a separate connection guard so MOVE=0 restoration remains available after a movement failure.

SAVE_CONFIG dispatch rechecks the exact approved pending settings; mesh saves also recheck the measured current/profile data. Changes observed from other clients invalidate the save. This client-side guard is not an atomic lock across all Moonraker clients.

Preset, file-list, directory, sorting and Info HTTP reads run in a bounded background worker. The UI remains responsive while reads are pending. Print confirmation revalidates the file asynchronously; Cancel or a connection change prevents a pending validation from starting the print. Mainsail preset writes also finish asynchronously and report failures on screen.

Command feedback has a deadline even while its transport Future remains unresolved. Expired actions stay unconfirmed and are never accepted by a late result; inspect the printer before retrying.

MMU controls use the validated live control state independently of optional Home RGB telemetry. Missing or malformed gate colors can hide the Home strip without disabling otherwise valid menu actions; print, busy, physical-state and dispatch guards still apply.

HTTP JSON responses are limited to 8 MiB by default, including file lists, metadata and command replies. Integrations can configure `MoonrakerClient(max_json_bytes=...)` with a positive integer byte budget. The reader enforces the limit independently of Content-Length; oversized responses fail without automatically replaying commands.

Complete T5UIC1 LCD configuration, firmware/assets, memory layout and runtime protocol details are documented in [`docs/t5uic1-reference.md`](docs/t5uic1-reference.md).

The MMU full-screen pages use the complete T5UIC1 driver and reserve the top-right header for the managed power icon. From MMU Back, one more counter-clockwise step focuses power; clockwise returns to Back. Choosing No in the power popup restores the full MMU page, including its draft and selection. Static custom icons use the master atlas manifest; MMU live gate/filament graphics remain dynamic. Panel loss or a connection epoch change cancels an open MMU power popup without sending a shutdown command. See the [driver integration record](docs/mmu-driver-integration.md).

### Regression tests

```bash
cd ~/KlipperDWIN
~/klipperdwin-env/bin/python -m unittest discover -s tests -v
```

Tests exercise real UI/backend methods with isolated state and mocked serial/GPIO/network I/O. Coverage includes menu paging, folders/sorting, preview metadata/cache invalidation, UART packets/recovery, command epochs, movement guards, presets and calibration save/cancel flows. They do not replace physical printer/panel testing. See [test contracts](tests/README.md), [LCD asset inventory](docs/lcd-assets.md) and the [historical source audit](docs/source-audit.md).

### Contributing

Issues and pull requests are welcome. Include relevant regression coverage for behavior changes. For bug reports, provide Pi/OS, UART device, encoder BCM pins, software versions, optional components, logs and a photo for visual problems.

## Credits and license

This project originated from [odwdinc/DWIN_T5UIC1_LCD](https://github.com/odwdinc/DWIN_T5UIC1_LCD) and [bustedlogic/DWIN_T5UIC1_LCD](https://github.com/bustedlogic/DWIN_T5UIC1_LCD). Original copyright notices and Git history are retained.

Integrations use [Klipper](https://github.com/Klipper3d/klipper), [Moonraker](https://github.com/Arksine/moonraker), [Mainsail](https://github.com/mainsail-crew/mainsail), [Happy Hare](https://github.com/moggieuk/Happy-Hare) and [Spoolman](https://github.com/Donkie/Spoolman).

Licensed under **GNU GPL v3.0**. See [LICENSE](LICENSE).
