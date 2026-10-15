# Maintenance capability discovery (development)

[English](maintenance-discovery.md) · [Türkçe](maintenance-discovery_TR.md)

**Status:** Discovery core, lazy snapshot owner, and unit tests only. No Maintenance UI actions or printer-side tests have been enabled. This is an implementation milestone, not the final support matrix.

## Design constraints

- `maintenance_discovery.py` is independent of the existing `printer_capabilities.py`. The latter must not be changed by Maintenance development.
- `discover(state, services=())` only reads existing, authoritative `PrinterState` data from the Klipper/Moonraker subscription. It does **not** send G-code, issue discovery HTTP requests, copy configuration dictionaries, retain the input state, create threads, or open sockets.
- Named Moonraker/Petrel services are enabled only by **positive API evidence** passed by the caller; an unverified service is not assumed available.
- A result represents an available **method**, not a completed health check or permission to run a command. Test execution must independently enforce idle/printer state, device limits, connection epoch, actuator safety, and user approval.
- No confidence is inferred from macro names, arbitrary output pins, or commands merely returning `ok`. If no meaningful observation exists, the test remains hidden.
- Long-lived results contain only an immutable epoch, device name/type, compact integer method masks, and a global method mask. No response body, settings mapping, status mapping, or sample history survives discovery.
- The discovery module is designed to be **loaded lazily** when Maintenance is integrated. It is **not yet imported by the running Petrel UI**, so this stage adds no normal-print code path.

## Lazy snapshot owner

`maintenance_cache.py` provides `MaintenanceCache.get(state, services=())`. It does not import the discovery module until `get` is called. A matching Klipper epoch, effective settings identity and positively confirmed service set reuse the **same** immutable snapshot; a new config/epoch or service set recomputes it. A disconnected state clears the result. The cache keeps only that snapshot, not its source state. **This owner is not yet wired to the UI.**

## Method flags

| Flag | Meaning |
|---|---|
| `AUTOMATIC` | Real firmware/sensor evidence is available |
| `USER` | A meaningful, directly observable user confirmation is possible |
| `EXTERNAL` | Requires a real measurement tool and a numeric user entry |
| `CALIBRATION` | Supported guided Klipper calibration |
| `INFORMATION` | A view/estimate/history, **not** proof of functionality |
| `NONE` | Not positively supported; hidden |

Multiple flags can coexist. 121 standardized IDs (`F01–F13`, `H01–H18`, `M01–M17`, `P01–P22`, `R01–R08`, `E01–E15`, `S01–S20`, `O01–O08`) have a reserved five-bit slot in each compact mask. An unimplemented or unproven ID remains zero.

`MaintenanceSnapshot.method(feature, device=None)` returns the flags for one device or a global feature. `instances(feature)` selects the supported devices. All objects are immutable; no persistent per-feature dictionaries are created.

## First discovery milestone

The first pass covers configured heaters, the common Klipper fan families, physical endstop candidates, motion/stepper entries, a conservative subset of TMC fields, standard and load-cell probe support, manual and automatic bed-mesh prerequisites, resonance/accelerometer prerequisites, filament sensors, a restricted group of environmental sensors and LEDs, and explicitly confirmed host/service capabilities.

**Not yet claimed as automatically supported:** unproven TMC register fields, hidden advanced analysis without historical baselines, unknown actuator functions, arbitrary G-code macros, arbitrary servo motions, unconfigured diagnostic integrations, and tests whose sensor reports cannot be accessed as structured data. Those IDs remain hidden until their adapter and evidence policy are implemented.

Fan `tachometer_pin` indicates potential automatic RPM verification. The test runner must still subscribe to actual RPM and validate samples before recording a pass. Heater/control fan tests must not bypass Klipper's automatic safety logic. Motion telemetry is not physical position feedback.

## Performance tests

```sh
python3 -m unittest discover -s tests -p 'test_maintenance_discovery.py' -v
python3 tools/benchmark_maintenance_discovery.py --fans 150 --runs 20
```

The benchmark reports discovery duration, `tracemalloc` retained allocation delta, tracked peak allocation and Linux `/proc/self/smaps_rollup` RSS/PSS/USS changes. Measurements are **synthetic and environment-specific**: run the same benchmark on Pi Zero 2 W and compare the **real Petrel process** before and after UI integration. Passing the Python-only memory test does not guarantee that OS RSS is released by CPython.

**Acceptance target, not a measured guarantee:** no extra persistent worker/socket/polling; under 100 KiB retained snapshot for the supported realistic device inventory; no discovery work in the printing hot path; aim for under 1 MiB additional steady-state RSS after first Maintenance use. If the measured budget is exceeded, revisit the architecture before enabling the feature.

## Next stages

1. Complete the remaining recognized test adapters with verified API evidence and dedicated regression cases.
2. Wire the existing lazy Maintenance snapshot owner to Maintenance entry only; do not alter the printing hot path.
3. Connect relevant Moonraker service evidence and **on-demand** test telemetry without always-on subscriptions.
4. Build execution/safety arbitration independently from discovery; design the UI only after the discovery matrix is verified.

## Extended API-backed discovery and complete ID contract

The completed discovery *decision engine* recognizes the entire 121-ID
contract. This does **not** mean every ID becomes visible: unsupported,
unsafe or unmeasurable tests are deliberately hidden (`NONE`). In particular,
`M02`, `M17`, `R07`, `R08`, `E10`, `O07`, and `O08` have no general valid
measurement method. Historical trends, controller overrides, travel counters,
MMU tests, and arbitrary actuators require a verified, explicitly registered
integration/baseline/safe operating profile; they cannot be inferred by name.

| Area | Requirements for visibility |
|---|---|
| Fans | Individual Klipper fan object; tachometer pin only for RPM-based modes. A plain PWM fan retains a meaningful user-confirmed test; automatic heater/controller fans are **not** forcibly bypassed. |
| Heating | Independently identified hotend, bed and generic heater plus configured thermal limits; heater trend and electrical-energy estimates require *separate* verified records. |
| Motion | Real physical switch for press/release test. TMC register, temperature or current modes need actual structured fields or configured current. No physical-position accuracy is inferred from commanded coordinates. |
| Probe / mesh | Load-cell and eddy probes use their own methods. Manual mesh remains separate from probe-based mesh. Historical drift requires a stored, compatible baseline. |
| Resonance | Explicit accelerometer assignment in `[resonance_tester]`, not mere accelerometer presence. Frequency, belt comparisons and trends never accept unaided human estimates. |
| Filament / MMU | Presence and motion sensors are distinct; unrestricted servos, macro names and actuators never qualify as safe tests. |
| Host | Positive Moonraker API responses only. No invented disk API and no large directory listing at global discovery. |

### Entry-only service evidence

`maintenance_services.parse_evidence(responses)` classifies verified Moonraker
JSON responses. `probe(client, cancelled)` performs small read-only calls to
`/server/info`, `/machine/proc_stats`, `/machine/system_info`, and
`/server/history/totals`, **only when invoked by the Maintenance entry owner**.
It reuses Petrel's existing HTTP transport and read worker; it does not create
connections or run during the regular print tick. Optional endpoints fail
closed. `MaintenanceDiscoverySession` owns the temporary Future and cancellation
flag, clears them after completion and drops its snapshot on exit. Already
in-flight HTTP requests cannot be interrupted forcibly, but cancel stops the
next request from being started.

Other capability tags (`maintenance.*` or `petrel.*`) are explicit positive
evidence contracts for **future independently verified integrations**, not
claims that Petrel already records every baseline or has a safe actuation
profile. Until an integration provides that evidence, the feature stays hidden.

### Explicit performance and integration boundary

The display only loads this module when entering Maintenance. The existing
`PrinterCapabilities` is untouched. The feature/UI lookup does not run in the
printing hot path, and exiting Maintenance releases the cached snapshot. CPU,
RSS, USS and PSS must still be measured on real Pi Zero 2 W hardware before
claiming an absolute production memory budget. Unit tests and synthetic
benchmarks are not proof of real printing-time zero overhead.
