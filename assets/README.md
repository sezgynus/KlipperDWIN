# LCD artwork

[English](README.md) · [Türkçe](README_TR.md) · [Contributing](../CONTRIBUTING.md)

## Files in this folder

| File | Purpose |
|---|---|
| `petrel_bootsplash.jpg` | Petrel bird logo and slogan boot artwork for panel picture slot 0 |
| `spool-empty.png` | Shared 42×52 empty spool sprite: wooden flanges and a thin gray hub |
| `display-settings.png` | Original transparent Display icon sprite |
| `petrel-readme.png` | Petrel bird logo, wordmark and slogan header used by both main READMEs |
| [emulator/](emulator/README.md) | Host-side stock icon and font inputs for screenshots |
| [stock-dwin/](stock-dwin/README.md) | Original Creality DWIN_SET bundle for restoring stock LCD firmware and artwork |

The boot JPEG is 480×272 for panel picture slot 0. It is shown directly without cache copies. After boot artwork synchronization, the splash, progress bar and loading animation are displayed before icon-library preparation and checks. Unchanged icon synchronization does not stop the animation; actual icon uploads stop it temporarily and the next boot stage restarts it.

Changed boot artwork is uploaded automatically to picture slot 0 on the first LCD connection. A verified fingerprint at Flash address `0x0120` prevents repeated writes; the JPEG must be baseline 480×272 and at most 32767 bytes.

## Managed icon library

Put baseline JPEG icons in [`assets/icons`](icons/README.md), with the icon ID in each filename. The application packs and uploads changed resources on its first LCD connection after an update. The packer reuses block gaps and never uses a block's final byte. The emulator uses the same sources.

Print buttons, switches, fan frames, source licenses and the distinction between current package size and reserved space are documented in the [icon source guide](icons/README.md#print-buttons-switches-and-fan-artwork).

## Screenshots

User-interface screenshots belong in `docs/assets/screens/`, not this artwork folder. Follow the [capture guide](../docs/ui-emulator.md) and preserve original 272×480 PNG output.

## After reinstalling panel resources

After reinstalling panel resources, force a reload of the managed icons over SSH as the service user:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

The tool reads the configured UART, rebuilds library 3 and reloads its blocks. Display settings are preserved.
