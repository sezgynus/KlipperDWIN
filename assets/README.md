# LCD artwork

[English](README.md) · [Türkçe](README_TR.md) · [Contributing](../CONTRIBUTING.md)

## Files in this folder

| File | Purpose |
|---|---|
| `petrel_bootsplash.jpg` | Petrel bird logo and slogan boot artwork for panel picture slot 0 |
| `petrel_shared.jpg` | Slot 1 shared artwork page; project QR at portrait origin |
| `spool-empty.png` | Shared 42×52 empty spool sprite: wooden flanges and a thin gray hub |
| `display-settings.png` | Original transparent Display icon sprite |
| `petrel-readme.png` | Petrel bird logo, wordmark and slogan header used by both main READMEs |
| [emulator/](emulator/README.md) | Host-side stock icon and font inputs for screenshots |

The boot JPEG is 480×272 for panel picture slot 0. It is shown directly without cache copies. After boot artwork synchronization, the splash, progress bar and loading animation are displayed before icon-library preparation and checks. Unchanged icon synchronization does not stop the animation; actual icon uploads stop it temporarily and the next boot stage restarts it.

Changed boot artwork is uploaded automatically to picture slot 0 on the first LCD connection. A verified fingerprint at Flash address `0x0120` prevents repeated writes; the JPEG must be baseline 480×272 and at most 32767 bytes.

## Shared UI artwork page

`petrel_shared.jpg` occupies Picture Flash **slot 1**. The **272×480 portrait** page holds the project QR in its upper-left **168×168** region; remaining space can hold future artwork. The physical JPEG must be **480×272**, baseline 4:2:0 and at most **32767 bytes**. Additional artwork must stay within the same dimensions and total JPEG size limit, without overlapping source coordinates in `shared_artwork.py`.

`python tools/render_project_qr.py` regenerates the SVG source and page (developer dependency: CairoSVG). The QR is absent from the ICO library. Changed pages upload automatically at the first LCD connection; the Data Flash fingerprint at `0x0150–0x0177` skips unchanged files. Opening Info decodes the page into Area 1 without changing the display; scrolling copies only the newly exposed QR region opaquely. Another picture replacing Area 1 or an LCD reconnect causes the cache to be prepared again.

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

The tool reads the configured UART, rebuilds library 3 and reloads its blocks and the shared slot-1 page. Display settings are preserved.
