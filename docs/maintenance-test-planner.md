# Maintenance test planner (development)

[Türkçe](maintenance-test-planner_TR.md) · [Catalog](maintenance-test-catalog.md)

**Status:** Pure planning only. The printer and LCD are not controlled, and the menu is still a placeholder.

`maintenance_planner.build_plan(snapshot, adapters=())` intersects the immutable discovery snapshot with the 121-ID catalog and **explicitly registered** adapters. The default adapter registry is empty, so all discovered candidates remain `blocked` and `visible_plan` is empty. A discovery method never implicitly installs a test.

Each immutable row captures the feature ID, exact device or global scope, available method mask, selected single method, adapter name (if installed), required evidence, safety-profile key, Klipper epoch/config marker, and any assigned resonance axes. Multiple heaters, fans, and TMCs remain distinct. R02/R03/R04 are scoped to actual accelerometer instances and assigned axes without a duplicate global row.

Registered methods are matched exactly and validated against the catalog, declared evidence and safety profile; fake registrations, duplicates, unsupported IDs and invalid masks are rejected. A registered `INFORMATION` method creates an informational item, **not a PASS**. A guided item requires user/instrument/calibration interaction. Even a `runnable` candidate is **not dispatch permission**: the future Safety Coordinator must perform positive, current printer-state and per-command checks, and the future Executor must validate actual measurements.

No I/O, G-code, polling, workers, subscriptions, renderer changes or change to existing `PrinterCapabilities` is introduced. GitHub Actions runs `tests/test_maintenance_planner.py` with the full suite on branch push; verify signed HEAD and CI PASS before further changes.
