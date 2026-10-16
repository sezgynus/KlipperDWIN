# Maintenance auxiliary hardware

[Turkish](maintenance-auxiliary_TR.md)

O03/O04 keep the existing explicitly approved light/output and LED runners. No arbitrary output, unknown macro or missing-MMU pseudo test is added.

O01 requires an exact registered gcode_button plus a benign empty/message-only action. Unknown macros, motion commands and Jinja actions are rejected even if a profile names the button. The test reads RELEASED → PRESSED → RELEASED from fresh firmware status; it does not execute the button's G-code.

O02 requires an explicit safe servo range and 2–5 test angles within firmware limits. The initial nonzero reported PWM must map inside that range; a deenergized servo has unknown mechanical position and cannot be assumed safe. Each angle needs a separate operator action. After the last angle, the original pulse width is restored and read back before user observation. This verifies reported PWM and coarse observed motion, not measured angle/torque. Active uncertain cancellation uses Klipper emergency_stop rather than an unverified reverse movement.

O05 reads only the declared ambient sensor; it cannot prove hotend accuracy. O06 displays declared physical-service steps with explicit acknowledgments and records user-performed service, not measured component health. Cold idle heaters and disabled motors are required. User questions never expire.

Declare roles in ~/.config/Petrel/maintenance-auxiliary.json:
```json
{
  "version": 1,
  "buttons": ["gcode_button service"],
  "servos": [{"object":"servo hatch","minimum_angle":30,"maximum_angle":150,"angles":[60,120]}],
  "ambient_sensor": "temperature_sensor room",
  "tasks": [{"id":"inspect_belt","label":"Inspect belt","steps":["Inspect for wear","Check fasteners"]}]
}
```
These are examples, never printer-specific defaults. Review the entire physical servo path and the actual servicing instructions for your machine. Safe declarations do not replace firmware limits or authorize arbitrary macros. Changes are discovered at the next Klipper READY epoch. Physical acceptance remains deferred.
