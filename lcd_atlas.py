"""Host-side custom icon-atlas manifest for KlipperDWIN.

The UI must not depend on atlas coordinates or virtual-area selection. Add or
move custom static icons only by updating ICON_COORDINATES and the corresponding
JPEG file. Stock icons already present in 9.ICO do not belong here.

T5UIC1 JPEG files are stored at the physical 480x272 panel resolution, while
source rectangles below use the runtime portrait virtual-area coordinate space
(272x480) after direction=1 is applied.
"""

# KlipperDWIN custom icon IDs. UI code imports these symbolic IDs and calls
# lcd.draw_atlas_icon(icon_id, x, y); it never sees atlas coordinates.
ICON_MMU_HOME_NORMAL = 0x0100
ICON_MMU_HOME_SELECTED = 0x0101
ICON_FOLDER = 0x0102
ICON_MCU = 0x0103
ICON_MACHINE = 0x0104
ICON_HOST = 0x0105
ICON_SOFTWARE = 0x0106
ICON_POWER = 0x0107
ICON_DISPLAY = 0x0108

# virtual_area: (repo-relative JPEG path, reserved Picture Flash ID)
ATLAS_FILES = {
    0: ("assets/klipperdwin_atlas_0.jpg", 14),
    1: ("assets/klipperdwin_atlas_1.jpg", 15),
}

# icon_id: (virtual_area, source_x, source_y, width, height)
#
# Coordinates are in the runtime 272x480 virtual-area orientation.
# Atlas 1 is deliberately empty/reserved for future custom assets.
ICON_COORDINATES = {
    ICON_MMU_HOME_NORMAL: (0, 0, 0, 77, 47),
    ICON_MMU_HOME_SELECTED: (0, 80, 0, 77, 47),
    ICON_FOLDER: (0, 160, 0, 20, 18),
    ICON_MCU: (0, 192, 0, 20, 20),
    ICON_MACHINE: (0, 224, 0, 20, 20),
    ICON_HOST: (0, 160, 32, 20, 20),
    ICON_SOFTWARE: (0, 192, 32, 20, 20),
    ICON_POWER: (0, 224, 32, 20, 20),
    ICON_DISPLAY: (0, 0, 48, 52, 64),
}
