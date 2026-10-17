# 17 October 2026 physical trace review

Session: `dec3042495ca4ab78b58b947e2b3c73a`; running HEAD: `32a8e14991e6d1d308909602084ab2e1f7b7d815`.
Local time: 13:47:51–13:56:35. 2,844 consecutive events; no drops, write errors or rotations.

53 start attempts: 15 rejected at admission and 38 terminal results.
Results: 7 INCONCLUSIVE, 20 BLOCKED, 5 operator ABORTED, 2 automatic PASSED, 4 PASSED_USER (3 distinct targets).

| Scope | Evidence / result |
|---|---|
| H01 extruder, run 1 | Target 60°C, test ceiling 70°C, measurement 70.37°C, power 0. Safety shutdown; restore unverified. Keep the ceiling. |
| Following 15 H attempts | `thermal_busy_or_locked`; no heating command. These are not 15 independent thermal faults. |
| M03/M04/M05/M06/M12, runs 17–27 | `motion_requires_cold_idle_heaters`; hot extruder blocked dispatch. |
| M01 X/Y, runs 28/29 | Reply contained `stepper_x=open`, `stepper_y=open`; code looked only for x/y. Confirmed parser defect fixed; physical acceptance remains pending. |
| M10, runs 30–33 | `driver_monitor_disabled_or_unknown`. Neither motor health nor a definite driver fault is established. Future traces include drv_status. |
| P01, runs 34/37 | Operator cancel. Run 34 stayed on “Release probe”; a correct physical released/triggered/released sequence is needed. |
| P03, run 36 | Automatic PASSED: range 0.0175 mm, stddev 0.005362 mm, 10 samples. This is not absolute accuracy or operator physical acceptance. |
| P04, run 40 | Automatic PASSED: X/Y=117.5 mm, Z=-0.021667 mm. The prior two attempts required raising Z. |
| E03, run 41 | Absent→present observed; operator cancelled before confirming the final absent stage. Sensor enabled=true restore verified. |
| E01/E02/E07 | Active extruder preheat missing; BLOCKED before dispatch. |
| E11 | MMU enabled; prerequisite rejected. Disable through the normal MMU menu first. |
| E12, run 47 | ValueError preparing grip; no mechanical command sent. Old trace omitted the message, so the precise MMU blocker cannot be established. Known MMU messages are mapped to fixed safe codes in future traces. |
| S15, run 48 | GPIO +2/-3/click 1; explicit observe(true); PASSED_USER, restore=true. Accepted. |
| S16, run 50 | Five color stages and explicit observe(true); PASSED_USER, restore=true. Accepted. Later cancelled reopens do not revoke completed acceptance. |
| S17, runs 51/53 | 10/50/100%, restore and explicit observe(true); two PASSED_USER results. Accepted once for this target. |

## UI findings

1,976 UI events; no captured `ui_handler_error`.
No direct `pulse → tests` transition occurred; a result screen and operator Back action intervene.
The initial H shutdown is followed by result → recovery → home.
This trace does not prove the absence of every UI bug; it did not reproduce the earlier unexplained list return.
The filter unnecessarily omitted labels containing “ / ”. Spaced UI separators will survive while file paths/URLs remain omitted.

## Retest

- Do not bypass the H safety lock. Verify safe hardware/OFF before a new Petrel session; address the H01 overshoot without weakening its ceiling.
- Cold tests first: M motion while the hotend is cold, P workflows with homing/Z prerequisites satisfied.
- After the M01 fix, physically exercise X/Y released→pressed→released.
- For E03, choose “read” at the final Remove filament stage; Cancel aborts.
- Disable MMU for E11; separately stabilize preheat for E01/E02/E07.
- Record E12 again with the new detailed safe code.
- S15/S16/S17 acceptance is complete; retest only for a new regression.

[Acceptance ledger](maintenance-reference-printer-acceptance.md) · [Türkçe](maintenance-acceptance-2026-10-17_TR.md)
