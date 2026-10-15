# Shared picture sources

[English](README.md) · [Türkçe](README_TR.md) · [LCD artwork](../README.md#shared-ui-artwork-page)

Put each source image here as a `.jpg` or `.jpeg`. From the repository root, run:

```bash
python tools/pack_shared_artwork.py
```

The tool creates both `assets/petrel_shared.jpg` (Picture Flash slot 1) and `shared_artwork_layout.py`. Commit the input JPEGs and both generated files together. Generation is a developer action; users receive the prepared outputs and the service uploads changed artwork automatically.

| Source filename | Generated rectangle | Generated dimensions |
|---|---|---|
| `qr.jpg` | `QR_BOX` | `QR_SIZE` |
| `nozzle-idle.jpeg` | `NOZZLE_IDLE_BOX` | `NOZZLE_IDLE_SIZE` |

Names are normalized to uppercase Python identifiers; punctuation becomes underscores, accents are transliterated, and digit-leading names receive `IMAGE_`. Names that collide after normalization or with generated metadata are rejected. Keep `qr.jpg`: Info imports its `QR_BOX`. The QR source can be regenerated from the brand artwork with `python tools/render_project_qr.py`; run the packer afterwards. Packing alone preserves every input file.

Rectangles use **portrait** coordinates `(left, top, right, bottom)`, with exclusive right/bottom edges. Dimensions are `(width, height)`. Import the constants instead of copying numeric coordinates. For `copy_cache1`, subtract 1 from right/bottom to obtain the LCD's inclusive coordinates. Adding an image makes it available in the page; UI code must still choose when and where to display it.

The portrait canvas is **272×480**; the output JPEG is stored as **480×272** for panel direction 1. Packing tries multiple MaxRects orders, bin widths and placement rules, choosing the most compact occupied rectangle. This is a deterministic heuristic, not a guarantee of the mathematical optimum. Inputs are neither resized nor rotated. Placement may change when sources change, so always use the generated constants.

Sources must fit geometrically, and the final baseline 4:2:0 JPEG must fit **32767 bytes**. Empty folders, invalid images, duplicate names, packing failures and compressed-size overflow leave the previous outputs intact. JPEG quality defaults to 100 with optimized Huffman coding; `--quality 94` explicitly selects lower quality when needed. Inspect the result and validate QR readability on the physical panel after artwork changes.

For review without replacing the shipped outputs:

```bash
python tools/pack_shared_artwork.py --output /tmp/petrel-page.jpg --layout /tmp/petrel-layout.py
```

The generated module includes the JPEG's SHA-256. The service refuses a JPEG/layout mismatch before writing to the panel. A failed output replacement rolls back the pair; the generated files should still be committed and deployed together.
