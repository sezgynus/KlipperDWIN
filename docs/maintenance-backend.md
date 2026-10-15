# Maintenance read-only backend integration

[Türkçe](maintenance-backend_TR.md) · [Safety](maintenance-runtime.md)

**Stage 6:** The existing Petrel backend now owns a lazily used `MaintenanceReadController`. No Maintenance requests are made at startup, during normal print telemetry processing or when merely displaying another menu. No additional background thread, Moonraker client, websocket or DWIN drawing loop is introduced.

`PrinterData.maintenance_read_plan()` joins discovery, catalog and a fixed set of six information adapters (S01/S02/S03/S05/S08/S10). `start_maintenance_read(feature_id)` queues a bounded read-only job queue preflight on Petrel's existing Maintenance worker; it never performs network I/O on the UI thread. `poll_maintenance_read()` advances the nonblocking Future once queue evidence is available and returns either no result (pending) or a final `ReadResult`. `cancel_maintenance_read()` drops stale results. The controller is cancelled on connection/epoch transition and closed before the shared worker/client are stopped.

The preflight explicitly checks `/server/info` for job_queue existence and, if present, `/server/job_queue/status`; it does not assume a failed endpoint means a disabled queue. Live printer-state, print/pause/manual-probe/MMU and operation-owner checks are repeated before GET and on result collection. READ ONLY results never report a hardware PASSED. No physical actuator test is included.

**Not yet a UI feature:** Existing Maintenance LCD screen remains unchanged. This backend API is opt-in for later Diagnostics/Information screens. External Mainsail/Fluidd can race state checks; this must be addressed with stronger dispatch-time synchronization before physical tests.

`tests/test_maintenance_controller.py` covers real backend construction, queue present/absent, print start, stale epoch, cancel, opt-in behavior and nonblocking workflow, as part of the full GitHub CI gate.
