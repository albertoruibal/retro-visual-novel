# Playing the games

Every target runs the same story engine, so scenes, options, highlighted words and items behave the same way. What
changes is how you move, confirm and open the inventory/action list. The built games are listed under **Outputs** in
[the README](../README.md).

The text of a scene is above the options, and an option that is hidden by a flag is simply not shown. Highlighted
`{{words}}` are one-shot: selecting one sets its flag and redraws the scene. A system with `menu: popup` enabled in
`# Systems` puts its options and held items in a dialog instead of the pinned list (the Master System, Game Boy
Color, Commodore 64 and NES always do this).

## Controls at a glance

| Target | Move / scroll | Confirm | Options & items |
|---|---|---|---|
| ZX Spectrum 128K | Cursor keys or W/A/S/D | Enter | Bottom inventory row, or `SPACE` dialog |
| ZX Spectrum Next | Cursor keys, W/A/S/D, arrow keys or joystick | Enter or fire | Bottom inventory row, or `SPACE` dialog |
| Amstrad CPC | Cursor/WASD/8/2/4/6/joystick | Enter/Space/fire | Pinned/inventory, or `SPACE` dialog |
| MSX2 | Cursor/WASD/8/2/4/6/joystick | Enter/Space/fire | Pinned options/inventory, or `SPACE`/button 2 |
| Sega Master System | D-pad | Button 2 | Button 1 opens/closes the action dialog |
| Nintendo Game Boy Color | D-pad | A or Start | B opens/closes the action dialog |
| Commodore 64 | Cursor keys or W/A/S/D | Return | `SPACE` opens/closes the action dialog |
| NES | D-pad | A | B or Select opens/closes the action dialog |
| Oric Atmos | Cursor keys or W/A/S/D | Return | Bottom inventory row, or `SPACE` dialog |
| Web player | Tap/click or `Up`/`Down` | Tap/click or `Enter`/`Space` | Bottom inventory bar; tap an item |

The editor's **Emulator** tab runs the ZX Spectrum in JSSpeccy, the C64 in VICE, the NES in FCEUmm and the Oric Atmos
in Oricutron. On a phone or tablet the Spectrum emulator shows an on-screen pad below the picture: arrows move,
`ENTER` confirms, `SPACE` opens the action dialog when the game uses it, and `P` toggles music, so a hardware
keyboard is not needed. Click the Oric picture first so the canvas takes keyboard focus; the cursor keys, `RETURN` and
`SPACE` are forwarded to the emulated machine. Click the C64 picture first; the page
forwards the physical keyboard (cursor keys/`W` `A` `S` `D`, `RETURN`, `SPACE`). For the NES, EmulatorJS's defaults
are arrows = D-pad, `Z` = A (confirm), `X` = B (open/close the dialog), `V` = Select and `Enter` = Start; remap them in
its Control Settings.

## Web player

The exported web player and the editor's Emulator tab (which auto-exports and previews it) use the same
mobile-first novel. Tap or
click an option, a highlighted word or an inventory item. `Up`/`Down` move focus, `Enter`/`Space` activate the
focused control, and `Escape` closes the item screen. The inventory bar stays at the bottom on phones, and
**Restart** resets the story. Use the **Sound: on/off** button to mute the music; browsers may wait for the first
click or key press before starting it. The player lists only the systems ticked in the Systems tab. When a native
ZX Spectrum entry is selected on a touch device, the same on-screen pad (arrows/`ENTER`/`SPACE`/`P`) appears below the
picture. The editor's top-bar **Export player** button re-exports and reloads the preview. See
[the web player](web-runtime.md) for export and implementation details.

## ZX Spectrum 128K

- **Movement:** the cursor keys (CAPS SHIFT + `5`/`6`/`7`/`8`; the bare number keys also work) or `W` `A` `S` `D`.
  `UP`/`DOWN` move between the options; `LEFT`/`RIGHT` move between highlighted words. With the pop-up dialog,
  `UP`/`DOWN` scroll overflowing scene text and `LEFT`/`RIGHT` move between words.
- **Confirm:** `ENTER` selects the highlighted word or option.
- **Inventory:** `DOWN` from the last option moves the cursor to the inventory row 23. `LEFT`/`RIGHT` (or `A`/`D`)
  step through the held items, `UP` returns to the options, and `ENTER` opens the selected item. On the item screen
  `UP`/`DOWN` move between the item's options, **Drop** and **Back**, and `ENTER` confirms.
- A scene or item option with a `msg` line first shows that message in a popup over the text pane. A message longer
  than the pane scrolls with `UP`/`DOWN` (`^`/`v` mark the overflow); any other key dismisses it, as do `UP` at the
  top or `DOWN` at the bottom. Then the option's effects and target run as normal.
- **Pop-up dialog:** with `## zx128 menu: popup` (or `## zx48 menu: popup`), `SPACE` opens and closes an action dialog
  instead; it lists
  the scene options first and then the held items (prefixed `*`), with `UP`/`DOWN` to move and `ENTER` to choose.
  The text then uses every row below the art and there is no permanent inventory row; overflowing scene text and
  item descriptions scroll. On an item screen, `UP`/`DOWN` scroll a long description while the cursor is on the
  first entry.
- **Music:** press `P` to pause/play the AY music. Music is set per scene and resumes when unmuted.
- **Boot password:** if the game sets one, type it at the boot screen and press `ENTER`. `DELETE` (or Backspace)
  erases the last character.
- Without the pop-up dialog the text pane is fixed: keep a scene's wrapped lines (and options) within the rows below
  the art band. With the dialog, long text scrolls.

The **ZX Spectrum 48K** build uses the same controls. Its picture is a 1-bit dithered mono band by default, or
classic 8x8 attribute colour when Black and white is off (no NIRVANA+), and there is no music; everything else,
including the pop-up dialog and the row-23 inventory, behaves as on 128K.

## ZX Spectrum Next

The Next build uses the ZX layout and controls: cursor keys, `W`/`A`/`S`/`D`, the Next's own arrow keys or the joystick
(its fire button also confirms), `ENTER` to confirm, the row-23 inventory band (or the `SPACE` dialog with
`menu: popup`), and `P` to pause/resume music. In ZEsarUX the PC arrow keys are fed to the emulated Kempston joystick,
which the Next build reads as well. Layer 2 supplies the 256-colour picture band; the title, text and inventory remain
on the ULA.

Without a bundled Next emulator, run it with ZEsarUX:

    python3 tools/build.py run demo-game next

## Amstrad CPC 6128 / 464

Both CPC joystick ports work; the web emulator maps its arrow keys to port 0. The controls are identical on the
6128 and 464 builds. The 464 build is a 64K disk image (it needs a disk drive, e.g. the DDI-1) and streams its
pictures from the disk, so the first scene may pause briefly while a new art loads.

- **Movement:** cursor keys, `W` `A` `S` `D`, the numeric cursors `8`/`2`/`4`/`6`, or the joystick.
- **Confirm:** `ENTER` or the joystick fire button when the dialog is enabled; with pinned options `SPACE` also
  confirms.
- **Words:** `LEFT`/`RIGHT` move between highlighted words.
- **Default (pinned):** the options stay pinned below the text and row 24 is the inventory band. `DOWN` from the
  last option enters it, `LEFT`/`RIGHT` step through the items, `UP` returns and `ENTER` opens the selected item.
  `LEFT`/`RIGHT` also scroll a long scene body when it has no highlighted words.
- **`menu: popup`:** the text uses every row below the art. `SPACE` opens and closes an action dialog listing the
  scene options first and then the held items (prefixed `*`); `UP`/`DOWN` move and scroll it, `ENTER`/fire confirms,
  and `SPACE` closes it. A long scene body scrolls with `UP`/`DOWN` (or `LEFT`/`RIGHT` when the scene has no
  words). On a long item description, `UP`/`DOWN` scroll the description while the cursor is on the first entry.

## MSX2

- **Movement:** cursor keys, `W` `A` `S` `D`, the numeric cursors `8`/`2`/`4`/`6`, or the joystick.
- **Confirm:** `ENTER` or the joystick fire button when the dialog is enabled; with pinned options `SPACE` also
  confirms.
- **Words:** `LEFT`/`RIGHT` move between highlighted words.
- **Options and inventory:** by default the options are pinned below the text and row 23 is the inventory band.
  `DOWN` from the last option enters it, `LEFT`/`RIGHT` step through the held items, `UP` returns to the options, and
  `ENTER` opens the selected item. On the item screen `UP`/`DOWN` move between the entries, and while the cursor is
  on the first entry they scroll a long description. With `## msx2 menu: popup`, `SPACE` or joystick button 2
  opens and closes the action dialog instead, and the text may use row 23.
- The text pane never scrolls, so a scene's text (and options on the pinned layout) must fit the rows left below the
  art band.

## Sega Master System

- **D-pad:** `UP`/`DOWN` scroll a long scene body, or move between highlighted words when the text fits.
  `LEFT`/`RIGHT` move between highlighted words (or scroll when the scene has none).
- **Button 2:** confirm the highlighted word or option.
- **Button 1:** open and close the action dialog. It lists the scene options first and then the held items (prefixed
  `*`); the D-pad moves and scrolls the list, button 2 confirms and button 1 closes it.
- On a long item description, `UP`/`DOWN` scroll the description while the cursor is on the first entry. There is no
  permanent inventory row.
- **Music:** the console's `PAUSE` button pauses/resumes the converted SN76489 soundtrack.

## Nintendo Game Boy Color

- **D-pad:** `UP`/`DOWN` scroll a long scene body, or move between highlighted words when the text fits.
  `LEFT`/`RIGHT` move between highlighted words (or scroll when the scene has none).
- **A or Start:** confirm the highlighted word or option.
- **B:** open and close the action dialog. It lists the scene options first and then the held items (prefixed `*`);
  the D-pad moves and scrolls the list, `A`/`Start` confirms and `B` closes it.
- On a long item description, `UP`/`DOWN` scroll the description while the cursor is on the first entry. There is no
  permanent inventory row. On a CGB the configured `highlight_ink:` colours the selection; the `>` marker remains so
  the same cartridge is still usable on a monochrome Game Boy.
- **Music:** `Select` pauses/resumes the converted Game Boy APU soundtrack.
- The Game Boy Color build has no boot-password screen.

## Commodore 64

- **Movement:** cursor keys or `W` `A` `S` `D`; `RETURN` confirms.
- **Options and items:** `SPACE` opens and closes the action dialog. It lists the scene options first and then the
  held items (prefixed `*`); the cursor keys move and scroll the list and `RETURN` confirms. On a long item description,
  `UP`/`DOWN` scroll the description while the cursor is on the first entry.
- **Music:** not implemented yet on the C64 build.
- There is no boot-password screen.

## Oric Atmos

- **Movement:** cursor keys or `W` `A` `S` `D`; `RETURN` confirms.
- **Options and items:** with the default pinned layout, the options sit at the bottom of the text pane and held items
  on the row-24 inventory band; press `DOWN` off the last option to enter the band, `UP` off the first item to return,
  and `RETURN` to open the selected item. With `## oric menu: popup`, `SPACE` opens and closes the action dialog: it
  lists the scene options first and then the held items (prefixed `*`), the cursor keys move and scroll the list, and
  `RETURN` confirms. On a long item description, `UP`/`DOWN` scroll the description while the cursor is on the first
  entry.
- The picture is a monochrome HIRES band; selection uses inverse video. Text is 40 columns.
- **Music:** not implemented yet on the Oric Atmos build.
- There is no boot-password screen.

## NES

- **Movement:** D-pad; `A` confirms.
- **Options and items:** `B` or `SELECT` opens and closes the action dialog. It lists the scene options first and then
  the held items (prefixed `*`); the D-pad moves and scrolls the list and `A` confirms. On a long item description,
  `UP`/`DOWN` scroll the description while the cursor is on the first entry.
- **Music:** Start toggles music. PT3 songs are converted to NES APU register streams at build time; cursor moves,
  confirmations, backing out, item pickups/drops and blocked moves also play short UI sound effects.
- There is no boot-password screen. The build targets MMC1 cartridges with 8KB battery WRAM, so use the editor's
  Emulator tab, a compatible emulator (FCEUX, Mesen, Nestopia) or a flash cart.

## Other notes

- Items can have their own options; choosing one applies its effects and returns to the current scene. **Drop**
  removes the item and frees its slot.
- A game's `# Game carry:` cap limits how many items are held; when the pack is full, `pick` options are hidden, so
  dropping an item is how you make room.
- On the targets with a permanent inventory row (ZX, MSX2, CPC by default) the item screen also has **Drop** and
  **Back** entries. On the dialog targets (SMS, Game Boy Color, Commodore 64, NES, and any system with
  `menu: popup`) the action dialog is the only way in.
