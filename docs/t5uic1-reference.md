# T5UIC1 LCD configuration and protocol reference

KlipperDWIN targets the DWIN **T5UIC1** command-driven display used by the
Ender 3 V2 family. This document covers the complete LCD-side configuration
surface used by this project: kernel firmware, `T5UIC1.CFG` hardware
configuration, SD-card assets, memory regions and runtime UART commands.

The intent is to keep panel configuration details out of UI code. Runtime
communication belongs in `t5uic1_driver.py`; boot-time hardware settings and
installed assets belong to the display firmware bundle.

## Configuration layers

The display has several independent configuration layers. They should not be
treated as one interchangeable mechanism.

| Layer | Stored/configured by | Purpose |
|---|---|---|
| Kernel/program | `T5UIC1_*.BIN` | T5UIC1 kernel/program upgrade |
| Hardware configuration | `T5UIC1.CFG` | CPU clock, boot behavior, CRC, default orientation, LCD selection and main UART baud rate |
| Font library | `0T5UIC1.HZK` | Panel-side font resources |
| JPEG pages | picture IDs `0..15` | Boot/background/full-screen images |
| Icon libraries | icon-library IDs `0..15` | Panel-side icon resources |
| Data SRAM | selector `0x5A` | 32 KiB volatile working memory |
| Data Flash | selector `0xA5` | 16 KiB non-volatile application data |
| Runtime commands | UART instruction set | Drawing, cache, animation, memory and display control |

Changing a runtime UART setting does not necessarily change the corresponding
boot-time hardware setting. For example, opcode `0x34` changes orientation at
runtime, while the orientation bits in `T5UIC1.CFG` define the boot default.

## SD-card firmware bundle

The T5UIC1 update bundle is placed in a `DWIN_SET` directory on a FAT32 SD/SDHC
card using 4 KiB allocation units. The T5UIC1 v2.3 guide defines these file
families:

| File | Role |
|---|---|
| `T5UIC1_*.BIN` | Program/kernel upgrade |
| `T5UIC1.CFG` | Hardware profile/configuration |
| `0T5UIC1.HZK` | Font library |
| `<ID>*.JPG` | JPEG picture storage, ID `0..15` |
| `<ID>*.ICO` | JPEG icon library storage, ID `0..15` |

JPEG page files must match the physical screen resolution, use baseline JPEG,
and use a supported sampling mode. The T5UIC1 guide also limits a single JPEG
image to 32 KiB. KlipperDWIN's audited asset layout and icon/cache assumptions
are documented separately in [lcd-assets.md](lcd-assets.md).

## T5UIC1.CFG hardware configuration

`T5UIC1.CFG` is a binary hardware-configuration file. Defined fields occupy
offsets `0x00..0x0A`; unused bytes should be written as `0x00`.

### Field map

| Offset | Length | Field | Definition |
|---:|---:|---|---|
| `0x00` | 4 | Identification | Fixed `54 35 43 31` (`T5C1`) |
| `0x04` | 1 | System configuration | CPU clock, boot display, CRC enable and orientation |
| `0x05` | 1 | LCD selection | Physical LCD profile selector |
| `0x06` | 2 | System clock calibration | `5A A5` starts factory-style clock calibration |
| `0x08` | 2 | Main UART baud divisor | `baud = 7,833,600 / divisor` |
| `0x0A` | 1 | LCD-selection enable | `0x5A` enables the selection in `0x05`; other values disable it |

### System configuration byte: offset 0x04

| Bits | Meaning | Values |
|---|---|---|
| `7` | CPU frequency | `0` = 250 MHz, `1` = 400 MHz |
| `6` | Power-on display behavior | `0` = display picture ID 0, `1` = clear black and turn backlight off |
| `5` | Main UART CRC checking | `0` = disabled, `1` = enabled |
| `4..2` | Reserved | Write `0` |
| `1..0` | Default display direction | `00` = 0°, `01` = 90°, `10` = 180°, `11` = 270° |

The stock KlipperDWIN transport currently assumes **CRC disabled**. The driver
parses the panel's inbound `0xFF` CRC-error report, but enabling CFG bit 5
would also require validating/implementing the CRC-enabled TX/RX frame format
before that mode can be supported safely.

### LCD selection: offset 0x05

The T5UIC1 guide defines LCD profile IDs including:

| Value | LCD profile |
|---:|---|
| `0x00` | 480×272 `DMT48270C043_04WN` |
| `0x01` | 240×320 `DMT32240C028_04WN` (older model) |
| `0x02` | 320×240 `DMT32240C035_04WN` |
| `0x03` | 240×320 `DMT32240C028_04WN` |
| `0x04` | 320×480 `DMT48320C035_04WN` |
| `0x05` | 240×320 `DMT32240C024_04WN` |
| `0x06` | 320×480 `DMT48320C035_04WN` IPS variant |

Later selection IDs are listed in the translated v2.3 guide, but their model
text is ambiguous in that translation. KlipperDWIN does not depend on those
profiles.

The byte at `0x05` is used only when offset `0x0A` contains exactly
`0x5A`. Any other `0x0A` value leaves the selection override disabled.

### System clock calibration: offsets 0x06-0x07

Writing `5A A5` starts the T5UIC1 system-clock calibration procedure. During
calibration UART2 emits repeated `0x55` data at 115200 8N1. DWIN documents the
clock as factory-calibrated; normal users should leave this field zero.

### Main UART baud rate: offsets 0x08-0x09

The 16-bit divisor is calculated as:

```text
divisor = 7,833,600 / requested_baud
actual_baud = 7,833,600 / divisor
```

The valid divisor range is `1..1023`. The standard KlipperDWIN configuration
uses:

```text
0x0044 = 68
7,833,600 / 68 = 115,200 baud
```

This is the **main UART** setting used for the host-to-display protocol. It is
not the same as opcode `0x38`, which configures the T5UIC1 extended/auxiliary
serial interface at runtime.

## KlipperDWIN reference panel configuration

The panel used to develop and physically validate KlipperDWIN currently runs:

```text
Kernel: T5UIC1_V20_4页面_191022.BIN

T5UIC1.CFG:
54 35 43 31 81 00 00 00 00 44 00 00 00 00 00 00
```

Decoded configuration:

| Setting | Current value |
|---|---|
| Identification | `T5C1` |
| CPU frequency | **400 MHz** |
| Power-on display | **Picture ID 0** |
| Main UART CRC | **Disabled** |
| Default orientation | **90°** |
| LCD selection byte | `0x00` |
| LCD-selection override | **Disabled** because `0x0A = 0x00` |
| Clock calibration | Disabled / zero |
| Main UART divisor | `0x0044` |
| Main UART baud rate | **115200** |

This matches the runtime assumptions in KlipperDWIN: the serial port opens at
115200 baud, CRC framing is not enabled, and startup applies runtime direction
`1` (90°).

## Boot-time configuration vs runtime control

Some settings exist only in `T5UIC1.CFG`, some only as UART commands, and some
have both boot-time and runtime forms.

| Function | Boot-time configuration | Runtime control |
|---|---|---|
| CPU frequency | CFG `0x04[7]` | none |
| Power-on image/black boot | CFG `0x04[6]` | drawing/JPEG commands after boot |
| Main UART CRC | CFG `0x04[5]` | no normal enable/disable opcode |
| Default orientation | CFG `0x04[1:0]` | `0x34 set_orientation()` |
| LCD physical profile | CFG `0x05` + `0x0A=0x5A` | none |
| Main UART baud | CFG `0x08..0x09` | none |
| Backlight | boot behavior via CFG | `0x30 set_backlight()` |
| Extended UART baud | none | `0x38 set_aux_baud_divisor()`, `set_aux_baudrate()` |
| JPEG/icon assets | SD-card picture/icon files | `0x22..0x29` display/cache/animation commands |
| Persistent application data | none | Data Flash through `0x31/0x32` |

## UART wire format

With the reference CFG above, normal commands use the non-CRC frame format:

```text
AA CMD DATA... CC 33 C3 3C
```

Multi-byte integer fields are encoded big-endian. The driver bounds the
command/data field before transmission and parses fragmented responses without
using payload bytes as frame delimiters.

## Runtime instruction coverage

| Opcode | T5UIC1 function | Driver API |
|---:|---|---|
| `0x00` | Handshake | `handshake()` |
| `0x01` | Clear screen | `clear()` |
| `0x02` | Point / point list | `draw_point()`, `draw_points()` |
| `0x03` | Line / polyline | `draw_line()`, `draw_polyline()` |
| `0x05` | Rectangle / fill / XOR | `draw_rectangle()` |
| `0x08` | Two-color bitmap fill | `draw_bitmap()` |
| `0x09` | Move display area | `move_area()` |
| `0x11` | Text | `draw_text()`, `draw_text_bytes()` |
| `0x14` | Native numeric variable | `draw_number()` |
| `0x21` | QR code | `draw_qr()` |
| `0x22` | Show JPEG / cache to area 0 | `show_jpeg()` |
| `0x23` | Icon library | `show_icon()` |
| `0x24` | JPEG icon from SRAM | `show_sram_jpeg()` |
| `0x25` | JPEG to virtual area 1 without display | `cache_jpeg()` |
| `0x26` | Copy virtual area 1 | `copy_cache1()` |
| `0x27` | Copy virtual area 0/1 | `copy_cache()` |
| `0x28` | Configure icon animation | `configure_animation()` |
| `0x29` | Animation enable mask | `set_animation_mask()` |
| `0x2A` | EAN-13 barcode | `draw_ean13()` |
| `0x30` | Backlight | `set_backlight()` |
| `0x31` | SRAM/Data Flash write | `write_memory()`, `write_sram()`, `write_flash()` |
| `0x32` | SRAM/Data Flash read | `read_memory()`, `read_sram()`, `read_flash()` |
| `0x33` | SRAM to picture Flash | `store_sram_as_picture()` |
| `0x34` | Display orientation | `set_orientation()` |
| `0x38` | Extended UART baud rate | `set_aux_baud_divisor()`, `set_aux_baudrate()` |
| `0x39` | Extended UART transmit | `aux_write()` |
| `0x3A` | Extended UART receive upload | `poll_aux_data()` |
| `0xFF` | CRC error report (inbound) | `poll_crc_error()` |

KlipperDWIN also retains the proven `0x3D` display-update command through
`update()` for compatibility with the Creality/mriscoc T5UIC1 implementation.

## Memory and persistence

The T5UIC1 exposes two data-memory regions to the runtime protocol:

| Region | Selector | Size | Persistence |
|---|---:|---:|---|
| SRAM | `0x5A` | 32 KiB | Volatile |
| Data Flash | `0xA5` | 16 KiB | Non-volatile |

`read_memory()` uses conservative `0x3F`-byte transactions. The T5UIC1 guide
documents an opcode `0x32` length range of `0x01..0xF0`; the current smaller
chunk is an implementation choice pending a separate low-address physical
length sweep. Writes are split into bounded packets and Data-Flash writes wait
for the panel acknowledgement instead of assuming completion.

The guide documents Data Flash as 16 KiB (`0x0000..0x3FFF`). On the reference
T5UIC1 panel, physical testing showed `0x0000..0x3FFE` is readable and writable,
while a one-byte read at `0x3FFF` receives no response and a write transaction
that spans `0x3FFF` receives no acknowledgement. KlipperDWIN therefore keeps
the documented 16 KiB physical size but exposes only `0x0000..0x3FFE` through
the Data Flash API.

Picture Flash is separate from the 16 KiB Data Flash.
`store_sram_as_picture()` uses opcode `0x33` to copy the panel's 32 KiB SRAM
image content into picture slot `0x00..0x0F`.

## Managed custom icon atlases

KlipperDWIN reserves Picture Flash IDs **14** and **15** for up to two
host-managed custom JPEG atlases. Stock assets already available through
`9.ICO` remain on the normal `0x23 show_icon()` path and are intentionally
not duplicated into these atlases.

The host manifest lives in `lcd_atlas.py`:

```python
# virtual_area: (JPEG path, reserved Picture Flash ID)
ATLAS_FILES = {
    0: ("assets/klipperdwin_atlas_0.jpg", 14),
    1: ("assets/klipperdwin_atlas_1.jpg", 15),
}

# icon_id: (virtual_area, source_x, source_y, width, height)
ICON_COORDINATES = {
    # ...
}
```

UI code does not know source coordinates, dimensions, Picture Flash IDs or
virtual-area assignments. It renders a custom asset only by ID:

```python
lcd.draw_atlas_icon(icon_id, x, y)
```

The driver resolves the coordinate table, ensures that the required atlas is
resident in virtual area 0 or 1, then emits the corresponding `0x27` copy.
If another low-level JPEG/cache operation replaces a virtual area, the driver
tracks that change and automatically restores the required atlas on the next
`draw_atlas_icon()`.

### Atlas synchronization and versioning

An active atlas is hashed on the host with SHA-256; the first 16 digest bytes,
JPEG size, Picture Flash ID and virtual-area ID form its persistent version
record. KlipperDWIN reserves Data Flash range **0x0000..0x003F** (64 bytes) for
this metadata, with magic `KDWATLS1`. The record intentionally starts at zero
and avoids the physically non-responsive `0x3FFF` boundary.

On LCD connection the driver:

1. reads the persistent atlas metadata;
2. compares it with the current host JPEG fingerprints;
3. uploads only changed JPEGs through SRAM;
4. commits each changed JPEG to its reserved Picture Flash slot with `0x33`;
5. writes the new metadata **only after all required Picture Flash writes
   succeed**.

Each successful Picture Flash write is checkpointed immediately in Data Flash
and read back for verification. If a later atlas fails, an already committed
atlas is therefore not rewritten on the next service start.

Automatic Picture Flash programming also has a process-lifetime wear guard:
the same `(Picture ID, size, digest)` is attempted at most once automatically
per KlipperDWIN process. Atlas-sync failure is non-fatal to the normal LCD UI
and does not enter the 5-second UART reconnect loop. Rendering APIs
(`draw_atlas_icon()` and `load_atlases()`) never initiate persistent Flash
writes; they require startup synchronization to have completed successfully.
A deliberate explicit `sync_atlases()` call may retry after an operator has
investigated the failure.

This means a lost acknowledgement, failed metadata write, or later atlas error
cannot cause continuous Picture Flash programming every few seconds. A true
host/service restart may make one new automatic attempt, while systemd's
existing start-rate limit remains a secondary guard.

If host and panel versions already match, no JPEG or metadata is written.

Atlas JPEGs must be complete JPEG files and fit inside the T5UIC1's 32 KiB SRAM
transfer limit. The default coordinate table is intentionally empty until the
production atlas artwork is finalized, so this infrastructure does not alter
the current UI rendering or startup traffic yet.

Virtual areas are preloaded on connection by `load_atlases()` and restored lazily
by `draw_atlas_icon()` if necessary. This target panel requires `0x22` to load
area 0; `0x25` is used only for area 1. The generic reference API's cache-index
argument must not be taken as proof that cache-only area-0 loading works on
this panel. `cache_jpeg(..., area=0)` therefore raises rather than recording a
false successful load.

On connection, `load_atlases(preserve_boot_splash=True)` sends:

1. `0x25 01 00`: load Picture Flash slot 0 into temporary cache 1.
2. `0x22 00 0E`: load Picture Flash slot 14 into area 0/display buffer.
3. `0x26`: copy the full portrait splash from cache 1 back to the display buffer.
4. Restore an active area-1 atlas, if any, using `0x25`.

No `0x3D` refresh is sent between steps 2 and 3. The splash is restored before
progress rendering refreshes the screen, while area 0 retains slot 14 for
`0x27` icon copies. Both cache areas remain exclusively driver-owned. No
Picture Flash or Data Flash writes occur in this restore sequence.


## Rendering compatibility

The complete-driver migration deliberately does **not** change the current UI
render strategy. Compatibility helpers such as `draw_integer_text()`,
`draw_scaled_float_text()` and `draw_signed_scaled_float_text()` continue to
generate the same `0x11` text rendering used before the migration.

The native `0x14` implementation is available separately as `draw_number()`.
Hardware animation, virtual display areas, QR/EAN-13, Data Flash, picture Flash
and extended-UART APIs are exposed without changing current UI behavior. They
can be adopted by the UI only after physical-panel validation.

## Sources and validation boundary

Primary protocol/configuration reference:

- DWIN, *T5UIC1 Kernel Application Guide v2.3*.
- The archived guide and T5UIC1 tools are mirrored by
  [ihrapsa/T5UIC1-DWIN-toolset](https://github.com/ihrapsa/T5UIC1-DWIN-toolset).
- Known-good Ender 3 V2 runtime behavior is cross-checked against
  [mriscoc/Ender3V2S1](https://github.com/mriscoc/Ender3V2S1).

Automated tests validate packet bytes, payload/address bounds, response parsing,
partial UART reads, acknowledgements, retries and compatibility rendering. They
cannot prove rendering behavior on every T5UIC1 kernel or asset revision.
Boot-time CFG changes and new rendering paths must be verified on the physical
panel before being made part of normal UI behavior.
