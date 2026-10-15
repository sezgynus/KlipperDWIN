# Maintenance Stage 8C — guarded physical pulse runner

[Türkçe](maintenance-physical_TR.md)

`MaintenancePulseController` is an on-demand backend state machine. The only supported physical actions are compiled `PulseProgram` scripts from Stage 8B, with a self-contained restore after a maximum 950-ms stimulus. It reuses the existing Petrel read worker, Moonraker HTTP client, `postREST` command queue, immutable discovery, fail-closed job queue/operation evidence and explicit `GuidedConsentGate`.

Two distinct UI actions are mandatory: first, select a discovered test (queues a read-only job-queue + target baseline GET); second, explicitly confirm **within three seconds** after the preflight. Nothing is sent on menu entry or discovery. A dispatch-time guard rejects changed Klipper epoch/config, print/paused/manual-probe/MMU operations, stale queue evidence and unknown status. `postREST` queues the short G-code script; after the command completes, a new bounded GET must confirm the original value was restored. Only then does the runner ask for the user's observation, and **only an explicit YES** returns `PASSED_USER`, never automatic PASS or RPM data.

IMPORTANT: a Moonraker timeout/connection interruption can leave a command's execution ambiguous even if the script includes a restore. The controller marks this `INCONCLUSIVE`; it never replays a timed-out command. An ambiguous command may continue executing after a cancel/timeout. The user must inspect the hardware; the local reservation is not a global lock against other Moonraker clients. This implementation cannot establish hard real-time fail-safe guarantees. In particular, an unverified original output, unknown queue, active template, or mismatching post-command readback **blocks** success.

The LCD interface and accepted real-Pi hardware stimuli require separate validation; CI fakes cannot prove any physical actuator works.
