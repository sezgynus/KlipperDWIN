# Maintenance system diagnostics

[Turkish](maintenance-system_TR.md)

S01–S10 read actual host, disk, MCU, CAN, classified recent events and recorded print-history data. MCU names remain separate; null CAN fields are not faults. S04 lists one directory only on explicit request and retains disk totals, never filenames. S09 retains event/error counts and known error categories, not raw console lines or tokens. S19 reads update status without refreshing or installing updates; ordinary update controls stay in Info.

S11 stores up to 64 result records with actual method, timestamp, device, planned epoch/config marker, firmware/config identity and allowlisted evidence. No CI result is physical acceptance. S12 records bounded sampled lower-bound heater/fan ON time: only intervals <=2 s with ON at both ends count. Missing samples, downtime and crash losses are not invented lifetime hours. Inventory is cached per epoch; normal ticks do no I/O. Flush uses the existing worker.

S13 requires an authoritative extension counter, never position-difference integration. Declare maintenance-travel-counter.json under ~/.config/Petrel with {"version":1,"object":"your_registered_object","authoritative":true}; the registered object must return nonnegative x_mm/y_mm/z_mm counters in mm. Without it the feature stays hidden.

S14 reports actual driver TX/RX, handshake requests, response timeouts, CRC notifications and bounded RX drops, scoped to the current driver/UART epoch. CRC notifications are panel protocol events, not optical checks. S15 counts physical GPIO rotation steps and button edges; remote inputs do not increment them. Its guided test requires new physical steps in both directions plus a new physical button edge after Start; counter reads alone cannot PASS. No printer snapshot is taken in the GPIO callback.

S16 offers explicit red/green/blue/white/black observation patches on the physical LCD, plus startup-asset-sync information. S17 offers explicitly advanced 10/50/100% backlight levels and restores the captured runtime brightness. Settings are not saved. Auto-dimming is suspended only during the owned panel workflow. No user question expires, and a reconnected panel cannot silently receive an old session's brightness command.

S20 explicitly writes ~/.config/Petrel/maintenance-report.json. Remote Display can download the last export at /maintenance-report.json using its existing Host/Origin boundary. Download never generates a report or starts a test. No raw config, filenames, URLs or API keys are exported.

All reads/preflights are bounded and asynchronous. Physical panel observations remain pending real-printer acceptance.
