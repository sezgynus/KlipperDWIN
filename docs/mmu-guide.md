# MMU and filament

[English](mmu-guide.md) · [Türkçe](mmu-guide_TR.md) · [Documentation](README.md)

## Open the MMU menu

With a configured Happy Hare MMU, select **Home → MMU**. Home also shows gate colors and, when Spoolman data is available, remaining filament percentages. Missing Spoolman information does not prevent other MMU functions.

<p align="center">
  <img src="assets/screens/mmu.png" width="220" alt="Loaded filament">
  <img src="assets/screens/mmu-loading.png" width="220" alt="Live path during loading">
  <img src="assets/screens/mmu-unloading.png" width="220" alt="Live path during unloading">
  <img src="assets/screens/mmu-purging.png" width="220" alt="Purge and residual filament color">
</p>

Rotate to select; press to activate. Select a colored **T0, T1, …** button to change filament: Happy Hare unloads the current tool and loads the chosen tool automatically. The gate above each spool shows its actual mapping; several tools can use the same gate. More than four tools appear in groups as you rotate. **G0 is Happy Hare gate 0**.

The vertical diagram follows filament loading and withdrawal. The Gate circle fills green when filament is detected. The nozzle retains the previous filament color while residual material remains; purge has a small extrusion animation and follows Happy Hare's reported color. The MMU screen shows nozzle temperature; general printer information remains on Home.

The overview's tool and **Load/Unload** buttons start immediately and keep the diagram visible. **More** opens gates, mapping, bypass, management and detailed status. Actions on those pages open a confirmation with **Cancel initially selected**. Routine movement and edits require an idle MMU outside printing/pauses. Unsupported options are hidden; actions may be locked when the printer state is busy, unknown or unsuitable. Check the actual printer before retrying a failed/unconfirmed operation.

<p align="center">
  <img src="assets/screens/mmu-more.png" width="220" alt="Additional MMU controls">
</p>

## Gates and loading

<p align="center">
  <img src="assets/screens/mmu-gates.png" width="220" alt="Select a gate">
  <img src="assets/screens/mmu-gate-details.png" width="220" alt="Gate actions">
  <img src="assets/screens/mmu-confirm.png" width="220" alt="Action confirmation">
</p>

Open **MMU → More → Gates → [gate]**:

| Action | Use |
|---|---|
| Select only | Select the physical gate; the selector may move |
| Load selected | Load filament from that gate |
| Load / change | Use a logical tool associated with the gate and its Happy Hare mapping |
| Unload | Park loaded filament back in the MMU |
| Eject spool | Remove filament from the MMU, unloading the active gate first if needed |
| Preload | Prepare the gate's filament using Happy Hare |
| Check | Check the selected gate |
| Filament details | View name, material, color, spool ID, remaining percentage, temperature and Spoolman mode |

Confirm the gate/tool named on the screen before accepting. The MMU Home Load/Unload shortcut operates on the current gate.

## Spool assignments

<p align="center">
  <img src="assets/screens/mmu-filament.png" width="220" alt="Filament and Spoolman details">
  <img src="assets/screens/mmu-spool.png" width="220" alt="Assign a spool ID">
</p>

Open **Gates → [gate] → Filament details → Assign spool ID**. Press **Spool ID**, rotate to the positive numeric ID, press to accept the edit, then choose **Save** and confirm. **Cancel** discards the draft. Use **Clear assignment** to remove an assignment explicitly.

Assignment depends on the configured Spoolman mode: known `off`, `readonly` and `push` modes allow local edits; `pull` and unknown modes remain locked. Required filament information must be available. A duplicate-ID warning means the ID will move from another gate. Confirm the spool exists and inspect Spoolman afterwards if synchronization is expected.

## Tool map

<p align="center">
  <img src="assets/screens/mmu-tool-map.png" width="220" alt="Tool-to-gate mapping">
</p>

Open **MMU → More → Tool map**. Select a tool, press, rotate to its gate and press to accept. Repeat for other tools, then **Save** and confirm, or **Cancel** to discard the draft. Several tools can share one gate.

Make edits while idle and outside printing/pauses. If the mapping changes from the web UI during editing, reopen the editor before continuing.

## EndlessSpool

<p align="center">
  <img src="assets/screens/mmu-endless-spool.png" width="220" alt="EndlessSpool groups">
  <img src="assets/screens/mmu-group-members.png" width="220" alt="Choose group members">
</p>

From **Tool map**, open **EndlessSpool**. It groups compatible replacement spools so Happy Hare can continue when a spool runs out.

1. Press **Enabled**, rotate and press to accept the desired state.
2. Open a group and press gates to add/remove membership. Removing a member gives it a separate group; the last member stays.
3. Check the displayed material/color compatibility and the physical spools.
4. Choose **Save** and confirm, or **Cancel** to discard the draft. Back from a member page keeps the draft.

Make changes while idle and outside printing/pauses. Matching metadata is a guide; verify the actual filament is suitable for substitution.

## Bypass

<p align="center">
  <img src="assets/screens/mmu-bypass.png" width="220" alt="Bypass actions">
</p>

Open **MMU → More → Bypass**. First **Unload current gate**, then **Select bypass**. Use **Load extruder** and **Unload extruder** for the extruder-only filament path. Confirm each operation. Bypass selection requires unloaded filament.

## Recovery and status

<p align="center">
  <img src="assets/screens/mmu-recovery.png" width="220" alt="Recovery options">
  <img src="assets/screens/mmu-manual-state.png" width="220" alt="Report the actual filament state">
</p>

<p align="center">
  <img src="assets/screens/mmu-manage.png" width="240" alt="Manage and recovery">
  <img src="assets/screens/mmu-status.png" width="240" alt="MMU status and sensors">
</p>

During a print, an MMU error stays on Print as a summary; **MMU** replaces **Resume**. Follow **Print → MMU → full error → MMU recovery**; rotate to scroll long text. **Back** returns to Print. You can also use **MMU → More → Manage → Recover state**. A failed overview operation changes its main button to **Recover**. See [Print/Tune](print-controls.md).

1. Read the error and fix the physical filament problem.
2. Use recovery, or the manual state editor to report the actual gate/tool/filament state. Manual Apply reports state; it does not load or unload filament.
3. Unlock/reheat if needed.
4. Choose **Resume** separately once the print is paused, the MMU is unlocked and filament is loaded.

**Status** / **Sensors / status** shows the current action, available Bowden-stage progress, sensors, gear sync, nozzle temperature and operation result. Bowden percentage describes that stage, not the whole tool change. `CLEAR`, `TRIGGERED`, `UNKNOWN/OFF` and `ABSENT` distinguish sensor conditions.

## Maintenance and options

<p align="center">
  <img src="assets/screens/mmu-maintenance.png" width="240" alt="MMU maintenance">
  <img src="assets/screens/mmu-options.png" width="240" alt="MMU options">
</p>

Open **Manage → Maintenance** or **Manage → Options**. Controls depend on the installed Happy Hare configuration and reported state:

| Page / option | Use and prerequisite |
|---|---|
| Maintenance → Check all gates | Check every configured gate |
| Maintenance → Home selector | Available for a supported single linear-selector unit; confirmation identifies the tool selected afterwards |
| Maintenance → Grip / Release | Supported selector grip control with unloaded filament; Release is omitted for always-gripped units |
| Options → Gear sync ON/OFF | Synchronize MMU gear and extruder with loaded filament; always-gripped units cannot unsync |
| Options → Enable/Disable MMU | Requires unloaded filament outside printing/pauses; enabling resets Happy Hare state |
| Options → Release MMU motors | Release the MMU motors when supported; requires unloaded filament outside printing/pauses and may lose homing |
| Options → LEDs | Active-unit on/off, animation and exit modes: Off, Gate status, Filament color or Slicer color |
| Options → Units | Browse multiple units and their global gates; Select this unit separately confirms selection of its first gate and may move/home the selector |

Units is omitted for single-unit installations. Unit selection needs unloaded filament outside printing/pauses. LED options require supported active-unit LED information. Use the web interface for **MMU calibration, custom LED effects and entry/status/logo LED configuration**.

<p align="center">
  <img src="assets/screens/mmu-leds.png" width="220" alt="LED modes">
  <img src="assets/screens/mmu-units.png" width="220" alt="Multiple-unit list">
  <img src="assets/screens/mmu-unit-gates.png" width="220" alt="Gates of a unit">
</p>
