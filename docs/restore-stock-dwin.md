# Restore original DWIN screen resources

[English](restore-stock-dwin.md) · [Türkçe](restore-stock-dwin_TR.md) · [LCD compatibility](lcd-assets.md)

> **Warning — this writes persistent LCD firmware/resources.** Use this guide **only** for the original Ender-3 V2 **DWIN T5UIC1** display. The `DWIN_SET` files must **not** be used on DACAI, TJC or other screen controllers. Disconnect power before handling the display.

## What this restores

Recent Petrel builds write a custom startup JPEG to Picture Flash slot **0** and synchronize their generated icon library **3** into Picture Flash slots **3–15** (only blocks required by the current pack are written). This improves the interface's visual consistency and drawing performance: the original icon images do not provide all the symbols, selections, animations and layout elements Petrel needs. Changed Flash blocks are uploaded over UART, and fingerprints in separate Data Flash prevent redundant updates. Print thumbnails use temporary SRAM and are not permanent replacements. The Petrel ASCII font is installed separately by SD card; Petrel does not automatically rewrite font or LCD kernel firmware.

The **original Creality Ender-3 V2 DWIN_SET** is included at [`assets/stock-dwin/DWIN_SET`](../assets/stock-dwin/DWIN_SET). It contains the OEM boot image, English/Chinese pages, icon library **9**, T5UIC1 configuration and LCD kernel. These files come from [Creality's GPL-3.0 source repository](https://github.com/CrealityOfficial/Ender-3V2/tree/88a603b396d09607f4b25bf1bd1c5881092380c0/UI/DWIN_SET); see [bundle provenance](../assets/stock-dwin/README.md).

**Limits:** This pack restores the OEM resources used by the stock display firmware; it does not promise a byte-for-byte erase of every previously written Picture Flash slot. Creality's source bundle does **not** contain an OEM `0T5UIC1.HZK` font, so a separately installed Petrel font may remain. Flashing this display pack **does not restore your printer mainboard firmware**. To use the original Creality interface, restore a compatible stock **mainboard firmware separately**.

## Restore using the LCD microSD slot

1. Finish any print, shut down the printer safely and **stop Petrel** on the host so it cannot reprogram its assets when the display reconnects:
   ```bash
   sudo systemctl disable --now Petrel.service
   ```
2. Verify the hardware is the original **DWIN T5UIC1** panel. Do not continue if it is DACAI/TJC or the model is uncertain.
3. Prepare a reliable microSD card, preferably **8 GB or less**, with an **MBR** partition table, **FAT32** filesystem and **4096-byte allocation units**.
4. Copy the **complete** [stock `DWIN_SET` folder](../assets/stock-dwin/DWIN_SET) to the **root** of the card. Its structure must be `/DWIN_SET/0_start.jpg`, `/DWIN_SET/9.ICO`, `/DWIN_SET/T5UIC1.CFG`, etc. Do **not** use Petrel's `assets/fonts/DWIN_SET` folder for this restore; it contains only a Petrel font.
5. With **power off**, access the microSD slot on the **back of the LCD module** (not the printer mainboard slot). Insert the card, reconnect the screen securely and power on. Do not disconnect wiring while powered.
6. Observe the LCD update sequence; on compatible DWIN displays the indicator typically changes **blue → orange**. Allow it to complete without interrupting power.
7. Switch off again, remove the microSD card, reassemble the display and power on normally. Check the boot image and stock icons with the matching mainboard firmware.

If the update does not complete, check the card format, root-folder name and panel identity; try a different card rather than flashing an unrelated display pack. See [mriscoc's DWIN update procedure](https://github.com/mriscoc/Ender3V2S1/wiki/How-to-update-the-display).

## Returning to Petrel later

The Petrel service **must remain stopped** while you want to retain the OEM resources. Re-enabling Petrel will manage the boot image and library **3** again. If the SD update replaced Flash blocks while Petrel's Data Flash fingerprints survived, an ordinary launch can incorrectly assume some icons or the boot image are already present. With the service stopped, use [the explicit icon reload procedure](../assets/README.md#after-reinstalling-panel-resources) before resuming Petrel; verify the boot image on the physical LCD as well. Reinstall the [Petrel LCD font](lcd-assets.md#lcd-font) if required. Do not assume that icon reload also forces boot image slot 0.

The LCD microSD update changes the **screen**, not the Raspberry Pi installation or the printer mainboard.
