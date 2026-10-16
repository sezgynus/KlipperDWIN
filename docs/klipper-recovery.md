# Klipper recovery
Petrel distinguishes Moonraker reachability from Klipper readiness. After an MCU
shutdown or Klipper configuration error, the LCD shows the reported state_message
(including the MCU name) and scrollable error details instead of a dead-end
"Moonraker unavailable" screen.

- Refresh connection only requests status; it never restarts anything.
- Restart Klipper reloads the host/configuration through POST /printer/restart.
- Firmware Restart resets Klipper and connected MCUs through POST /printer/firmware_restart.
- If Klipper is disconnected, Restart Klipper service is offered only when
  /machine/system_info identifies this instance's exact service in
  instance_ids.klipper and available_services. No service name is guessed.
- A genuinely unreachable Moonraker shows connection retry information.
  It cannot be restarted through an unreachable API.
- Starting/ready Klipper does not offer restart commands on a stale error screen.

Every restart requires a separate confirmation, initially Cancel. Check the
printer and correct the underlying fault before restarting. Commands are
dispatched on the existing HTTP command worker with a fresh server/printer
check immediately before dispatch. An acknowledgement is not proof of READY;
the existing subscription must recover. Failed or ambiguous commands are never
automatically replayed. Recovery returns to Home, without resuming interrupted
heating, movement, printing or Maintenance tests. Existing thermal safety limits
are unchanged.

Offline checks run at most one outstanding job on the existing bounded read
worker, with a two-second retry interval after completion. No additional threads
or transports are created. Normal READY operation does not run recovery reads.
Cold boot with Klipper already in error also exposes the recovery menu.
The screen remains usable through the encoder despite Klipper not being READY.

Regression tests cover state/error distinctions, MCU text, exact service
selection, fresh dispatch guards, duplicate/ambiguous commands, explicit
confirmation, scrolling, cold boot and recovery navigation. CI only; no local
test suite or emulator was run. Physical acceptance remains pending.
