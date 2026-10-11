"""Shared panel icon-library identity for runtime and screenshot rendering."""

ICON_LIBRARY_ID = 7
ICON_LIBRARY_FILENAME = "7.ICO"

# Custom JPEG source IDs in the managed icon library.
ICON_MMU_HOME_NORMAL = 100
ICON_MMU_HOME_SELECTED = 101
ICON_FOLDER = 102
ICON_MCU = 103
ICON_MACHINE = 104
ICON_HOST = 105
ICON_SOFTWARE = 106
ICON_POWER = 107
ICON_DISPLAY_NORMAL = 108
ICON_DISPLAY_SELECTED = 109
ICON_SPOOL_EMPTY = 124
# Only the small wooden flanges vary in width, not entire spool images.
SPOOL_LEFT_FLANGES = {width: 109 + width for width in range(1, 8)}
SPOOL_RIGHT_FLANGES = {width: 116 + width for width in range(1, 8)}
