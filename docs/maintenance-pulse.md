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

Each affected unit receives one \`MMU_SET_LED UNIT=<discovered-unit> [SEGMENT_EFFECT=(r,g,b)...] DURATION=1 FADETIME=0\` through **Happy Hare's own LED controller**, with a dim stimulus deliberately chosen to differ from the target LEDs' captured colors. One unit may receive multiple segment effects in one command; independent units are addressed individually. The adapter never writes raw \`SET_LED\` to a Happy Hare-owned chain and never disables the MMU LED manager. After the one-second Happy Hare timer, Petrel waits and checks each participating \`mmu_leds\` object's original \`enabled\` and \`animation\` flags with two readbacks. That checks *controller policy only*, not physical output or an animated color restoration; after the user's visual confirmation the outcome is \`OBSERVED_USER\`, **\`restore_verified=False\`**.

All physical tests keep double explicit user consent, fresh printer/queue/operation safety checks and bounded scripts. The managed path refuses disabled LED management, busy MMU actions, missing or conflicting section/status data, duplicate or out-of-range physical indexes, ambiguous multi-chain segments, unsupported names and independently configured effects targeting the physical chain. A partial subset of a physical chain is acceptable only when each modified pixel is positively mapped to its Happy Hare segment; unrelated pixels are never deliberately pulsed. Unknown third-party LED ownership remains blocked, not guessed. Mock CI is not hardware acceptance.

### Happy Hare numeric UNIT compatibility

The suffix of [mmu_leds NAME] is a unit NAME, not necessarily its G-code UNIT index. Some Happy Hare releases accept only numeric UNIT arguments. Petrel resolves the numeric index from the authoritative ordered [mmu_machine] units configuration (the same list used by Happy Hare to construct its units). It never parses digits out of unit names or assumes the first unit is always named unit0. An absent, duplicate or inconsistent mapping blocks the test before G-code dispatch. This fixes real installations reporting "unable to parse unit0".
