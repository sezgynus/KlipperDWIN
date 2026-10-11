# LCD compatibility

[English](lcd-assets.md) · [Türkçe](lcd-assets_TR.md) · [Documentation](README.md)

## Supported display

KlipperDWIN targets the **272×480 portrait DWIN T5UIC1** layout used by the compatible 4.3-inch Ender 3 V2 panel. DWIN, DACAI and TJC firmware/resource packs are not interchangeable.

The physical panel needs the matching stock icon library **7 (`7.ICO`)**, fonts and English bitmap resources. Display direction is **1**. Custom KlipperDWIN artwork is supplied separately with the application; see the [artwork guide](../assets/README.md).

## Before installing or replacing a panel

Check the controller family and installed resource pack, not just the screen size. The application installer does not flash LCD kernel firmware or install the stock font/icon pack. For panel firmware work, use the optional [T5UIC1 reference](t5uic1-reference.md).

After setup, inspect menu labels/icons, colors, preview images and encoder navigation on the physical display. A working emulator screenshot does not guarantee that a different panel/resource pack renders the same way.

## Print previews

Previews come from Moonraker and do not need a new panel asset pack. Missing thumbnails do not prevent starting a print. Images are prepared again after restarting or reconnecting; they do not replace installed icons.

## Resource identification

The [stock inventory](lcd-assets.json) records the resources previously audited for this project. It does not identify the files installed on your own panel. Contributor artwork and emulator font-selection instructions are linked from the [documentation index](README.md).
