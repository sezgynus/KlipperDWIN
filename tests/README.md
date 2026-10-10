# Regression tests

Run the complete isolated suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

On an installed Pi, use `~/klipperdwin-env/bin/python` instead of `python3` to
run with the application's dependencies.

The suite uses `unittest`, isolated printer state and mocked serial, GPIO,
HTTP and WebSocket I/O. Tests execute real UI/backend methods without opening a
printer connection or moving hardware. Preset writes use temporary directories.

## Coverage

| Area | Regression contracts |
|---|---|
| HTTP transport | Authentication, bounded requests/downloads, malformed responses, observable command results, closed clients and cancelled queues |
| WebSocket state | Bootstrap/discovery, partial and out-of-order updates, early notifications, lifecycle changes, reconnect, ping checks and RPC completion |
| State and capabilities | Immutable snapshots, effective configuration/limits, heater/fan combinations, active extruder, optional controls and epoch replacement |
| Input and ownership | Concurrent producers, FIFO input, bounded overload, debounce, stale-event rejection, one UI owner for initialization/rendering/cleanup and UART writes |
| Home menus | Forward/reverse four-icon paging, empty slots, Leveling/MMU/Info routes, return selection, capability removal and persistent dashboard/MMU areas |
| MMU controls | Full-screen ownership, read-only browsing, gate scrolling, draft manual/map/EndlessSpool/spool-ID edits, target-specific Cancel-first confirmations, stale-menu/target rejection, print/busy/unknown guards, completion plus state queries, distinct sensors, bypass/recovery, calibration exclusion, active-unit LED controls, read-only unit browsing, confirmed unit selection and UART/offline recovery |
| Files and folders | Cached lists, nested/empty folders, folder-first sorting, basename labels, full-path print starts, deletion/replacement and selection preservation |
| Mainsail sorting | Name/date/size in both directions, newest-first fallback, invalid preferences/timestamps, bounded polling and stale Enter rejection |
| Print workflow | Duplicate suppression, command/status confirmation, failed starts, timeout without replay, paused/resumed/completed/cancelled states and retained errors |
| Preview images | Baseline 128×128 JPEG, letterboxing/transparency, decode/download limits, relative paths, Cancel/late results and revalidation before Print |
| SRAM cache | First-five priorities, incremental uploads, nonoverlapping addresses, complete-entry publication, folder/sort reuse, LRU eviction, retry and stale-worker rejection |
| Preview metadata | Shared metadata request, JSON-encoded materials, referenced T1/T2 versus all tools, positive-weight fallback, unknown values, image-free details and bounded rows |
| Movement | Command-space targets, homing/bounds, cold/excessive extrusion, paused/printing rejection, relative modal-state preservation and restore failure guards |
| Thermal/presets | Optional heaters/fan, atomic target validation, percentage conversion, local editor isolation, Mainsail sync and atomic local JSON persistence |
| Motion | All four runtime parameters, supported-field omission, numeric domains, cruise-ratio boundaries and external updates |
| Probe calibration | Session ownership, start/manual-state confirmation, serialized TESTZ, accept/abort, exact pending-offset save guards and reconnect without replay |
| Screws Tilt | Four-corner geometry, homing/print guards, fresh and identical repeated results, largest-turn instruction, tolerance/colors, rollover, failures and label bounds |
| Bed Mesh | Completion and fresh query, probe sample deduplication, profile viewing without LOAD, exact pending-profile save guards, explicit stop/restart confirmation and map bounds |
| System/integrations | Host/software/MCU information, Happy Hare/Spoolman data, light state, configured encoder power-on, guarded power-off and global confirmation navigation |
| UART/display | Full T5UIC1 opcode framing, handshake/ACK fragmentation, RX parsing, SRAM/Data Flash read-write, Picture Flash, managed atlas ownership, panel-reset heartbeat/reconnect recovery, numeric/text bounds, RGB565, asset coordinates and compatibility rendering |

Failure/epoch tests verify that uncertain actions are not replayed. Acceptance of
a transport request is tested separately from the expected printer-state change.
Rendering fixtures validate generated packets and coordinates; they cannot prove
that an arbitrary physical panel will render those packets correctly.

## Physical validation

User panel tests have exercised direct JPEG display, SRAM cache hits and metadata
layout. Compatibility with other panel kernels/assets and printer configurations
remains a separate check. Automated tests do not validate Pi service lifecycle,
real motion, probing accuracy or live-server persistence.

When checking a release on hardware:

- Browse nested folders, change Mainsail sorting and verify the selected file/path.
  Hidden thumbnail folders and non-G-code files should remain absent.
- Compare preview time, tool changes, totals and used-tool colors/weights with
  Moonraker metadata. Check Print/Cancel, missing images and the four-row layout.
- Compare cold and cached previews using `Thumbnail` logs. Replace/delete a file,
  reconnect and ensure stale SRAM entries are not reused.
- Open Prepare → Screws Tilt Adjust → Calculate. Compare Base and each direction/
  amount with Klipper, adjust the indicated screw and repeat. Confirm input is
  locked during measurement and success instructions turn green within tolerance.
- Open Home → Leveling → Bed Mesh Calibrate. Compare final points/min/max with
  `bed_mesh.probed_matrix`, inspect grid orientation and repeat after Continue.
- In Mesh Viewer, compare saved profiles and Current Mesh; verify viewing does not
  change `bed_mesh.profile_name` or move the printer.
- Confirm Save only when the displayed profile/restart is intended; after restart,
  verify the generated `lcd_mesh_N` profile persists with the measured matrix.
- Test Cancel → Stop only when shutdown is intended; restore Klipper with
  `FIRMWARE_RESTART` afterward.

Record the software revision, hardware configuration, logs and screen photos for
failures. The [historical audit](../docs/source-audit.md) and
[LCD compatibility notes](../docs/lcd-assets.md) provide additional context.


## MMU physical verification

The isolated suite checks behavior with mocked I/O. Validate the following on the
actual LCD and installed Happy Hare configuration before merging the control UI:

1. Enter/exit MMU and its subpages. Check the full-screen layout, encoder focus,
   restored Home selection/dashboard and readable colors/fonts.
2. Browse every gate without movement; check lists with more than four gates and
   Spoolman missing/available. Confirm G1 corresponds to API gate 0.
3. With unloaded filament, test Select only, Preload, Check, Load selected and
   mapped Load/change. Verify the confirmation target and actual final state.
4. Test Unload versus Eject spool, including an initially loaded active gate.
   Confirm Eject removes filament from the MMU, rather than merely parking it.
5. Unload before selecting bypass; verify extruder-only load/unload and locks.
6. Exercise an MMU error pause. Confirm automatic Recover entry, draft/manual
   Cancel, actual-state Apply, separate unlock/reheat and explicit Resume.
7. Change MMU selection/state from the web UI while an LCD confirmation/editor is
   open. The old action must not be submitted. Verify printing/busy controls lock.
8. Disconnect/reconnect Moonraker and UART. Check retained operation errors,
   rebuilt current page, read-only offline navigation and no command replay.

Options → LEDs and Options → Units are implemented when their validated
capabilities are available. Follow the checks below on hardware; configuration
confirmation alone does not prove LED output or selector movement. Calibration,
custom LED effects and entry/status/logo editing remain in the web UI.

LED checks:

1. Open Options → LEDs with valid active-unit `mmu_leds <name>` telemetry. Verify
   missing/unknown LED telemetry hides or locks the corresponding controls.
2. Change Enable, Animation and supported exit modes (`off`, `gate_status`,
   `filament_color`, `slicer_color`). Check Cancel-first confirmation, Cancel
   without dispatch, and one `MMU_LED UNIT=...` command per confirmed action.
3. On a multi-unit setup, verify only the active unit changes. Confirm the result
   is queried from that unit's actual LED object; check the physical enabled,
   animation and exit output separately from the reported configuration.
4. Change unit or LED configuration from the web UI during confirmation, and test
   busy/printing/paused locks and disconnect/reconnect. Stale confirmation must
   not dispatch; uncertain commands must not replay.
5. Check Home exit-LED colors, off/black lanes and contrasting gate labels. LCD
   hue normalization does not reproduce physical brightness.

Unit checks (requires a validated multi-unit gate partition):

1. Open Options → Units, browse each unit and its gates, and return. Browsing must
   send no command; gate labels must preserve global gate indices. A single-unit
   installation omits this browser; invalid partitions must not enable selection.
2. Choose Select this unit. Verify the confirmation names its first global gate,
   starts on Cancel, and Cancel causes no movement. Confirm once with unloaded
   filament outside printing/pauses; expect `MMU_SELECT GATE=...` exactly once.
3. Verify the queried active unit and gate both match the confirmed target. Check
   actual selector travel/homing on the printer; selection can cause movement.
4. Change the partition, active unit or physical state from the web UI while
   confirmation is open. Test loaded/busy/printing/paused locks and reconnect;
   stale or uncertain operations must not be submitted again.

Tool map: edit several tools to one gate, cancel the draft, cancel confirmation,
then Save and verify the actual Happy Hare mapping. Check long lists, gate bounds,
printing/pause locks and web UI mapping changes while the editor is open.

EndlessSpool: toggle enable, join/split gates (including the final member),
check material/color metadata, Cancel and Save. Verify whole enable/group state,
arbitrary existing group IDs, missing metadata, external changes, off-print locks,
long lists and reconnect behavior. Physical compatibility still needs hardware QA.

Spool assignment: edit/accept/Save/Cancel, first assignment, explicit clear,
mode/temperature/print locks, duplicate-spool warning and whole-map verification.
On hardware check that TEMP is preserved, the previous gate becomes unassigned,
and any Spoolman synchronization completes. Local assignment confirmation does
not establish spool-record existence or completion of external synchronization.

Maintenance/options: validate unit partitions and selector types, hide unsupported
controls, check unloaded grip/release and loaded sync guards, home then select the
confirmed tool, check all gates, and verify actual homing/grip/sync/availability.
Hardware QA must establish calibration, selector travel, servo positions, command
compatibility and safe behavior before merging. Never treat static homing data
from mmu_machine as a live homing result.

MMU enable/disable: unloaded-only off-print guards, re-enable from disabled,
Cancel-first confirmation and actual enabled flag. Motor release: discover
stepper_enable, resolve configured MMU drivers only, reject missing telemetry,
query every driver plus sync state, and verify printer XYZ drivers stay untouched.
On hardware verify servo behavior and re-home a linear selector if necessary.


## MMU with the complete T5UIC1 driver

`test_mmu_driver.py` renders every MMU page through the actual driver, checks
all production LCD call names and verifies normal/selected Home atlas packets.
`test_mmu_power_integration.py` covers header space, idle-page reuse, encoder
focus, numeric editing and complete popup restoration without discarding drafts.
`test_mmu_driver_lifecycle.py` verifies a single refresh per encoder event,
heartbeat recovery, atlas restoration without Flash programming, no MMU command
replay and cancellation of stale power confirmations.

Physical follow-up on the integrated branch:

1. Check Home MMU icons, folder icons and Info headings against master.
2. Browse all MMU pages. From Back, rotate CCW to power; CW returns to Back.
   Open power and choose No; verify the complete page and any unsaved draft.
3. With no active movement, power-cycle only the LCD. Verify the current MMU
   screen and icons return without restarting a filament operation.
4. Change or restart the Moonraker/Klipper connection while an MMU power popup
   is open. Verify cancellation and read-only offline navigation.
5. Run the MMU operation checks above, including real Load/Unload and LED output.

These are physical acceptance checks; mocked UART packets do not establish
panel rendering or real printer motion. Integration details and the master
comparison are recorded in [the driver integration record](../docs/mmu-driver-integration.md).
