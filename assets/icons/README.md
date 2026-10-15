# Managed LCD icons

[English](README.md) · [Türkçe](README_TR.md)

Add or replace baseline **4:2:0 JPEGs** here. Use the icon ID as the filename prefix: `092.jpg`, `092-about.jpg` or `092_about.jpeg`. IDs are 0–255; each ID must occur once. Existing IDs retain their meaning. Renaming an icon without changing its ID or bytes does not trigger an upload. A new image enters the library; UI code chooses where its ID is displayed.

JPEGs are preserved without resizing or recompression. Progressive JPEGs, other color sampling formats, duplicate IDs and images larger than 32767 bytes are rejected. The whole library must fit Picture Flash slots 3–15; picture 0 holds Petrel boot artwork, picture 1 holds the shared UI artwork page and picture 2 is unused.

After an application update, the first LCD connection builds the library from this directory. The packer places larger icons first and fits smaller icons into remaining holes. Icon IDs do not depend on physical placement. Every block's last byte is reserved and excluded from UART writes. No JPEG crosses a block boundary.

Only changed blocks are uploaded; the directory block is committed last. Panel metadata records successful blocks, so a subsequent start resumes incomplete uploads. Unchanged libraries cause no Flash writes. A failed Picture Flash attempt is not repeated in the same process. Logs describe upload progress and failures.

Preview/export the exact runtime pack:

```bash
python tools/pack_icon_library.py assets/icons /tmp/3.ICO --library 3
```

The emulator uses these same JPEG sources. `assets/emulator/3.ICO` is a reference export, not the source for automatic updates.

Custom UI icons use IDs 100–109 and 124. MMU uses 100/101 and Display uses 108/109 for normal/selected 110×100 home tiles, using the established native tile footprint. The empty spool uses ID 124. Metal spool flanges use IDs 110–123 for widths 1–7, so compact lanes need no separate complete spool artwork. The symbolic mapping is in `lcd_resources.py`. All UI icons render directly through library 3.

After reinstalling panel resources, force a reload because stored metadata may still describe the previous installation:

```bash
sudo systemctl stop Petrel.service
~/petrel-env/bin/python ~/Petrel/tools/reload_icons.py
sudo systemctl start Petrel.service
```

Write acknowledgements and metadata readback are verified; Picture Flash itself is not read back. Confirm the newly packed icon layout on the physical display.

## Graphite

Graphite adds dedicated IDs 210–234 for light, brightness, sound settings, motion parameters, calibration and profiles. Editable SVG sources are in `assets/icon-source`; use `python tools/render_icon_sources.py` to regenerate JPEGs (developer dependency: CairoSVG). Black JPEG backing is filtered with the native transparent/enhanced icon mode; menu and dashboard surfaces remain visible. The icon pack starts at picture slot 3 and may use slots 3–15; its 512-byte metadata record occupies Data Flash `0x0200–0x03FF`.

## Print buttons, switches and fan artwork

Print buttons contain the rounded surface, selection outline and Lucide symbol in one JPEG; labels remain native panel text using font ID **0**. Normal narrow buttons use **243–247** and selected variants **125–129** (78×36); completed-print Tune/Close pairs use **130–133** (119×36). AFTER JOB switches use **248/249** (27×12). Keep normal/selected silhouettes identical: the renderer uses a hard rounded mask with the same neutral opaque perimeter so filtered JPEG edges do not retain the previous state.

Fan frames **235–242** use a neutral fan symbol on the dashboard's **RGB565 `0x18C4`** background. The SVG uses mid-bin RGB `#1c1a24` so JPEG rounding stays inside that RGB565 color. Native animation (`0x28`) has no background-filter option, so these frames are opaque; the stopped fan uses the same opaque rendering. Preserve this backing when regenerating from SVG. Fan and full-button JPEGs use **quality 100**, baseline **4:2:0**. Other generated icons use quality 94. Regenerate from SVG rather than recompressing JPEGs. Lucide source licensing: [Lucide license](../icon-source/Lucide-LICENSE.txt).

## Package size and reserved space

The current reference pack occupies **9×32 KiB = 288 KiB**, slots **3–11**. The reserved maximum is **13×32 KiB = 416 KiB**, slots **3–15**, leaving slots **12–15** available for growth. This is allocated block space, not an exact JPEG payload budget: the directory, placement gaps and reserved final bytes also consume space. Picture Flash is separate from the **512-byte Data Flash metadata record at 0x0200–0x03FF**. Pass `--library 3` to export; the export tool's legacy default is 7, with a different available slot count.

## JPEG compatibility rule

All managed icons must be baseline RGB/YCbCr JPEG with 4:2:0 sampling (`Pillow: subsampling=2`). Render directly from SVG using `tools/render_icon_sources.py`; do not repeatedly recompress JPEGs. Physical T5UIC1 tests reproduced damaged selected home tiles and homing artwork with 4:4:4 from both Flash and byte-verified SRAM; 4:2:0 rendered correctly. A clean emulator preview cannot validate the panel JPEG decoder. The source loader rejects other sampling formats before any panel access, and CI checks every shipped icon and the exported ICO against its sources. Check selected/unselected home tiles, homing, small menu/status icons and animation on hardware after artwork updates.
