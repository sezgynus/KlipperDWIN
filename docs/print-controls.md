# Print and Tune controls

[English](print-controls.md) · [Türkçe](print-controls_TR.md) · [Documentation](README.md)

## Manage a print

1. Choose a file under **Home → Print**, then select **Print** on its preview.
2. Watch progress, elapsed/remaining time and estimated finish time. The thumbnail and `print_stats.info` layer data are optional; layers are never inferred from Z height.
3. **Pause / Resume** act directly. **Stop** opens confirmation with **Back** initially selected.
4. When the job completes, select **Close** to return Home.

![Example Print and Tune workflow](assets/framed/print-controls-demo.gif)

Offline emulator output from the real UI and driver, using example state data. See the [emulator guide](ui-emulator.md) for reproduction.

## Adjust with Tune

Use **Tune → field → rotate → Apply**. PRINT, MOTION, EXTRUSION and AFTER JOB share one page. Controls appear only for supported devices and valid telemetry; the following 17 fields show the maximum scope.

| Group | UI label | Unit | Visibility | Effect |
|---|---|---|---|---|
| PRINT | Speed | % | Ready printer | M220 speed override |
| PRINT | Flow | % | Active hotend | M221 extrusion override |
| PRINT | Fan | % | Part-cooling fan | Fan target, 0–100% |
| PRINT | Nozzle | °C | Active hotend | Nozzle target |
| PRINT | Bed | °C | Heater bed | Bed target |
| PRINT | Z offset | mm | Runtime offset available | Session adjustment; no saved probe calibration |
| MOTION | SCV | mm/s | Toolhead reports the field | Square-corner velocity |
| MOTION | Min cruise ratio | % | Toolhead reports the field | Minimum cruise ratio; sent as value / 100 |
| EXTRUSION | Pressure advance | — | Active extruder reports PA | Runtime pressure advance; UI shows no unit |
| EXTRUSION | PA smooth time | s | Active extruder reports smooth_time | Pressure-advance smoothing window |
| EXTRUSION | Retract length | mm | firmware_retraction + telemetry | Firmware retract distance |
| EXTRUSION | Retract speed | mm/s | firmware_retraction + telemetry | Firmware retract speed |
| EXTRUSION | Unretract extra | mm | firmware_retraction + telemetry | Extra length on unretract |
| EXTRUSION | Unretract speed | mm/s | firmware_retraction + telemetry | Firmware unretract speed |
| AFTER JOB | Heaters off | On/Off | Turn_OFF_Heaters_After_Job | Set policy pin only |
| AFTER JOB | Motors off | On/Off | Disable_Motors_After_Job | Set policy pin only |
| AFTER JOB | Printer power off | On/Off | Power_OFF_Printer_After_Job | Set policy pin only; no immediate shutdown |

Settings apply at runtime; edit Klipper configuration separately for persistent defaults. Firmware retraction settings affect G10/G11 usage; they do not rewrite explicit extrusion moves from the slicer.

A value or switch immediately shows the new choice. If the command is rejected, it returns to the current subscribed value and briefly blinks red twice. A slow response alone is not rejection. Older replies cannot overwrite a newer edit; reconnects invalidate pending edits. If the result is unclear, check Mainsail before retrying.

## Recover from an MMU error

Happy Hare shows the active tool's mapped gate color/material. Toolchange source/target use reported `last_tool` / `next_tool`; unknown values are never guessed.

1. An MMU lock keeps you on Print, shows the reason and replaces **Resume** with **MMU**.
2. Select **MMU** to open the full error reader; rotate to scroll long text.
3. Select **MMU recovery** for recovery, or **Back** to return to Print.
4. Fix the physical problem and follow the [recovery steps](mmu-guide.md); select **Resume** separately when ready.

These controls are absent without an MMU.

## Power shortcut

**Hold for 1.2 seconds, then release**; progress appears after 450 ms. Releasing an incomplete hold does not activate a menu item. Cancelling preserves a Tune draft. Power off is blocked during printing and pauses; cancel the job first. Power-on has a separate **2-second** default. See [printer power](user-guide.md#printer-power).

## Optional job policy switches

Petrel recognizes these exact three digital output pin names independently:

```ini
[output_pin Turn_OFF_Heaters_After_Job]
pin: virtual_pin:Turn_OFF_Heaters_After_Job_pin
value: 1

[output_pin Disable_Motors_After_Job]
pin: virtual_pin:Disable_Motors_After_Job_pin
value: 1

[output_pin Power_OFF_Printer_After_Job]
pin: virtual_pin:Power_OFF_Printer_After_Job_pin
value: 0
```

`virtual_pin:` requires your installed Klipper virtual-pins extension; it is not a built-in Klipper pin provider. Alternatively use suitable output pins. Petrel does not install an extension or modify macros.

Switching a row sends only `SET_PIN PIN=<exact name> VALUE=0|1`. It does **not** immediately stop heaters, disable motors or power off the printer. Your START_PRINT / END_PRINT macros decide what each pin means. For example:

```jinja
{% if printer['output_pin Turn_OFF_Heaters_After_Job'].value|int %}
  TURN_OFF_HEATERS
{% endif %}
{% if printer['output_pin Disable_Motors_After_Job'].value|int %}
  M84
{% endif %}
```

Handle `Power_OFF_Printer_After_Job` in your own end-print power macro using your configured Moonraker power device and cooling policy. Undefined pins, PWM pins and pins without a known digital value are hidden.

## State examples

| Step | Visual evidence |
|---|---|
| Edit Flow → Apply; fewer configured features | [Editor](assets/screens/tune-edit.png) · [Reduced Tune](assets/screens/tune-limited.png) |
| Rejected value/switch/Pause | [Two red blinks and rollback GIF](assets/framed/rejected-controls-demo.gif) |
| Read long MMU error with encoder → Back | [Scrolling GIF](assets/framed/mmu-error-scroll-demo.gif) · [Full error](assets/screens/error-full.png) |
| Stop → Back initially selected | [Stop confirmation](assets/screens/stop-confirm.png) |
| Hold → release → confirm; incomplete hold/active-print blocking | [Power shortcut GIF](assets/framed/power-shortcut-demo.gif) · [Preserved draft](assets/screens/tune-hold-cancel.png) |
| Missing preview or layer data | [Print without metadata](assets/screens/print-no-metadata.png) |

![Rejected value, job switch and Pause command blink red twice](assets/framed/rejected-controls-demo.gif)

These are offline emulator outputs from the real UI with example states. [Production commands](ui-emulator.md#refresh-pngs-frames-and-gifs) and [complete gallery](screenshots.md).
