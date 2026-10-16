# Maintenance Stage 8B — bounded actuator program compilation

[Türkçe](maintenance-pulse_TR.md)

This is a **pure compiler**: no method here sends commands, starts tests, claims hardware PASS, or bypasses safety. Only exact USER-guided discovery rows can produce an immutable `PulseProgram`. The generated G-code has one allowlisted stimulus, a 150–950 ms `G4` delay and an explicit original-state restoration in **one bounded script**. Start is forbidden if original firmware status is missing or untrusted. External clients and Klipper restarts can still interrupt scripts: a subsequent executor MUST independently verify the restored output before reporting that restoration was observed.

Hardware profiles: F01 part fan uses M106 and restores prior commanded PWM, not RPM; F04 fan_generic uses exact SET_FAN_SPEED and refuses templates or unsafe names; O03 is any explicitly registered visual output_pin PWM with scale 1, a live baseline and raw config pin identity; O04 is a single LED element with fully known color_data and exact SET_LED restore, not multi-pixel strips; S18 is a per-device, explicitly registered audible pwm_cycle_time output with configured default and shutdown value 0 (not live OFF telemetry). Unsupported hardware remains blocked. Klipper's G-code command grammar is documented in its official [G-Codes reference](https://www.klipper3d.org/G-Codes.html).

The future executor must keep the printer idle, verify Moonraker job queue and other Petrel operations, guard the dispatch, avoid automatic execution on UI/menu entry, read the target again after completion, distinguish physical user-observed YES/NO from status values, and preserve INCONCLUSIVE if verification fails. All tests are run only in GitHub CI.

## S18 readback limitation

The opt-in `pwm_cycle_time` buzzer has no Klipper status readback. Its bounded script first commands OFF, waits 50 ms, sends a 150-ms tone, and commands OFF again. The 200-ms program **attempts** restoration but does not establish that it physically occurred; `restored()` deliberately never accepts S18 as telemetry-verified, even when handed a fabricated status value. Only the exact explicitly permitted, default-OFF effective configuration is admitted.

The S18/O03 SET_PIN compilers require a separately verified case-preserved `pin_command_name` from Klipper's raw configuration. It rejects missing or case-insensitively different identifiers, and uses only this validated spelling for every `SET_PIN PIN=` command.

## O04 LED chains: automatic capability recognition, guarded execution

O04 is device-neutral. Unmanaged Klipper \`led\`, \`neopixel\`, \`dotstar\` and \`pca9632\` chains remain opt-in via the normal \`led\` role, with 1–32 uniform RGB/RGBW pixels, explicit user confirmation, an indexed stimulus and complete per-pixel restoration (twice confirmed by Klipper readback). No software state can prove physical light emission: affirmative operator observation is always required for \`PASSED_USER\`.

For Happy Hare, Petrel reads effective \`[mmu_leds <unit>]\` configuration and actual Klipper objects **without fixed MMU names, pins or gate counts**. A physical chain may be divided across the \`exit_leds\`, \`entry_leds\`, \`status_leds\` and \`logo_leds\` segments, including independently mapped 1-based ranges and multiple MMU units. A bounded, disjoint, exact segment-to-physical-index mapping is required. Confirmed Happy Hare-owned chains automatically become **guided candidates**; users need no printer-specific LED profile for these known MMU integrations. Discovery NEVER sends a command or grants automatic test PASS.

Each affected unit receives one \`MMU_SET_LED UNIT=<discovered-unit> [SEGMENT_EFFECT=(r,g,b)...] DURATION=0.40 FADETIME=0\` through **Happy Hare's own LED controller**, with a dim stimulus deliberately chosen to differ from the target LEDs' captured colors. One unit may receive multiple segment effects in one command; independent units are addressed individually. The adapter never writes raw \`SET_LED\` to a Happy Hare-owned chain and never disables the MMU LED manager. After the one-second Happy Hare timer, Petrel waits and checks each participating \`mmu_leds\` object's original \`enabled\` and \`animation\` flags with two readbacks. That checks *controller policy only*, not physical output or an animated color restoration; after the user's visual confirmation the outcome is \`OBSERVED_USER\`, **\`restore_verified=False\`**.

All physical tests keep double explicit user consent, fresh printer/queue/operation safety checks and bounded scripts. The managed path refuses disabled LED management, busy MMU actions, missing or conflicting section/status data, duplicate or out-of-range physical indexes, ambiguous multi-chain segments, unsupported names and independently configured effects targeting the physical chain. A partial subset of a physical chain is acceptable only when each modified pixel is positively mapped to its Happy Hare segment; unrelated pixels are never deliberately pulsed. Unknown third-party LED ownership remains blocked, not guessed. Mock CI is not hardware acceptance.

### Happy Hare numeric UNIT compatibility

The suffix of [mmu_leds NAME] is a unit NAME, not necessarily its G-code UNIT index. Some Happy Hare releases accept only numeric UNIT arguments. Petrel resolves the numeric index from the authoritative ordered [mmu_machine] units configuration (the same list used by Happy Hare to construct its units). It never parses digits out of unit names or assumes the first unit is always named unit0. An absent, duplicate or inconsistent mapping blocks the test before G-code dispatch. This fixes real installations reporting "unable to parse unit0".

### Happy Hare unit identity versus display name

A loaded Happy Hare `mmu_machine` may expose `num_units` and consecutive `unit_N` records while `configfile.settings.mmu_machine.units` is absent. In some Happy Hare versions the live `unit_N.name` is **a readable label**, not the canonical name used by `[mmu_leds NAME]`. The two names need not match (for example, a display label with spaces). Petrel never inserts display names into G-code and never infers an index from digits in a section name.

The native numeric `UNIT` index is established by one of two bounded, read-only proofs: (a) a validated, ordered `[mmu_machine] units` configuration list, with consistent live unit count and canonical IDs where comparable; or (b) **exactly one** live MMU unit, **exactly one** configured MMU LED controller owning the selected chain, and a valid `unit_0` record. Case (b) uniquely establishes `UNIT=0` irrespective of the user's display label, with no printer-specific exception. For multiple MMU units without verifiable canonical ordering, display names are not sufficient: O04 is withheld rather than guessing.

Discovery uses subscribed live status and fresh preflight queries repeat the proof; active printer/queue guards, temporary Happy Hare effects and mandatory operator observation remain unchanged. An ambiguous or inconsistent unit/controller count never dispatches G-code.

### O04 four-color full-scale visual test

RGB-capable LED chains run **red → blue → green → white**, in that order, with **all mapped LEDs changing together** at full per-channel scale (1.0). Each stage lasts 650 ms. RGB white is `R=G=B=1`; RGBW standalone white uses `W=1, R=G=B=0` to exercise the dedicated white channel. Standalone indexed chains transmit one complete frame at a time, then restore the **captured per-pixel original colors**; two stable Klipper status readbacks plus an explicit operator observation are needed before `PASSED_USER`.

Happy Hare-owned segments use four `MMU_SET_LED ... (R,G,B) DURATION=0.40 FADETIME=0` stages, each followed by **`G4 P650` and `M400`**. In Klipper, `G4` advances the toolhead's scheduled time, but can return before a real 650 ms has elapsed; `M400` drains the dwell and allows the Happy Hare reactor timer to expire before the next frame. Without this real-time barrier, Happy Hare's deferred timed updates can replace intermediate colors (e.g. blue). The original 400 ms effect thus expires before the next frame; no arbitrary sleeping thread or second physical dispatch is introduced. The 250 ms gap may briefly reveal normal HH colors between frames. Happy Hare restores its **policy** on its own timer; exact RGB restoration cannot be read back, so success is `OBSERVED_USER`, `restore_verified=False`. The user must observe all four colors, not merely any change.

Monochrome `[led]` outputs with no R/G/B channel set cannot run this O04 RGB cycle; they are rejected before dispatch. The bounded full-scale procedure is intended only for properly powered RGB/RGBW chains; even short full-white peaks draw substantially more current than dim pulses. No guessed power allowance or automatic brightness downgrade is applied. CI verifies commands only, never real color or electrical performance.

### Effective Klipper color_order compatibility

Klipper neopixel's config.getlist('color_order') can expose a tuple that Moonraker serializes as a JSON list in configfile.settings. O04 validates both the ordered list form (one shared RGB/RGBW order or exactly one order per pixel) and the comma-separated string form; it rejects malformed values, mixed RGB/RGBW pixels, missing RGB channels and out-of-range counts before issuing G-code. The standalone and Happy Hare-controlled compilers share this validation. A rejected physical preflight retains BLOCKED, and the exact safe compiler error code is written to the Petrel journal as "Maintenance physical preflight blocked" without revealing arbitrary Moonraker responses.

### F02 part fan speed-step test

When the READY snapshot confirms F02 and the effective fan configuration has a finite, usable PWM range, Petrel offers an explicit **USER**-observed three-step fan exercise. It derives three distinct duty commands from the configured `off_below`/`max_power` range (40%, 70%, and 100% of that available band), dwells 2,000 ms at each (6,000 ms total), and appends a restore to the fresh original `fan.speed` in the **same bounded script**. The existing physical runner requires queue/idle safety checks, positive consent, fresh post-script restored-state readback, and explicit human observation; merely acknowledging the commands or seeing the requested duty is not evidence of measured RPM. Unsupported limits, unknown baseline or stale printer state fail closed. The reference-printer acceptance ledger preserves the accepted *old* 800-ms/stage version; the extended 2,000-ms/stage version remains **retest_required** until a new real-operator acceptance.


The LCD confirmation uses `Run speed steps` for F02 and `Run color sequence` for O04; actual short-pulse tests retain `Run short pulse`. The revised longer F02 procedure requires a separate real-printer retest after CI.


**Long F02 HTTP timing:** The 6-second `G4` program can outlast MoonrakerClient's normal 5-second HTTP deadline, yielding `INCONCLUSIVE` even when the fan executed the steps. Only F02 supplies a bounded 10-second POST timeout (the transport rejects overrides above 15 seconds), allowing its script acknowledgement and subsequent **two** restored-fan status samples. All other transport requests retain their original timeout; an ambiguous failure still blocks, without replay or automatic PASS. The first 2-second/stage Pi attempt was inconclusive before operator confirmation; it is not an acceptance of the revised program.

### Happy Hare O04 live flag compatibility

The `[mmu_leds <unit>]` Klipper status can expose `enabled` and `animation` as the **exact strings** `'True'` / `'False'`, not JSON booleans. Petrel strictly normalizes either these exact strings or native boolean values at O04 preflight **and** during the two post-script readbacks. It still requires `enabled=True`; `animation` may be valid `True` or `False` but must match the captured original on readback. Numbers, missing values, malformed strings, or a disabled controller fail closed. This change does not authorize raw LED commands, guess unit indexes, bypass Happy Hare or claim physical color restoration. The prior physical PASS remains historical; this new compatibility fix requires a fresh operator-led O04 test.


**O04 blue-stage acceptance:** After the Happy Hare flag compatibility fix, the 16 Oct 2026 operator observed red → green → white but not blue. This is not a four-color physical PASS. The synchronized `G4` / `M400` revision requires renewed real-printer observation of all four distinct colors. A bounded HTTP override applies only to managed Happy Hare O04; other tests retain their existing timeouts.
