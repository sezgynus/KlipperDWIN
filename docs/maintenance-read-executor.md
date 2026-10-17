# Bounded read-only Maintenance executor (development)

[Türkçe](maintenance-read-executor_TR.md) · [Safety](maintenance-safety.md)

**Status:** Six information-only adapters exist as a standalone backend facility. They do not control motors/heaters/fans, run G-code, display a Maintenance menu, or report a physical PASSED result.

`maintenance_executor.py` registers only S01, S02, S03, S05, S08 and S10, with fixed bounded GET endpoints and schema-specific scalar extraction. Requests use Petrel's **existing** Moonraker client and bounded read worker, injected on demand. There is no new thread, polling loop, websocket subscriber or network client. Every read starts with the Safety Coordinator's positively verified idle/session check. State is rechecked immediately before the worker's GET and when the Future is collected, so a stale result cannot be published across a print start, disconnect or epoch/config change.

`start(row)` validates an explicit INFORMATION plan, a trusted fixed adapter, a bound timeout and a fresh positive safety context, returning admission status. `poll()` is nonblocking and returns `None` until a result is available. `cancel()` invalidates the session and suppresses late responses; `close()` does not close Petrel-owned client/worker. Only selected numeric/status fields from a response become a small evidence tuple; raw API mappings and secrets are not retained.

A successful information read has `ReadResult.status=None`, meaning **observed telemetry, not a hardware PASS**. Missing measurements produce `INCONCLUSIVE`, cancellation/unsafe state `ABORTED`, and read errors/timeouts `ERROR`. These are intentionally not persisted as completed physical tests.

**Integration still pending:** An owner must instantiate this facility with an existing worker/client, provide *genuine* current queue/operation checks, and use the plan/view model in the DWIN UI. A caller must not set the positive SafetyContext flags without checking real state. This stage adds no automatic startup work or changed UI hot path. More advanced TMC fault and active hardware tests need driver-specific evidence and separate approval.

`tests/test_maintenance_executor.py` covers valid/missing/invalid payloads, method selection, cancellation, queued reads, external printing, epoch drift and shared worker ownership in GitHub Actions CI.

## Current M07 implementation: homing-independent direct register diagnostics

The paragraphs above describe the original GET-only stage. Current M07
Diagnostics issues `DUMP_TMC STEPPER=<verified name> REGISTER=DRV_STATUS` on
explicit request for supported TMC chips. Klipper's `notify_gcode_response`
is correlated using the existing Moonraker connection, a fresh response
cursor and RPC completion. Historical lines, ambiguous/double replies,
missing data and communication errors never become a fault-free result.
No motor enable/homing/movement or register writing occurs. Exact TMC2208
bit masks yield a bounded fault summary; other supported chips show only
the raw register. TMC2660 keeps its passive fallback because selecting its
read register writes RDSEL. M07 remains informational; M10 stays reserved.
GitHub CI covers normal GET and direct register/failure paths; no local tests.
