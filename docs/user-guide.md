# Daily use

[English](user-guide.md) · [Türkçe](user-guide_TR.md) · [Documentation](README.md)

## Navigation and dashboard

<p align="center">
  <img src="assets/screens/framed/home.png" width="360" alt="Home, first page">
  <img src="assets/screens/framed/home-page-2.png" width="360" alt="Home, second page">
</p>

Rotate to move the highlight; press to select. Press a numeric value, rotate to edit it and press again to apply it. **Back** returns to the previous screen. Home shows four icons per page; continue rotating to change pages. Dots indicate the active page. Optional entries depend on your printer's configuration.

The three dashboard rows are shown below. Speed/flow fields alternate every two seconds between an override and instantaneous telemetry. Tune, its numeric editor, the full error reader and MMU pages omit this dashboard.

| Row | Left | Center | Right |
|---|---|---|---|
| 1 | Nozzle actual/target (°C) | Speed override (%) / live velocity (mm/s) | Fan (0–100%) |
| 2 | Bed actual/target (°C) | Flow override (%) / volumetric flow (mm³/s) | Session Z offset (mm) |
| 3 | X (mm) | Y (mm) | Z (mm) |

The fan icon uses panel-native animation; its speed follows the fan percentage, rounded to 10 ms intervals. Unchanged intervals send no new command; 0% stops it.

![Panel-native fan animation at 0, 1, 50 and 100 percent](assets/framed/fan-animation-demo.gif)

Real UI emulator output with example data.

## Choose and start a print

<p align="center">
  <img src="assets/screens/framed/print-file.png" width="360" alt="File browser">
  <img src="assets/screens/framed/print-preview.png" width="360" alt="Model and filament preview">
</p>

1. Open **Home → Print**. Select a folder or G-code file. Folders appear first; **Back** goes up one level, or returns Home from the root.
2. Check the model preview, estimated time, tool changes, total filament length/weight and used filament colors/materials/weights when the slicer supplies them.
3. Select **Print** and press to start, or **Cancel** to return to the same file. Cancel is initially selected.

The browser follows Mainsail's name/date/size sorting and direction. Without a valid preference, newest files appear first. Hidden folders and non-G-code files are excluded.

Missing thumbnails or metadata do not prevent printing. Up to four used tools are shown; tool IDs such as T0 are slicer tools, not physical MMU gate numbers. Common previews are prepared ahead of time to make browsing faster.

## Printing and Tune

<p align="center">
  <img src="assets/screens/framed/printing.png" width="360" alt="Print progress and controls">
  <img src="assets/screens/framed/printing-paused.png" width="360" alt="Paused print">
  <img src="assets/screens/framed/tune.png" width="360" alt="Tune">
</p>

Print shows the preview, progress, elapsed/remaining time, estimated finish and optional layers. **Pause / Resume** act directly; **Stop** opens confirmation with **Back** initially selected. After confirming Stop, the live Print screen remains visible with an inactive **Stopping** button until cancellation is confirmed by printer state. Do not submit cancellation again while waiting. After completion or cancellation, **Close** returns Home.

Use **Tune** for Speed, **Flow**, temperatures/fan, Z offset, SCV, minimum cruise ratio, PA/smoothing and firmware retraction. Fields depend on configuration and telemetry. AFTER JOB switches only change policy pins; your macros implement the end-of-job actions. Z offset is not permanent probe calibration. See [fields, units and error behavior](print-controls.md).

## Prepare and Live jog

<p align="center">
  <img src="assets/screens/framed/prepare.png" width="360" alt="Prepare menu">
  <img src="assets/screens/framed/move.png" width="360" alt="Move, Live jog disabled">
  <img src="assets/screens/framed/move-live-jog.png" width="360" alt="Move, Live jog enabled">
</p>

**Prepare → Home** homes the printer. **Disable steppers** releases the motors. **Runtime Z offset** changes the current session's offset.

In **Prepare → Move**, select X, Y, Z or Extruder, edit the value and press to apply. With **Live jog** checkbox checked, encoder edits move immediately; with the checkbox empty, the movement is applied when confirmed.

Home the required axes first. Movement is unavailable during printing or pauses, and travel limits are enforced. Heat the nozzle before extrusion. If a failed jog leaves movement locked, check the printer and use **Control → Restore jog state** when offered.

## Temperature and preheat presets

<p align="center">
  <img src="assets/screens/framed/temperature.png" width="360" alt="Temperature controls">
  <img src="assets/screens/framed/preheat-settings.png" width="360" alt="Edit and save a preset">
  <img src="assets/screens/framed/prepare-preheat.png" width="360" alt="Prepare with named preheat presets">
</p>

- **Prepare → Preheat [name]** applies a preset. **Cooldown** turns off the heaters.
- **Control → Temperature** changes available hotend, bed and fan targets.
- Open a preset's **[name] settings**, edit its heater targets and choose **Save settings**. Saving the preset does not start heating. **Back** keeps unsaved edits; **Discard changes** restores the saved values for that preset. Wait for an ongoing save to finish before discarding edits.

Preset names and heater targets are shared with Mainsail when available; LCD edits are saved back there. Without Mainsail presets, local presets are used. Fan settings are not synchronized as temperature presets.

## Runtime motion limits

<p align="center">
  <img src="assets/screens/framed/control.png" width="360" alt="Control menu">
  <img src="assets/screens/framed/motion-runtime.png" width="360" alt="Runtime motion limits">
</p>

Open **Control → Motion** to adjust maximum velocity, maximum acceleration, square-corner velocity and minimum cruise ratio when supported. Press a field, rotate and press to apply. Changes are runtime settings; edit your Klipper configuration separately if you want permanent defaults.

## Screw adjustment

Requires a probe and four distinct corner screws in Klipper's `[screws_tilt_adjust]` configuration.

<p align="center">
  <img src="assets/screens/framed/screws-tilt.png" width="360" alt="Calculate screw adjustment">
  <img src="assets/screens/framed/screws-tilt-probing.png" width="360" alt="Probing corners">
  <img src="assets/screens/framed/screws-tilt-reading-results.png" width="360" alt="Reading results">
  <img src="assets/screens/framed/screws-tilt-adjust.png" width="360" alt="Screw directions and turn amounts">
  <img src="assets/screens/framed/screws-tilt-success.png" width="360" alt="Corners leveled">
</p>

1. Open **Leveling → Screws Tilt Adjust → Calculate**. Missing axes are homed before measurement.
2. Wait through **Probing corners…** and **Reading results…**.
3. Leave the **Base** screw unchanged. Turn the other screws according to **CW** (clockwise) or **CCW** (counter-clockwise) and the displayed amount. `01:20` means one full turn plus 20/60 of a turn.
4. Choose **Continue**, adjust as needed and calculate again. Green **Corners leveled / Tolerance achieved!** means the measured highest-to-lowest difference is below **0.05 mm**.

The screws are adjusted by you; the screen measures and gives instructions. This workflow does not save configuration.

## Bed mesh and saved profiles

<p align="center">
  <img src="assets/screens/framed/leveling.png" width="360" alt="Leveling menu">
  <img src="assets/screens/framed/mesh-calibrating.png" width="360" alt="Live point-by-point measurement">
  <img src="assets/screens/framed/mesh-results.png" width="360" alt="Measurement result, Save and Continue">
</p>

Open **Home → Leveling → Bed Mesh**. With a configured probe, **Calibrate** homes missing axes and measures the bed. After measurement, inspect the colored height map and minimum/maximum Z values.

During measurement, each probe result appears at its corresponding point. On completion and when opening a saved mesh, colors are scaled to that mesh’s minimum and maximum: lowest is blue, highest is red, with cyan, green and yellow between them.

- **Continue** returns to the menu and keeps the measured mesh for the current session.
- **Save** asks you to confirm the profile and restart. The measured mesh is saved as a generated `lcd_mesh_N` profile; Klipper restarts. Unrelated pending configuration changes can block saving.
- **Mesh Viewer** lets you inspect Current Mesh or saved profiles. Viewing does not load a profile, move the printer or change the active mesh. Low Y is at the bottom of the map.

<p align="center">
  <img src="assets/screens/framed/bed-mesh.png" width="360" alt="Bed Mesh menu">
  <img src="assets/screens/framed/mesh-profiles.png" width="360" alt="Saved mesh profiles">
  <img src="assets/screens/framed/mesh-viewer.png" width="360" alt="Default mesh height map">
  <img src="assets/screens/framed/mesh-pei.png" width="360" alt="Mesh height map">
</p>

**Cancel → Stop during measurement is an emergency stop:** Klipper enters shutdown. Use `FIRMWARE_RESTART` from the web console to recover. Cancel the confirmation if you want measurement to continue.

## Probe-offset calibration

<p align="center">
  <img src="assets/screens/framed/probe-calibration.png" width="360" alt="Start calibration">
  <img src="assets/screens/framed/probe-calibration-active.png" width="360" alt="Four movement buttons and live Z">
  <img src="assets/screens/framed/probe-calibration-accepted.png" width="360" alt="Save the accepted offset">
</p>

1. Ensure the bed is clear for calibration. The screen homes XYZ when needed, raises Z for clearance and moves the probe to the configured bed center before probing.
2. Open **Leveling → Probe Calibration → Start**.
3. Watch the live Z height between the lower and upper tested positions. Turn the knob to select one of the four **-- / - / + / ++** buttons and press it to move using Klipper's search steps.
4. Select **Accept** when satisfied, or **Cancel** to cancel the session.
5. After Accept, choose **Save** to persist the offset and restart Klipper, or **Continue** to leave it unsaved.

Printing must be stopped. Pending configuration changes do not block calibration. Saving is allowed only when the pending change is the accepted probe offset. Saving restarts Klipper; this is separate from the temporary runtime Z offset.

## Display settings

The top bar shows the Raspberry Pi's local system time in **HH:MM** format.

<p align="center"><img src="assets/screens/framed/display.png" width="360" alt="Brightness and idle dimming"></p>

Open **Home → Display**:

| Setting | Use |
|---|---|
| Brightness | Normal brightness, 0–100%; changes are visible while editing |
| Idle dim | Off, or 1–60 minutes without encoder input before dimming |
| Dim brightness | Brightness while dimmed, 0–100%; limited by normal brightness |

Press to edit, rotate and press again to save. Settings survive display power cycles. Defaults are **100%**, **Off** and **10%**. If saving fails, the edit stays open; press to retry.

The first encoder movement or click after idle dimming wakes the display without performing a menu action. **0% turns off the backlight**; while editing Brightness, rotate clockwise to increase it again.

### Buzzer and button sounds

<p align="center">
  <img src="assets/screens/framed/buzzer.png" width="360" alt="Choose the buzzer output">
  <img src="assets/screens/framed/display-sound-settings.png" width="360" alt="Sound options under Display">
  <img src="assets/screens/framed/display-volume-edit.png" width="360" alt="Edit the volume">
</p>

Open **Display → Buzzer** to choose one of the configured `[pwm_cycle_time name]` outputs, or **Disabled**. Pressing a choice saves it and returns to Display. With an available output selected, **Volume**, **Click tone** and **Encoder tone** appear below Buzzer in Display.

Press an audio setting, rotate to adjust it and press again to save. Volume uses 10% steps from 0 to 100%. Tones include Off, Tick, Short beep, Low, High and Double. Output and sound preferences survive restarts. Sounds play in the background; rapid rotations do not build a sound queue. If the selected section is removed from Klipper configuration, sound controls are hidden until an available output is chosen.

## Maintenance (experimental feature branch)

**Home → Maintenance** is the tile before Info. Its **Diagnostics** menu reads supported host/Klipper information on demand, while **Self Tests** shows only discovered, explicitly permitted part fan, generic fan, case light, LED or buzzer targets. No command runs merely by opening a menu.

Select a physical test, allow the safety/baseline check, deliberately choose **Run short pulse** (the default is Cancel), and wait for the original setting to be verified after the pulse. Only then can you report **Yes, observed** or **Not observed**; this user-observed result is not measured RPM or an automatic hardware PASS. An unknown output or failed restore remains blocked or inconclusive.

The older placeholder screenshot is preserved in the [gallery](screenshots.md) as a historical reference, **not** a depiction of the current menu. See [safe output profile registration](maintenance-profiles.md), [LCD interaction](maintenance-ui.md), and [real Raspberry Pi acceptance](maintenance-stage8-acceptance.md). Real actuator tests are not yet physically accepted.

## Info and updates

<p align="center">
  <img src="assets/screens/framed/info-overview.png" width="360" alt="Machine, Wi-Fi and host">
  <img src="assets/screens/framed/info-mcu-details.png" width="360" alt="MCU status">
  <img src="assets/screens/framed/info-mcu-overview.png" width="360" alt="MCU and software sections">
  <img src="assets/screens/framed/info-software.png" width="360" alt="Software versions">
</p>

Open **Home → Info** or **Control → Info**, then rotate to scroll through Machine, Host, MCUs and Software. Check printer dimensions, network/IP, Wi-Fi name/signal, CPU/RAM/temperature, MCU connection/load/temperature and installed software versions. Unavailable values show `N/A` or an unavailable status. MCU temperature needs a configured `temperature_mcu` source; Wi-Fi details require Linux `iw`.

<p align="center">
  <img src="assets/screens/framed/info-project.png" width="360" alt="Project QR and check for updates">
  <img src="assets/screens/framed/info-update-checking.png" width="360" alt="Checking for updates">
  <img src="assets/screens/framed/info-update-current.png" width="360" alt="Up to date">
</p>

Scan the project QR to open the repository. To update from the LCD:

1. Leave the printer idle and scroll to **Check for updates**. Press the encoder.
2. Wait for **Checking…**. Green **Up to date** means no update is needed; an available update changes the button to **Update**.
3. Select **Update** to install Petrel. Moonraker restarts the service afterwards. This does not update every printer component.

If the checkout is dirty or invalid, **Soft recovery** offers a second **Confirm recovery** step. Recovery discards local repository changes; back up anything you need first. Rotating cancels confirmation. Recovery does not automatically install an update. If a result is unconfirmed, check Mainsail Update Manager before retrying.

## Case light

<p align="center"><img src="assets/screens/framed/case-light.png" width="360" alt="Case Light"></p>

**Control → Case Light** appears for a configured `output_pin case_light`. Use On/Off and adjust PWM brightness from 0–100%. On restores the last positive brightness, or 100% when none is known. No macro is needed.

A PWM-capable output can be configured as follows; replace `PA3` with your actual light-control pin:

```ini
[output_pin case_light]
pin: PA3
pwm: True
value: 1.0
shutdown_value: 0
cycle_time: 0.01
```

## Printer power

<p align="center">
  <img src="assets/screens/framed/power-confirm.png" width="360" alt="Power-off confirmation">
</p>

Configure the Moonraker power-device name with `./configure.sh`. Hold the encoder button to turn it on; the default hold is **2 seconds**. This works while Klipper or the display is offline, provided the Pi/service and Moonraker remain available.

From any screen, **hold the encoder button for 1.2 seconds, then release** to open power-off confirmation. No hold indicator appears during the first 450 ms; then a small **Hold for power** popup shows the progress. **Cancel is selected initially**; rotate clockwise to select **Power off**, then confirm with a separate short click. Cancel restores the current screen and uncommitted editor value. Shutdown is blocked during printing, paused printing, or an operation in progress. Short clicks act on release without an additional timeout. Releasing an incomplete hold between 450 ms and 1.2 seconds does not select a menu item.

When a relay powers both the printer and display while the Pi stays running, powering back on returns to the first Home page. Wait for startup to finish before using the menus.

When the configured Moonraker power device turns on, Petrel starts nonblocking LCD handshakes at 150 ms intervals. If that device is absent, Klipper becoming ready triggers the same fast connection window. After 10 seconds without a response, handshake requests fall back to 5-second intervals. The connected panel is reused without a fixed 750 ms wake delay.

### Power workflow example

![Power hold, release, incomplete-hold cancellation and active-print blocking](assets/framed/power-shortcut-demo.gif)

Real UI emulator output with example data. [Original panel PNGs](screenshots.md) and [reproduction](ui-emulator.md#refresh-pngs-frames-and-gifs).
