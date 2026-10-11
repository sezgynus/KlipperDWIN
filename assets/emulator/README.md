# Emulator assets

[English](README.md) · [Türkçe](README_TR.md) · [Capture guide](../../docs/ui-emulator.md)

## Choose matching resources

These files are inputs for screenshot rendering on the Pi. Enabling the emulator does not install them on the physical display or replace its fonts/icons.

| File | Use |
|---|---|
| `7.ICO` | Application icon library at slot 7; stock icons plus About variants 92/93 |
| `0T5UIC1.HZK` | Default original T5UIC1 font |
| `0_DWIN_ASC.HZK` | Alternative DGUS ASCII font; select explicitly only when appropriate |

For a custom panel font, set `DWIN_EMULATOR_FONT` to the matching file in the service environment and restart. See [optional emulator settings](../../docs/ui-emulator.md#optional-settings). Matching resources matters when comparing a screenshot with a physical display.

## Provenance

- `0T5UIC1.HZK`: [Quint097/DWIN_Font_Tools](https://github.com/Quint097/DWIN_Font_Tools/blob/main/HZK%20Font%20Files/DWIN%20Font%20(Original)/0T5UIC1.HZK).
- `0_DWIN_ASC.HZK`: [ihrapsa/T5UIC1-DWIN-toolset](https://github.com/ihrapsa/T5UIC1-DWIN-toolset/blob/main/Dwin_Toolbox-en%2F0_DWIN_ASC.HZK).

Upstream resources retain their original provenance; KlipperDWIN does not claim authorship of these binary files.
