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