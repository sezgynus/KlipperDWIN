# LCD compatibility

[English](lcd-assets.md) · [Türkçe](lcd-assets_TR.md) · [Documentation](README.md)

## Supported display

Petrel targets the **272×480 portrait DWIN T5UIC1** layout used by the compatible 4.3-inch Ender 3 V2 panel. DWIN, DACAI and TJC firmware/resource packs are not interchangeable.

The panel must support T5UIC1 commands and display direction **1**. Petrel renders text with the **stock DWIN font**; the [bundled LCD font](#lcd-font) is **optional**, for a different visual style. The application automatically uploads boot artwork and library **3** icons from repository sources; stock `3.ICO` and English bitmap labels are not prerequisites.

## Persistent LCD assets and stock recovery

> **⚠️ Stock artwork is replaced automatically.** The original Ender-3 V2 resource set did not provide the complete icon states, animations and artwork needed by Petrel's modern UI. To preserve predictable visuals and responsive native icon drawing, Petrel now manages its own images in non-volatile **Picture Flash**. This is **not temporary** and is not undone by uninstalling Petrel.

- **Boot JPEG:** Petrel synchronizes its `assets/petrel_bootsplash.jpg` to Picture Flash **slot 0**.
- **Icon library 3:** Petrel packs the baseline JPEGs under `assets/icons/` into 32 KiB blocks starting at **slot 3**, within slots **3–15**, and uploads only changed blocks. This provides menu icons, selected states, print controls and animation frames without redrawing all artwork as primitives.
- **Write reduction:** Content fingerprints are kept in a separate persistent Data Flash area, so matching resources are normally skipped. These fingerprints are **not a backup** of the original OEM images.
- **Not overwritten automatically:** Stock picture slots **1–2**, the LCD kernel and font resources. Print thumbnails are transferred to volatile SRAM. The bundled ASCII font is **optional** and is installed manually by SD card only if the user chooses it.

**To restore the stock Creality boot image and icon resources, flash the [original DWIN_SET](../assets/stock-dwin/DWIN_SET) from the LCD microSD slot** after stopping Petrel. Follow the [original DWIN restoration guide](restore-stock-dwin.md). Merely uninstalling the host service cannot restore Picture Flash. This package is for **DWIN T5UIC1 only**; it is not interchangeable with DACAI/TJC. The original LCD files also do not restore the printer mainboard firmware.

## Before installing or replacing a panel

Check the controller family and installed resource pack, not just the screen size. The application installer does not flash LCD kernel firmware or install the LCD font. For panel firmware work, use the optional [T5UIC1 reference](t5uic1-reference.md).

After setup, inspect menu labels/icons, colors, preview images and encoder navigation on the physical display. A working emulator screenshot does not guarantee that a different panel/resource pack renders the same way.

## Print previews

Previews come from Moonraker and do not need a new panel asset pack. Missing thumbnails do not prevent starting a print. Images are prepared again after restarting or reconnecting; they do not replace installed icons. Thumbnails use baseline 4:2:0 JPEG at quality 94 with black backing and native enhanced background filtering. Dark model pixels are lifted to a minimum luminance of 48 before alpha compositing, so pure black becomes dark gray; fully transparent pixels and letterboxing remain black and reveal the UI surface. Partial-alpha edges may be clipped by the panel filter; inspect them on hardware.

## Resource identification

The application now builds library 3 from [`assets/icons`](../assets/icons/README.md) and automatically uploads changed blocks at the first LCD connection after an update. Unchanged resources are skipped. Follow that guide to add JPEGs, export a pack or force a reload after reinstalling panel resources.

Automatic synchronization is the normal path. For developer diagnostics, the following command rebuilds the pack from current `assets/icons` JPEG sources and uploads it over UART; it does not read the reference ICO file:

```sh
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py && sudo systemctl start Petrel.service
```

The tool uses the configured serial port and writes slots starting at 3 (one slot per 32 KiB block). Failed writes leave the service stopped. It checks write acknowledgements, without Flash readback. Inspect the icons on the physical panel after upload.

To inspect the reference export itself, pass `--file` explicitly with the service stopped. This uploads the specified file's bytes rather than rebuilding from JPEG sources; the reference export may differ or be older if sources have changed:

```sh
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/flash_icon_library.py --file ~/Petrel/assets/emulator/3.ICO && sudo systemctl start Petrel.service
```

For contributor artwork, `tools/pack_icon_library.py source.ICO destination.ICO --library 3` preserves JPEG images while keeping each icon within one 32 KiB block. This layout avoids splitting icons at the boundaries associated with the observed rendering faults.

The [stock inventory](lcd-assets.json) records the resources previously audited for this project. It does not identify the files installed on your own panel. Contributor artwork and emulator font-selection instructions are linked from the [documentation index](README.md).

## LCD font

**Optional — Petrel works with the stock DWIN LCD font.** Changing the font is a visual preference, not a requirement for Petrel's features or performance. The bundled ASCII font can make physical text resemble Petrel's documentation screenshots. If you choose to use it, copy the font-only `assets/fonts/DWIN_SET` directory (containing `0T5UIC1.HZK`) to a compatible LCD update SD card, power off the printer, insert the card in the LCD's card reader and power on. Wait for the resource update to finish, power off, remove the card and start normally. **Do not use the separate stock-recovery `assets/stock-dwin/DWIN_SET` for this optional font change.** Petrel's boot artwork and icon library update automatically over UART, but the Pi service never uploads font Flash. The emulator uses the bundled font, so screenshots can have different typography from a physical panel retaining its stock font. The font's DejaVu license is in `assets/emulator/Petrel-font-license.txt`.
