# LCD artwork

[English](README.md) · [Türkçe](README_TR.md) · [Contributing](../CONTRIBUTING.md)

## Files in this folder

| File | Purpose |
|---|---|
| `klipperdwin_bootsplash.jpg` | Selected boot artwork, intended for panel picture slot 0 |
| `spool-empty.png` | Shared 42×52 empty spool sprite: wooden flanges and a thin gray hub |
| `display-settings.png` | Original transparent Display icon sprite |
| `klipperdwin-readme.png` | README logo and wordmark header adapted from the boot artwork |
| [emulator/](emulator/README.md) | Host-side stock icon and font inputs for screenshots |

The boot JPEG is 480×272 for panel picture slot 0. It is shown directly without cache copies.

## Managed icon library

Put baseline JPEG icons in [`assets/icons`](icons/README.md), with the icon ID in each filename. The application packs and uploads changed resources on its first LCD connection after an update. The packer reuses block gaps and never uses a block's final byte. The emulator uses the same sources.

## Screenshots

User-interface screenshots belong in `docs/assets/screens/`, not this artwork folder. Follow the [capture guide](../docs/ui-emulator.md) and preserve original 272×480 PNG output.

## After reinstalling panel resources

After reinstalling panel resources, force a reload of the managed icons over SSH as the service user:

```bash
sudo systemctl stop KlipperDWIN.service
~/klipperdwin-env/bin/python ~/KlipperDWIN/tools/reload_icons.py
sudo systemctl start KlipperDWIN.service
```

The tool reads the configured UART, rebuilds library 7 and reloads its blocks. Display settings are preserved.
