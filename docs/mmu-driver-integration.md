# MMU / master LCD driver integration

Date: 2026-10-08. Branch: `feature/mmu-menu`.

## Compared revisions

- Common ancestor: `779b25fc3e25c9f24d823e617953bd739d29c58d`.
- MMU before integration: `15964f0436244e769a9cd6aeae67b1e1899ec7e0`.
- Integrated master: `231c9b9583838d33935c8035f4b21db1d3920b0e`.

Master is a real second parent of the integration commit. Its history is
preserved, so a later MMU merge does not need to reconcile the removed driver
against an unrelated copied implementation. Master itself was not changed.

## Master changes and MMU adaptation

| Master change since the common ancestor | Integrated MMU behavior |
|---|---|
| Removed `DWIN_Screen.py`; complete `T5UIC1Display` API | All MMU and branch-only LCD calls/tests use the new API; every MMU page is exercised through the real driver |
| Managed JPEG atlases, symbolic IDs, Picture Flash persistence | Home normal/selected MMU icons use atlas copies; folder, Info and power icons follow the master manifest |
| Exclusive ownership of virtual areas 0/1 | UI code does not load legacy language caches; the master driver, JPEGs and atlas manifest are retained unchanged |
| Atlas metadata readback and Flash wear guards | Restored by the existing driver; rendering/reconnect tests prohibit unnecessary memory/picture programming |
| Response-based panel heartbeat and reconnect | MMU canvas is invalidated and fully rebuilt; pending printer commands are not resubmitted |
| Global encoder power button | Present on every MMU page; Back → CCW focuses power; numeric edits retain encoder ownership |
| Shutdown popup | No restores the complete MMU canvas, draft, selection and confirmation target; connection/panel changes cancel stale popup state |
| Driver regression workflow | Existing workflow also runs on `feature/mmu-menu`, for both the initial and bot-signed commits |

MMU gate reels, filament path, sensor state and other live graphics remain
state-dependent drawing. Static custom icons come from the managed atlas. No
atlas coordinates, JPEG assets, Flash ownership policy or MMU command semantics
were redesigned by this integration. The earlier A01–A06/A08 audit fixes remain.

## Verification

- Separate baseline suites: MMU 518 tests; master 408 tests, both passed.
- Infrastructure/API integration: 561 tests passed.
- Header/power/canvas integration: 566 tests passed.
- Lifecycle and stale-popup integration: 573 tests passed.
- Final asset-documentation consistency pass: 573 tests passed.
- Python compile and shell syntax checks passed.
- GitHub regression runs and bot signatures are verified before the next commit.
- The exact master driver, atlas manifest and atlas JPEGs are preserved.

The tests cover actual driver packet generation with fake UART/network/GPIO;
they do not run on a physical LCD/Pi or execute printer movement. Follow the
[physical test checklist](../tests/README.md#mmu-with-the-complete-t5uic1-driver)
on the integrated branch before merging the MMU feature into master.
