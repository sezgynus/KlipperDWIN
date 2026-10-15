# Original Creality DWIN_SET

[English](README.md) · [Türkçe](README_TR.md) · [Restore guide](../../docs/restore-stock-dwin.md)

The [`DWIN_SET/`](DWIN_SET) directory contains **unaltered binary files** from Creality's official [Ender-3 V2 `UI/DWIN_SET`](https://github.com/CrealityOfficial/Ender-3V2/tree/88a603b396d09607f4b25bf1bd1c5881092380c0/UI/DWIN_SET) at commit `88a603b396d09607f4b25bf1bd1c5881092380c0`. Each copied Git blob ID was verified against the upstream original.

| File | Original Git blob SHA-1 |
|---|---|
| `0_start.jpg` | `bc5e50be0aa4d5c5992440fc3141f28e824cc427` |
| `1_English.jpg` | `e609fa91a60afbe77bea916722ad862f68f41350` |
| `2_Chinese.jpg` | `24478e62f3776a1a21bb2bab19585117868e1f6d` |
| `9.ICO` | `500f29029e1e95dda227edc6dd8fa2537b75ac54` |
| `T5UIC1.CFG` | `267996a88f9f3b15927a89047a20ac3f5ce98ff5` |
| `T5UIC1_V20_4页面_191022.BIN` | `eac6b5ca0371c70fe58b562eedc38183739b135d` |

Creality's unrelated Windows `Thumbs.db` file was intentionally excluded. The upstream package does not include an OEM `0T5UIC1.HZK` font. These are OEM resources, **not Petrel firmware**; the upstream repository distributes its work under **GPL-3.0**. See the upstream [license](https://github.com/CrealityOfficial/Ender-3V2/blob/88a603b396d09607f4b25bf1bd1c5881092380c0/LICENSE) and Petrel's root `LICENSE`.

**Only for the original DWIN T5UIC1 LCD, not DACAI/TJC.** Read the [restore guide](../../docs/restore-stock-dwin.md) before writing the files to a microSD card. Do not combine this OEM folder with Petrel's `assets/fonts/DWIN_SET` font-only folder.
