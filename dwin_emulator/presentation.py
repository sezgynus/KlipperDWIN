"""Optional screenshot presentation; never modifies the live framebuffer."""
from pathlib import Path
from PIL import Image

FRAME = Path(__file__).resolve().parents[1] / 'assets/emulator/display-frame.png'
SCREEN_ORIGIN = (128, 122)


def with_frame(screen):
    """Composite the native 272×480 pixels without resampling the UI."""
    if screen.size != (272, 480):
        raise ValueError('Expected a 272×480 panel snapshot')
    with Image.open(FRAME) as source:
        result = source.convert('RGBA').resize((528, 900), Image.Resampling.LANCZOS)
    result.paste(screen.convert('RGBA'), SCREEN_ORIGIN)
    return result
