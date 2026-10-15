# Maintenance test catalog (development)

[Türkçe](maintenance-test-catalog_TR.md) · [Discovery](maintenance-discovery.md)

**Status:** Definitions only. No tests are runnable, no physical actuation is implemented, and the Maintenance LCD menu remains the existing Back-only placeholder.

`maintenance_catalog.py` is a small immutable table of all 121 established feature IDs, with a description, global/device/mixed scope, potential discovery methods, evidence requirement identifier and safety-profile category. Every `adapter_id` is `None` until a verified adapter is implemented and registered in a later stage. The seven deliberately hidden feature IDs remain hidden. Unknown and noncanonical IDs fail closed.

The catalog's method bit mask is an upper bound: `candidate_methods(id, discovery_mask)` merely intersects potential methods. It is **not** a safety authorization, a successful measurement or evidence that an executor exists. `INFORMATION` describes monitoring, not a functional PASS. Evidence identifiers document required future proof; they do not themselves implement sampling or verification.

The next Planner stage must join device-specific and global discovery correctly, require an explicit adapter and evidence verifier, and keep unavailable/blocked tests out of the active menu. A separate Safety Coordinator must positively revalidate printer state at every side-effecting dispatch. No discovery module, printer telemetry hot path, normal UI, or `PrinterCapabilities` is modified by this catalog.

The `Driver Branch Regression` GitHub Actions workflow runs `tests/test_maintenance_catalog.py` with the existing full suite on every branch push. Local test execution is not required in the development workflow. Work proceeds only after the signed final branch HEAD and its CI result are verified.
