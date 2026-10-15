# Maintenance actuator opt-in profiles

[Türkçe](maintenance-profiles_TR.md)

The Stage 8 self-test only permits an actuator if three independent conditions are satisfied: **explicit operator registration**, **real Klipper discovery**, and **known safe effective configuration and original output readback**. Fan F01 requires no extra profile because Klipper's named `fan` object has dedicated part-cooling semantics. An arbitrary `output_pin` must never be inferred to be a case light or buzzer.

To deliberately enable the optional native Petrel case-light test or an installed buzzer, create the following small file on the Pi as the Petrel service user:

`~/.config/Petrel/maintenance-test-profiles.json`

```json
{
  "version": 1,
  "case_light": true,
  "buzzer_output": "tick"
}
```

Replace `tick` with the exact output name from your configured `[pwm_cycle_time tick]` section. Set `case_light` to false and `buzzer_output` to an empty string to disable the respective profile. **Do not copy this example unchanged unless the hardware really matches.** Profiles are read only on the next Klipper READY epoch/service restart. No G-code or GPIO is executed when reading them.

Only `[output_pin case_light]` with PWM enabled and scale 1 can be approved as case light. Only a verified `[pwm_cycle_time <output>]` with initial value 0, shutdown value 0, valid scale and an exact opt-in output name can be approved as buzzer. The program still requires live OFF/readback proof and explicit per-test confirmation. Malformed, missing or oversized profiles grant zero permissions. Physical tests are never automatic. CI provides only simulated evidence, not hardware PASS.
