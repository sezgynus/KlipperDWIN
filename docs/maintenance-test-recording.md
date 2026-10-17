# Temporary physical test recording

This tool is only for Maintenance physical acceptance. It observes existing menus; it never runs tests, changes safety, or grants automatic PASS/acceptance.

## Use

1. Maintenance → **Start test recording**.
2. Run tests in order from Self Tests or Diagnostics.
3. Answer the on-screen questions and enter the requested actual measurements. These answers are recorded too.
4. If something fails, you can proceed to another test without repeatedly retrying. If a test remains active, use its existing safe completion/cancel flow.
5. Finish with Maintenance → **Stop test recording**.
6. In [Remote Display](http://openeye3dpi.local:8088/), select **Download test recording** and attach the single ZIP to the conversation.

General URL: `http://<petrel-host>:8088/maintenance-test-trace.zip`.
This detailed recording is separate from Diagnostics S20; running S20 is unnecessary.
Starting/stopping recording never starts hardware. A stop request is refused while a test/read is active; it does not cancel that test.

## Captured evidence

- UTC/monotonic time, session/attempt IDs, test/device/method/READY epoch.
- Running git HEAD and starting config SHA-256; never config contents.
- Start, confirmation, choice, observation, measurement, cancel; return values and stage transitions.
- Allowlisted temperature/target/power, position, sensor, queue and related fields from existing Maintenance GET responses. No extra Moonraker queries.
- Command names/numeric parameters, script digest and RPC completion/error. RPC success is not physical PASS.
- Reason and last measurement **before** a shutdown request; final result/restore evidence.
- Before/after UI input: screen, page, selected row/label, adjacent rows, return menu and controller phase.
- Periodic UI transitions and tests remaining active behind another screen, including recovery.
- Raw firmware messages, full config, filenames, URLs and credentials are omitted.

A missing terminal result never means completion. The on-screen answer is the physical observation; describe any additional observation that cannot be expressed there separately.

## Continuity and limits

Recording is off by default. **After a Petrel service restart, choose Start test recording again.** A Klipper restart does not end recording if the same Petrel process remains alive.
Previously written disk events survive service restarts. Each start has its own session.
A power loss can lose the unwritten tail; writes are normally about once per second and may be delayed by existing worker load.

At most 128 pending events (8 KiB each) and two 4 MiB JSONL files are retained. Older data rotates; download intermediate ZIPs for long sessions.
Overflow/write errors appear as `(gaps)` in the menu and counters in the ZIP manifest. Downloads include the pending tail and do not clear records or issue hardware commands.
Disk writes use the existing **separate read worker**, never the Maintenance safety-read queue. No new thread is created.
Operator observation/choice waits gain no timeout.

ZIP: `events.previous.jsonl`, `events.jsonl`, `pending.jsonl`, `manifest.json`, `README.txt`.
Read in that order, then group by session/run/seq. Do not infer acceptance when rotation removed the beginning of an attempt.

## Removal

No permanent controller edits. Stopping restores original owner/client/worker references.
To remove the implementation:

- Remove `maintenance_test_trace.py` and `tests/test_maintenance_test_trace.py`.
- Remove hooks marked **TEMPORARY MAINTENANCE TEST TRACE** in `printerInterface.py`, `ui_maintenance.py`, `petrel_ui.py`; restore the original UI method names from their wrappers.
- Remove the Remote Display `trace_provider`, ZIP route and download link.
- Remove this TR/EN guide pair.

Data lives only in `~/.config/Petrel/maintenance-test-trace/`. After archiving and stopping Petrel, only that directory may be removed; permanent Maintenance history/usage/acceptance files are separate.
