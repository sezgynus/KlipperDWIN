# Managed LCD icons

[English](README.md) · [Türkçe](README_TR.md)

Add or replace baseline JPEGs here. Use the icon ID as the filename prefix: `092.jpg`, `092-about.jpg` or `092_about.jpeg`. IDs are 0–255; each ID must occur once. Existing IDs retain their meaning. Renaming an icon without changing its ID or bytes does not trigger an upload. A new image enters the library; UI code chooses where its ID is displayed.

JPEGs are preserved without resizing or recompression. Progressive JPEGs, duplicate IDs and images larger than 32767 bytes are rejected. The whole library must fit Picture Flash slots 7–15; stock pictures 0–2 are untouched.

After an application update, the first LCD connection builds the library from this directory. The packer places larger icons first and fits smaller icons into remaining holes. Icon IDs do not depend on physical placement. Every block's last byte is reserved and excluded from UART writes. No JPEG crosses a block boundary.

Only changed blocks are uploaded; the directory block is committed last. Panel metadata records successful blocks, so a subsequent start resumes incomplete uploads. Unchanged libraries cause no Flash writes. A failed Picture Flash attempt is not repeated in the same process. Logs describe upload progress and failures.

Preview/export the exact runtime pack:

```bash
python tools/pack_icon_library.py assets/icons /tmp/7.ICO
```

The emulator uses these same JPEG sources. `assets/emulator/7.ICO` is a reference export, not the source for automatic updates.

Custom UI icons use IDs 100–109 and 124. MMU uses 100/101 and Display uses 108/109 for normal/selected 110×100 home tiles, matching the stock home icons. The empty spool uses ID 124. Wooden spool flanges use IDs 110–123 for widths 1–7, so compact lanes need no separate complete spool artwork. The symbolic mapping is in `lcd_resources.py`. All UI icons render directly through library 7.

After reinstalling panel resources, force a reload because stored metadata may still describe the previous installation:

```bash
sudo systemctl stop KlipperDWIN.service
~/klipperdwin-env/bin/python ~/KlipperDWIN/tools/reload_icons.py
sudo systemctl start KlipperDWIN.service
```

Write acknowledgements and metadata readback are verified; Picture Flash itself is not read back. Confirm the newly packed icon layout on the physical display.
