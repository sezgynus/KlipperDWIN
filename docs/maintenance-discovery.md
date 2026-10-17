# Maintenance capability discovery (development)

[English](maintenance-discovery.md) · [Türkçe](maintenance-discovery_TR.md)

**Status:** This discovery module runs once per Klipper READY configuration epoch and remains passive. The separate [Stage-8 Maintenance engine](maintenance-stage8-acceptance.md) now implements guarded opt-in hardware tests; discovery never starts a test itself.

## Design constraints

- `maintenance_discovery.py` is independent of the existing `printer_capabilities.py`. The latter must not be changed by Maintenance development.
- `discover(state, services=())` only reads existing, authoritative `PrinterState` data from the Klipper/Moonraker subscription. It does **not** send G-code, issue discovery HTTP requests, copy configuration dictionaries, retain the input state, create threads, or open sockets.
- Named Moonraker/Petrel services are enabled only by **positive API evidence** passed by the caller; an unverified service is not assumed available.
- A result represents an available **method**, not a completed health check or permission to run a command. Test execution must independently enforce idle/printer state, device limits, connection epoch, actuator safety, and user approval.
- No confidence is inferred from macro names, arbitrary output pins, or commands merely returning `ok`. If no meaningful observation exists, the test remains hidden.
- Long-lived results contain only an immutable epoch, device name/type, compact integer method masks, and a global method mask. No response body, settings mapping, status mapping, or sample history survives discovery.
- Discovery runs on the first authoritative Klipper READY update for an epoch. It does not run on menu entry or ordinary printing-time status updates.

## READY-epoch snapshot owner

`maintenance_cache.py` provides `MaintenanceCache.get(state, services=())`. It loads the discovery module at the first READY epoch. A matching Klipper epoch, effective settings identity and positively confirmed service set reuse the **same** immutable snapshot; a new config/epoch or service set recomputes it. A disconnected state clears the result. The cache keeps only that snapshot, not its source state. The backend owns the snapshot throughout that READY epoch. Menu entry and exit only read it; disconnection invalidates it.

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

## Implemented capability coverage

The discovery implementation covers configured heaters, the common Klipper fan families, physical endstop candidates, motion/stepper entries, a conservative subset of TMC fields, standard and load-cell probe support, manual and automatic bed-mesh prerequisites, resonance/accelerometer prerequisites, filament sensors, a restricted group of environmental sensors and LEDs, and explicitly confirmed host/service capabilities.

**Not yet claimed as automatically supported:** unproven TMC register fields, hidden advanced analysis without historical baselines, unknown actuator functions, arbitrary G-code macros, arbitrary servo motions, unconfigured diagnostic integrations, and tests whose sensor reports cannot be accessed as structured data. Those IDs remain hidden until their adapter and evidence policy are implemented.

Fan `tachometer_pin` indicates potential automatic RPM verification. The test runner must still subscribe to actual RPM and validate samples before recording a pass. Heater/control fan tests must not bypass Klipper's automatic safety logic. Motion telemetry is not physical position feedback.

## Performance tests

```sh
python3 -m unittest discover -s tests -p 'test_maintenance_discovery.py' -v
python3 tools/benchmark_maintenance_discovery.py --fans 150 --runs 20
```

The benchmark reports discovery duration, `tracemalloc` retained allocation delta, tracked peak allocation and Linux `/proc/self/smaps_rollup` RSS/PSS/USS changes. Measurements are **synthetic and environment-specific**: run the same benchmark on Pi Zero 2 W and compare the **real Petrel process** before and after UI integration. Passing the Python-only memory test does not guarantee that OS RSS is released by CPython.

**Acceptance target, not a measured guarantee:** no extra persistent worker/socket/polling; under 100 KiB retained snapshot for the supported realistic device inventory; no discovery work in the printing hot path; aim for under 1 MiB additional steady-state RSS after Klipper READY. If the measured budget is exceeded, revisit the architecture before enabling the feature.

## Next stages

1. Complete the remaining recognized test adapters with verified API evidence and dedicated regression cases.
2. Preserve the current READY-epoch snapshot between Maintenance visits and invalidate it on disconnect.
3. Read Moonraker service evidence once at READY; subscribe to any additional test telemetry only when a user starts a test.
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

### READY-epoch service evidence

`maintenance_services.parse_evidence(responses)` classifies verified Moonraker
JSON responses. `probe(client, cancelled)` performs small read-only calls to
`/server/info`, `/machine/proc_stats`, `/machine/system_info`, and
`/server/history/totals`, **once after Klipper reports READY**.
It reuses Petrel's existing HTTP transport and read worker; it does not create
connections or run during the regular print tick. Optional endpoints fail
closed. `MaintenanceDiscoveryManager` owns only a small immutable snapshot, lock and
connection generation. The existing Maintenance read worker performs a single
short-lived service probe, and publishes its result only if the original READY
epoch still matches. No API request is started by entering or leaving the menu.

Other capability tags (`maintenance.*` or `petrel.*`) are explicit positive
evidence contracts for **future independently verified integrations**, not
claims that Petrel already records every baseline or has a safe actuation
profile. Until an integration provides that evidence, the feature stays hidden.

### Explicit performance and integration boundary

Discovery is performed by the printer backend when Klipper becomes READY, independent of the display. The existing
`PrinterCapabilities` is untouched. The feature/UI lookup does not run in the
printing hot path, and exiting Maintenance preserves the snapshot. CPU,
RSS, USS and PSS must still be measured on real Pi Zero 2 W hardware before
claiming an absolute production memory budget. Unit tests and synthetic
benchmarks are not proof of real printing-time zero overhead.

### READY-time static capability vs test-time measurements

At Klipper READY, the compact snapshot records **structural capabilities**, not a sample of instantaneous health. A configured `bed_mesh` can be inspected after a later calibration even if no mesh was active at startup; `load_cell_probe` includes structured force telemetry by Klipper contract even if no force sample has been taken; `temperature_fan` has a temperature status field regardless of subscription at startup. An explicitly whitelisted `gcode_button` may be observed by its documented status field without subscribing during discovery. These capabilities require **fresh, validated API observations at test execution time** before a result can be marked successful. No new always-on telemetry subscription is added. Unsupported capabilities still fail closed.

Klipper's `bme280`, `htu21d`, `sht3x` and `aht10` sensor objects expose environmental status independent of the display's live subscriptions. Their **capability** is available at READY, while the display reads actual values only on demand. A `bme280` object might represent a pressure-only BMP280: pressure display remains valid, but humidity-specific logic requires separate positive evidence.

### TMC temperature monitors: one-time structured API evidence

On each Klipper READY epoch, the existing read worker makes a single read-only `GET /printer/objects/query?heaters=available_monitors` request alongside the bounded Moonraker service checks. Klipper lists driver temperature monitors even if the driver is currently disabled and its live `temperature` would be `null`. Only recognized TMC names are converted into small positive-evidence tokens (capped at 64); raw API objects and responses are discarded. No driver is enabled, no G-code is issued, and no subscription is added. Measurement availability is validated again when the actual test executes.

For recognized Klipper TMC driver objects, the documented structured `drv_status` attribute may be `null` while the motor is disabled. M07 alone is therefore recognized as a driver diagnostic **capability**, never a PASSED test at startup. M10 is reserved and is not discovered. Runtime fault checks must obtain a fresh non-null status and apply driver-specific bit interpretation. No `DUMP_TMC` is sent during discovery; driver temperature remains gated on `heaters.available_monitors`.

CI runs the full regression suite and reports synthetic 150-fan Maintenance discovery timing, Python allocations and available Linux RSS/PSS/USS. These Linux runner values are an early regression signal, **not** the Pi Zero 2 W acceptance measurement; a real before/after Petrel process test on that target remains mandatory before merge.

**Benchmark interpretation:** Run the uninstrumented process separately from the `--trace` Python-allocation process. Tracing can itself inflate RSS substantially; its RSS is *not* the production footprint. Neither runner result replaces a real Pi Zero 2 W Petrel process comparison. The approximate immutable snapshot size is printed separately.

### Bounded startup evidence handling

READY discovery requests five small documented API endpoints (`/server/info`, `/machine/proc_stats`, `/server/history/totals`, `/printer/objects/query?heaters=available_monitors`). The unnecessary potentially large `/machine/system_info` request has been removed. Each JSON response is parsed into short evidence tokens and discarded **before** the next request; no list or dictionary of full endpoint replies is retained. Disk space remains an on-demand feature, not guessed at startup.

### Dynamic menu enumeration and resonance axes

`available_features()` and the device-unspecified `method(feature)` now aggregate all per-device method masks together with global capabilities. Individual instances remain inspectable via `instances(feature)`. Resonance capabilities also expose `snapshot.axes('R02'|'R03'|'R04', device=None)` with a compact X/Y/Z bitmask (1/2/4), reflecting Klipper's shared XY or separate accel_chip_x/accel_chip_y/accel_chip_z bindings; unassigned axes must never be offered as measurable. No per-feature dictionary or persistent index is allocated.

Storage S04 is now positively discovered via the **small** `GET /server/files/roots` response if a readable `gcodes` root is registered. Moonraker documents `disk_usage` on `GET /server/files/directory?path=gcodes`; that potentially large directory listing is **never requested at READY**. A later storage screen can request the actual free/total values on demand. Roots existence indicates a supported method, not measured free space. READY discovery now has five read-only API requests. <https://moonraker.readthedocs.io/en/latest/external_api/file_manager/>

### Real Pi Zero 2 W acceptance (required before merge)

To check the actual running Petrel process rather than synthetic Python allocations, use `tools/measure_petrel_resources.py`. Install **master** on the Pi with the same printer config, let Klipper become READY, and record the service's main process in a controlled idle or equivalent print workload:

```sh
PID=$(systemctl show -p MainPID --value Petrel.service)
python3 tools/measure_petrel_resources.py capture --pid "$PID" --seconds 30 --output /tmp/petrel-master.json
```

Repeat with the feature branch **on the same device and equivalent workload**, saving `/tmp/petrel-feature.json`. Then:

```sh
python3 tools/measure_petrel_resources.py compare --baseline /tmp/petrel-master.json --candidate /tmp/petrel-feature.json --max-uss-kib 1024 --max-rss-kib 1024
```

The tool is an **external, explicitly run** standard-library-only sampler reading Linux `/proc/<pid>/smaps_rollup` and CPU ticks. It does not attach a debugger, instrument Petrel, inject G-code or create a background service. The comparison reports median RSS/PSS/USS and single-core CPU usage. A PASS requires both median RSS and USS to stay within their limits and is valid only for comparable workloads; no Pi measurements have been performed by this development branch itself. Both warm-idle and identical printing scenarios should be checked. Independently verify startup latency and memory peak during Klipper READY.

### Config-backed steppers are not necessarily printer status objects

The active `configfile.settings` is authoritative for `stepper_x/y/z` (and numbered variants), even when `printer.objects.list` lacks those section names. Maintenance discovery now includes only these recognized **effective configuration sections** in a temporary candidate set; the final snapshot retains only compact per-device results. This restores motor M04/M05/M06 and physical endstop M01 recognition without requesting additional status or issuing G-code. Numbered auxiliary Z motors expose only coarse `STEPPER_BUZZ` capability, not independent coordinated G1 travel/measurement. Z-endstop P06 requires a physical, non-virtual endstop pin.

### Effective configuration is required for accelerometers and resonance tester

Klipper `printer.objects.list` returns only objects with a `get_status()` method. Drivers such as ADXL345 and the `ResonanceTester` may not implement this method, even when correctly configured and fully supported. Maintenance now recognizes the loaded `configfile.settings` sections `adxl345`, `lis2dw` and other supported accelerometer types (with named variants), and `resonance_tester`. It validates the configured chip-to-axis bindings before offering R02/R03/R04. A pin named `adxl_power` **does not** prove a sensor is configured. Successful live data collection remains a separate test-time requirement; no sensor is energized during discovery.

### Real-process lifecycle acceptance

The Petrel service emits **three bounded INFO lifecycle events**, without configuration data or names: `Maintenance discovery: READY epoch=N devices=X features=Y` (initial structural snapshot), `Maintenance discovery: EVIDENCE epoch=N services=S devices=X features=Y` (one completion of the same READY event), and `Maintenance discovery: CLEAR epoch=N` (disconnect or shutdown). They do not fire on UI navigation, ordinary telemetry or status revisions. They add no subscriptions, commands or background work. On an idle printer, follow the journal with `sudo journalctl -u Petrel.service -f -o cat | grep --line-buffered 'Maintenance discovery:'`; restart **Petrel alone** to see READY/EVIDENCE, open/leave Maintenance three times (no additional events expected), then restart **Moonraker alone** to verify CLEAR followed by READY/EVIDENCE in a new epoch. Do not restart services during a print. This is observational logging; it does not prove the physical state of a sensor or an individual test outcome.
