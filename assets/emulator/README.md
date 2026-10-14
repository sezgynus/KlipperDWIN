# Emulator assets

[English](README.md) · [Türkçe](README_TR.md) · [Capture guide](../../docs/ui-emulator.md)

## Choose matching resources

These files are inputs for screenshot rendering on the Pi. Enabling the emulator does not install them on the physical display or replace its fonts/icons.

| File | Use |
|---|---|
| `3.ICO` | Application icon library at slot 3; Graphite sources and semantic UI icons |
| `0T5UIC1.HZK` | Graphite ASCII glyphs; original non-ASCII banks retained |
| `0_DWIN_ASC.HZK` | Alternative DGUS ASCII font; select explicitly only when appropriate |

For a custom panel font, set `PETREL_EMULATOR_FONT` to the matching file in the service environment and restart. See [optional emulator settings](../../docs/ui-emulator.md#optional-settings). Matching resources matters when comparing a screenshot with a physical display.

## Provenance

- `0T5UIC1.HZK`: [Quint097/DWIN_Font_Tools](https://github.com/Quint097/DWIN_Font_Tools/blob/main/HZK%20Font%20Files/DWIN%20Font%20(Original)/0T5UIC1.HZK).
- `0_DWIN_ASC.HZK`: [ihrapsa/T5UIC1-DWIN-toolset](https://github.com/ihrapsa/T5UIC1-DWIN-toolset/blob/main/Dwin_Toolbox-en%2F0_DWIN_ASC.HZK).

Upstream resources retain their original provenance; Petrel does not claim authorship of these binary files.

Graphite rebuilds the ASCII glyph banks using DejaVu Sans Mono; its license is bundled in `Petrel-font-license.txt`. The remaining original banks retain the upstream provenance above.
