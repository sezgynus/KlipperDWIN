# Maintenance: generic actuator role profiles

[Türkçe](maintenance-profiles_TR.md)

Maintenance **never** assumes what is wired to a Klipper GPIO or infers a physical role from an output's name. A standard Klipper `fan` already has defined semantics; other physical actuators need an explicit role declaration. All output names, pins, counts and assignments come from the running printer and the operator's **per-printer** profile, not Petrel source code.

Create `~/.config/Petrel/maintenance-test-profiles.json` as the Petrel service user. The **version-2 format** is:

```json
{
  "version": 2,
  "actuators": [
    {"object": "output_pin enclosure", "role": "visual"},
    {"object": "output_pin tool_lamp", "role": "visual"},
    {"object": "pwm_cycle_time Alarm", "role": "audible"},
    {"object": "fan_generic aux", "role": "fan"},
    {"object": "neopixel board", "role": "led"}
  ]
}
```

Names here are examples, **not Petrel defaults**. Replace them with actual Klipper object names; leave unwanted entries out. A role is an explicit operator declaration, not physical proof. The file is parsed only at the next Klipper READY epoch (for example following an idle-printer Petrel service restart); merely entering the Maintenance menu never triggers discovery or G-code.

| Role | Required Klipper object and checks | Guided test |
| --- | --- | --- |
| `visual` | Named `output_pin` with PWM, `scale=1`, configured physical pin, queryable current value | O03 visual output change and baseline restore |
| `audible` | Named `pwm_cycle_time`, physical pin, finite valid scale, explicit zero `value` and `shutdown_value` | S18 short tone, OFF attempt, **human-observed** sound and stop |
| `fan` | Existing `fan_generic` object with separate live baseline | F04 fan pulse |
| `led` | Existing `led` / `neopixel` / `dotstar` / `pca9632` object with single-pixel restorable status | O04 LED pulse |

Up to **16** entries and **2048 bytes** are accepted. Unknown keys/roles, duplicates, unsafe output identifiers, absent objects, unsafe settings and invalid file formats grant no extra access. Individual correctly declared but absent targets remain disabled. Legacy **version 1 is deliberately fail-closed**: migrate to version 2 before testing. The old `case_light: true` becomes `{"object":"output_pin <actual_name>","role":"visual"}`; old `buzzer_output: "<name>"` becomes `{"object":"pwm_cycle_time <actual_name>","role":"audible"}`. The former `fan_generic_output` and `led_output` become `fan` and `led` entries with full Klipper object names.

S18 is now **per device**, not one global buzzer flag: multiple independently configured audible outputs create distinct rows. `pwm_cycle_time` is normally absent from `printer.objects.list`, so its positively approved effective settings provide structural evidence. The original case-sensitive `SET_PIN PIN=...` spelling is resolved from raw Klipper config in a read-only preflight, and its pin is checked against effective settings. O03 uses the same raw-config name validation and additionally requires a live readback before a pulse. There is no fabricated audible runtime status. An observed sound is `OBSERVED_USER` with `restore_verified=False`, never proof of telemetry-backed restoration.

**Safety:** No profile permits automatic G-code on discovery/menu entry. Every physical pulse requires idle/queue checks, a second explicit confirmation and bounded command dispatch. Unknown original state or missing raw pin evidence blocks execution. Commands are never dispatched merely because an object name contains `light`, `buzzer` or similar text. GitHub CI uses fakes and cannot count as physical acceptance.

**O04: generic versus recognized extension LEDs.** Standalone Klipper LED objects use the explicit \`led\` role profile, with a complete reported baseline, bounded indexed commands, full restoration checks and mandatory user observation. Standard Happy Hare-controlled LED segments are different: an exact \`mmu_leds\` configuration mapping plus loaded physical/MMU status objects provides known positive LED semantics, so Petrel **automatically discovers an O04 guided candidate without machine-specific profile entries**. It supports exit, entry, status and logo segments, nonoverlapping subsets, and multiple MMU units. Happy Hare retains controller ownership; Petrel only sends short \`MMU_SET_LED ... DURATION=0.40\` requests after explicit UI consent and live safety checks. HH color restore is not electronically proven; an operator-observed result is \`OBSERVED_USER\`, \`restore_verified=False\`. Conflicting/partial-unknown mappings fail closed. Neither discovery route ever sends automatic G-code.

Happy Hare auto-discovery requires a positively mapped physical LED segment and trustworthy numeric unit identity. Effective `mmu_machine.units` ordering is used if available. If not, a live one-unit (`num_units=1`, `unit_0`) installation with exactly one MMU LED controller is unambiguous even if its `unit_0.name` is a friendly display label different from the config section. For multi-unit installations, canonical ordering must be verified; display labels never authorize a guessed index. Discovery is passive; dispatch and physical PASS still require explicit operator consent and observation.

O04's supported RGB/RGBW outputs now run the same four-color, full-scale user-observed procedure: red, blue, green, white, followed by cleanup. Monochrome `[led]` objects lacking configured red/green/blue outputs are rejected for this RGB procedure, not misreported as an RGB PASS. Happy Hare-owned outputs use short native time-limited color effects; standalone indexed outputs restore their full original per-pixel RGB/RGBW values.
