# Maintenance filament and MMU

[Turkish](maintenance-filament_TR.md)

E01/E07 require a known active extruder, stable temperature above min_extrude_temp, can_extrude, clear path and homing. They command 5 mm at 1 mm/s using acknowledged SAVE/movement/non-moving cleanup. Modal state is read back. E02 commands 10 mm, requires an external measured length, and reports the error; it never rewrites rotation_distance.

E03 suppresses sensor insert/runout macros with ENABLE=0, then measures absent → present → absent and restores the original enabled state. E04 uses a 5 mm feed with the matched extruder and requires a fresh false → true motion indication. A latched true signal without a fresh transition is insufficient; sensor indication is not measured feed length. Unknown restoration is explicitly reported.

E05 reads actual diameter. E06 persists bounded explicit captures with timestamps and configuration identity, not continuous/lifetime monitoring. E08 requires real ten-second load-cell samples and no reported sensor errors. E09 requires tare, a declared traceable reference (50–25000 g), a numerical calibration result and matching pending configuration. No SAVE_CONFIG is sent.

E11 requires MMU disabled in its ordinary menu before handling sensor fragments, preventing autoload. Choose each actual sensor and verify absent → present → absent. E12 compiles only existing MMUSession grip/release/selector-home operations and checks the existing firmware-state verifier; clear all MMU mechanics. Empty action sequences cannot PASS.

Optional role file: ~/.config/Petrel/maintenance-filament.json, version 1. Supported keys:
- dryers: up to four explicit objects with object, target, ceiling, duration_s (30–21600 s); only configured heater_generic objects, target < ceiling < max_temp and 5–15 °C margin.
- chamber_sensor: exact configured humidity-sensor object.
- loadcell_reference: a named traceable reference/instrument.
- material_history: up to sixteen linked spool_id/material/used_mm/source records.

E14 runs only declared dryers, in bounded hold segments with fresh thermal checks and OFF readback. Cancel or an unknown active command requests Klipper emergency_stop. No generic heater is assumed to be a dryer. E13 requires actual Spoolman API evidence and reports declared linked usage, not wear. E15 reports chamber humidity, not moisture inside filament. Both are INFORMATION diagnostics.

Every subsequent action refreshes queue/lifecycle checks. Human questions never expire. Firmware failure does not trigger movement replay. CI is not physical acceptance.
