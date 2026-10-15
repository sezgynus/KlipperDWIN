# Stage 8D: Graphite Maintenance UI

[Türkçe](maintenance-ui_TR.md)

Maintenance is a passive entry: **Self Tests** and **Diagnostics** are shown without GETs or physical commands. Self Tests enumerate only the strictly discovered Stage-8 guided targets; Diagnostics enumerate available read-only adapters. No unsupported hardware is promised.

For a Self Test, select the exact device, allow the bounded read-only safety/queue/baseline preflight, rotate the encoder from the default **Cancel** choice to **Run short pulse**, and press to confirm within three seconds. During the pulse the backend submits one short restore-bearing script and reads the output back. A restored state permits a separate **Did it work?** choice; **Not observed** is the default and **Yes, observed** must be explicitly selected to generate `PASSED_USER`. A verification error yields `INCONCLUSIVE`, even if light or fan movement was seen. No physical RPM reading is implied. The UI never retries ambiguous commands.

The display UI does not start the hardware pulse from navigation, menu entry, or a page redraw. Physical tests are deliberately unavailable if their original status/config/profile cannot be positively verified. Only safe read-only Diagnostics can be used without a guided actuator test.

CI covers keyboard/encoder navigation and no-actuation entry with fake Moonraker and mock display. Actual fan, LED, buzzer and case-light tests must be performed explicitly on a safely idle real printer before claiming device acceptance.
