# LCD artwork

[English](README.md) · [Türkçe](README_TR.md) · [Contributing](../CONTRIBUTING.md)

## Files in this folder

| File | Purpose |
|---|---|
| `klipperdwin_atlas_0.jpg` | Custom static icons: MMU, folders, machine/host/MCU/software, power, Display and the shared empty spool |
| `klipperdwin_atlas_1.jpg` | Empty reserve; no icons currently use it |
| `klipperdwin_bootsplash.jpg` | Selected boot artwork, intended for panel picture slot 0 |
| `spool-empty.png` | Shared 42×52 empty spool sprite: wooden flanges and a thin gray hub |
| `display-settings.png` | Original transparent Display icon sprite |
| `klipperdwin-readme.png` | README logo and wordmark header adapted from the boot artwork |
| [emulator/](emulator/README.md) | Host-side stock icon and font inputs for screenshots |

Atlas filenames must stay unchanged. Atlas JPEGs are **480×272 baseline JPEGs** for the physical panel; icon positions are in the portrait **272×480** layout. The boot artwork is supplied here; placing it in this folder alone does not replace the panel's existing boot image.

## Prepare a new icon

Use a transparent PNG sprite. The patch tool finds space in Atlas 0, keeps existing decoded icons unchanged and checks the panel's 32 KiB image limit. Install its build-only dependencies in a separate development environment:

```bash
python3 -m venv .venv-artwork
.venv-artwork/bin/python -m pip install Pillow numpy jpeglib
.venv-artwork/bin/python tools/patch_atlas_icon.py sprite.png candidate-atlas.jpg
```

Run from the repository root. Use a **separate output filename**; the tool rejects overwriting the source atlas. It prints the new icon rectangle. Register the icon in `lcd_atlas.py` as part of the code change, review old/new icons, run the relevant tests and verify the result on a panel before replacing the tracked atlas.

## Managed icon library

Put baseline JPEG icons in [`assets/icons`](icons/README.md), with the icon ID in each filename. The application packs and uploads changed resources on its first LCD connection after an update. The packer reuses block gaps and never uses a block's final byte. The emulator uses the same sources.

## Screenshots

User-interface screenshots belong in `docs/assets/screens/`, not this artwork folder. Follow the [capture guide](../docs/ui-emulator.md) and preserve original 272×480 PNG output.

## After reinstalling panel resources

Atlases use Picture Flash slots 5 and 6. The second atlas is not uploaded while empty. A panel resource reinstall can leave stale atlas version metadata. Run these commands over SSH as the service user:

```bash
sudo systemctl stop KlipperDWIN.service
~/klipperdwin-env/bin/python ~/KlipperDWIN/tools/reload_atlases.py --force
sudo systemctl start KlipperDWIN.service
```

The tool reads the UART device from `~/.config/KlipperDWIN/KlipperDWIN.env`; override it with `--serial-port /dev/ttyS0` if needed. It rewrites only active atlases and updates their version records, preserving display settings.
