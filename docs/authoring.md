# Authoring

The authoring format for a game's art, scenes, items and songs.

A game is a single folder. `game.md` at its root holds the whole game — settings, art, items and the story — and the
folder's `assets/` tree holds the binary side: art images under `assets/art/<id>/`, reference images under
`assets/refs/<id>/`, PT3 music under `assets/music/<id>.pt3`. The editor edits `game.md` (structured tabs plus a raw
Source tab) and the build reads it; both go through the same parser, `tools/scenefile.py`, so they can never disagree
about the format. Every save re-serialises the file canonically and keeps a `game.md.bak` beside it.

The file is ordinary Markdown. Each top-level section is a `# Heading` and each entry inside it is a `## <id>`
subtitle; prose and indented example blocks are ignored wherever they appear. An id is a short ASCII token
(letters, digits, `-` and `_`, starting with a letter or digit) that other entries use to refer to it — a scene's
`art:`, an option's target, an art's `refs:`, a `pick`. There are six section kinds:

| Section | What it holds |
|---|---|
| `# Game` | once, at the top: story metadata, declarations and defaults |
| `# Systems` | one `## <id>` block per build system and that system's options |
| `# Art` | one `## <id>` block per generated image |
| `# References` | optional: reusable image-model references |
| `# Items` | optional: display names, descriptions and options for inventory items |
| `# Scenes` | the story itself, in story order; the first block is scene 0, the start |

Every scene must be reachable from the first scene, and every scene's `art:` must name an existing art. The editor
validates both (and everything else in this document) and refuses to save a broken file, reporting each problem with
the line it came from.

## Game settings

`# Game` appears once, at the top. Two settings are effectively required — `title:` names the game in the editor and
in the build — and the rest are optional: a line not present means a sensible default, and defaults that every art
inherits sit here so you write each art's own settings only when it differs.

    # Game
    title: <game title>              # shown by the editor / build
    prompt: <common prompt>          # prefixed to every art prompt
        <continuation line>          # 4-space indent keeps the line break
    negative_prompt: <what to avoid> # sent as the image model's negative prompt
    start: <item, ...>               # inventory held before the first scene
    flags: <flag, ...>               # names that exist before any use
    items: <item, ...>               # items that exist before any use
    songs: <id, ...>                 # PT3 songs; each needs assets/music/<id>.pt3
    music: off|<song-id>|on          # default song (off if absent)
    match: rgb|perceptual            # colour-distance metric
    palette: none|spectrum|adaptive  # pre-reduce the source
    palette_colors: <n>              # colours for palette: adaptive (16)
    saturation/contrast/brightness/gamma: <1.0>   # source adjustments
    password: <word>                 # boot screen before the first scene
    password_label: <text>           # prompt line above the password input
    popup_hint: <text>               # dismiss prompt on msg popups (default "Press a key")
    inventory_drop: <text>           # item screen's Drop entry label (default "Drop")
    inventory_back: <text>           # item screen's Back entry label (default "Back")
    text_ink: <colour>               # body/options/unselected-item colour
    highlight_ink: <colour>          # selection/word colour
    text_bg: <colour>                # text background/paper (default black)
    carry: <n>                       # max items carried (0 = unlimited)
    seed/steps/cfg: <defaults for every art>
    width/height: <base output size> # `size:` is a square fallback
    hires: off|2x|3x|4x              # high-res second pass (output is width*scale)
    hires_steps: <n>                 # second-pass steps (default 20)
    hires_denoise: <0.4>             # second-pass denoise (default 0.4)
    refine_denoise: <0.45>           # strength of the Art tab's Refine 2x

### Declarations

`start:`, `flags:` and `items:` are comma-separated lists of names. `start:` lists inventory items the player holds
before the first scene (they are marked set from the beginning). `flags:` and `items:` declare names up front so an
`if`, `pick` or `set` can reference them before they are first assigned; a name used with `pick`/`leave` (or listed in
`items:`/`start:`) is an inventory item, a name used with `set`/`unset` (or listed in `flags:`) is a flag. Names are
unique across both kinds. A condition never *creates* a name — see [Flags and inventory](#flags-and-inventory).

`songs:` declares the game's PT3 songs; each id needs a module at `assets/music/<id>.pt3` (at most 4158 bytes; the
editor and the build reject larger modules). See [Songs](#songs).

### The image prompt

`prompt:` is the style part of every image prompt. The generator sends "<game prompt>, <art prompt>" to the model, so
this holds the shared look (the current games ask for bright, saturated pixel art) and each art writes only its
subject. Keep dark gradients, lettering and fine textures out of it: the Spectrum band has just two colours per 8x2
cell, and dark blends mush out.

A prompt value may run over several lines. Write the first line after `prompt:` and continue with 4-space-indented
lines: each one keeps its line break. A 2-space-indented line is a *layout* wrap — it rejoins the previous line with a
space. The editor re-wraps long prompt lines itself at save time purely to keep lines within 120 columns, so how the
line wraps in the file never changes the text sent to the model.

`negative_prompt:` is optional and sent as the model's negative prompt; keep it to quality terms (blurry, artifacts,
deformed). It uses the same continuation rules.

### Generation quality

`seed:`, `steps:` and `cfg:` seed and tune the diffusion call (35 steps and cfg 6 by default); `width:`/`height:` set
the base output size, 512x256 by default (a square `size:` is accepted for old games). `hires:` adds a second
txt2img pass at `width`x`height` times the scale (2x default off), its own `hires_steps:` (20) and `hires_denoise:`
(0.4), and saves the enlarged PNG. The Art tab's **Refine 2x** is separate: it runs img2img on the chosen image at 2x
so its composition is preserved, and `refine_denoise:` (0.45) sets that pass's strength. Every art and reference can
override `seed`/`steps`/`cfg`/`width`/`height` with its own lines.

### Converting art to the Spectrum

The conversion from a source PNG to the 256-wide art band happens at build time, and these settings bake into its
result, so the engine carries no state. Each is a `# Game` default that any art may override (dithering is chosen per
build system instead — see [Build systems](#build-systems)):

- `match:` picks the distance metric used to pick colours: `rgb` (default) or `perceptual`, a redmean approximation
  that weighs hues the way the eye does.
- `palette:` pre-reduces the source before the cell search: `none`, `spectrum` (snap to the 16 hardware colours) or
  `adaptive` (median-cut to `palette_colors:` colours, 16 by default).
- `saturation:`, `contrast:`, `brightness:` and `gamma:` adjust the scaled source before quantising (1.0 =
  unchanged). Boost `saturation:` when muted AI output lands far from the Spectrum's flat palette.

### Text and colours

`text_ink:` (dim white) renders body text, option labels and unselected inventory names; `highlight_ink:` (green)
renders the cursor-selected option and every selectable word. `text_bg:` (black) sets the text background/paper behind
all text. Values are `black blue red magenta green cyan yellow white`, each optionally prefixed `dim_`.
`word_sel_ink:` is the old spelling of `highlight_ink:` and is read and rewritten on save. All three live on the Game
tab's **Text colours** card. CPC, SMS, MSX2, Game Boy Color and ZX snap the tokens to their hardware palettes.
CPC (Modes 0/2)/SMS/MSX2 bake them into every art palette's reserved entries (the picture may use those colours too);
Game Boy Color uses dedicated text palettes 6/7, so the picture never competes with them. **CPC Mode 1 is the
exception: it is a monochrome screen, so it ignores `text_bg:`, `text_ink:` and `highlight_ink:`** and draws picture
and text from one black/grey/white ramp (the `>` cursor still marks the selection). Text keeps the author's colours
on every colour target. On ZX the art band is unaffected by `text_bg:`, and a cell has one BRIGHT bit: the background
under text follows the text ink's brightness, while empty cells use the background's own brightness.

`inventory_drop:` and `inventory_back:` set the item screen's two entry labels; blank keeps the built-in default.
They, `password_label:`, `popup_hint:` and item display names are printed straight into the text band: keep them at
most 62 columns (item names 58) and printable ASCII; the usual accented-letter mapping applies.

### The boot password

`password:` adds a boot screen shown once before the first scene: it prints the game's `title:` and asks the player
to type the word. The entry is case-insensitive and must match in length; a wrong answer prints an error and loops.
Keep the word ASCII, at most 16 characters, with no spaces, and it needs a `title:` to display. `password_label:`
overrides the prompt line above the input ("Enter the password:" by default).

## Build systems

`# Systems` selects what a build produces. Each `## <system-id>` block selects that system and holds its options:

    # Systems
    ## zx128
    art_rows: 10            # art band rows, even (default 10)
    margin: 1               # optional: inset the picture by N 8x8 cells
    dither: bayer4          # optional, per system (default off)
    menu: popup             # optional: options/items in a SPACE dialog
    title_ink: text         # optional: scene/item title colour (default: text_ink)
    ## zx48
    art_rows: 10            # shares the 128K band; monochrome, no music on 48K
    dither: bayer2          # full list; off becomes bayer2 on this 1-bit target
    menu: popup             # optional: options/items in a SPACE dialog
    ## next
    art_rows: 10            # even 8..16 (default 10); Layer 2 256-colour band
    dither: floyd           # off|floyd only
    menu: popup             # optional: options/items in a SPACE dialog
    title_ink: text         # optional: scene/item title colour
    ## sms
    art_rows: 12            # default 12; always uses the action dialog
    dither: floyd           # off|floyd only
    ## cpc
    mode: 1                 # video mode 0|1|2 (default 1)
    columns: 32             # text columns 32|40|62 (default 32)
    art_rows: 12            # default 12; 14/16 need mode 2
    dither: off             # off|floyd in modes 0/2; mode 1 always dithers
    menu: popup             # optional: options/items in a SPACE dialog
    ## cpc464
    mode: 1                 # same mode/columns/art_rows options as cpc
    columns: 32
    art_rows: 8             # default 8; art is streamed from the disk
    dither: off             # off|floyd in modes 0/2; mode 1 always dithers
    menu: popup             # optional: options/items in a SPACE dialog
    ## msx2
    columns: 64             # text columns 64|80 (default 64)
    art_rows: 12            # default 12
    dither: floyd           # off|floyd only
    menu: popup             # optional: options/items in a SPACE/button-2 dialog
    ## gb
    art_rows: 8             # 8 (default 8); Game Boy Color action dialog
    dither: floyd           # off|floyd only
    ## c64
    art_rows: 8             # 8|10|12 (default 8); C64 action dialog
    dither: floyd           # off|floyd only
    ## nes
    art_rows: 10            # 8|10|12 (default 10); NES action dialog
    dither: floyd           # off|floyd only
    ## oric
    art_rows: 8             # 8|10|12 (default 8)
    dither: bayer2          # full list; off becomes bayer2 on this 1-bit target
    menu: popup             # optional: options/items in a SPACE dialog
    ## web
                            # builds <game-folder>/web/ (no native binary)

A build compiles the selected systems in the system-list display order (ZX 128K, ZX 48K, Next, CPC 6128, CPC 464,
MSX2, Commodore 64, Oric, SMS, NES, Game Boy Color, Web); each system's log is separated
by a `==== name [id] ====` banner and, where the target supports it, a playable artifact lands in the game folder
(`<slug>.tap`, `.sna`, `<slug>-48k.tap`, `.nex`, `.sms`, `.dsk`, `<slug>-cpc464.dsk`, `.rom`, `.gbc`, `.prg`,
`.nes`, `<slug>-oric.tap`, and the `<game-folder>/web/` player for `## web`). An absent `# Systems`
means the legacy `targets:` list in `# Game`, or the 128K ZX target when that is absent too. Old hand-written
`<target>_<option>` lines in `# Game` (and the old `## zx art_lines:` spelling) are still read and are rewritten into
this section on save; `## zx` is read as an alias for `## zx128`. The editor's **Systems** tab edits the selection with
one second-level sub-tab per platform.

`art_rows:` sets the ZX art band height (shared by `zx128` and `zx48`) in 8px character rows, so it is the single most
content-visible setting: rows
1..`art_rows` carry the picture (NIRVANA+ on 128K, Layer 2 on Next, dithered monochrome on 48K), the scene title renders on
row 0 above it, scene text and options occupy rows `art_rows+1..22`, and the inventory band lives on row 23. Even
numbers only — one NIRVANA+ tile is 16px = 2 rows — and 8..16, default 10 (the classic 256x80 band). A taller band
races more of the screen for the picture and leaves less room for text; see [Screen budgets](#screen-budgets).

`menu: popup` (ZX, CPC, MSX2 and Oric; default `inline`) moves the scene options and held items out of the text band
and into the action dialog: `SPACE` on ZX, CPC and Oric, and `SPACE` or joystick button 2 on MSX2. The scene text then
owns every row below the art (rows `art_rows+1..23` on ZX/MSX2, and rows `art_rows+1..24` on Oric) and the permanent
inventory row disappears. The dialog is **always** used on the Master System, Game Boy Color, Commodore 64 and NES,
which have no pinned-option layout. The editor's **Systems** tab sets this per system.

`title_ink:` (ZX only; default `text`) colours the scene title on row 0 and the item screen's title. `text` follows
the Game tab's `text_ink:`; any colour token from the [text colours](#game-settings) — `black`…`white` for the bright
variant or `dim_black`…`dim_white` — selects an exact Spectrum ink. The boot password screen's game title uses the
same colour.

`dither:` (default `off`) picks how each pixel chooses between its cell's colours, per build system. The ZX 128K/48K,
CPC and Oric targets accept the full list: `off` snaps to the nearest, `bayer2`/`bayer4`/`bayer8` are ordered matrices
from coarsest to finest, `noise` is plain grain, and `floyd`, `atkinson`, `jarvis`, `stucki` and `sierra` are
error-diffusion kernels (jarvis smoothest, atkinson highest contrast). The other targets accept `off` or `floyd`
(Floyd-Steinberg). Monochrome targets cannot honour `off` (a hard threshold would leave only black and white), so
`zx48` and `oric` substitute a 2x2 Bayer dither, and CPC Mode 1 substitutes a 4x4 Bayer dither for its
black/grey/white ramp. Set
it in each system's block so one game can use an ordered pattern on ZX and Floyd-Steinberg where the palette is
richer. Older files with a single `# Game dither:` line migrate it to each selected system on load; a per-art
`dither:` is dropped, because art no longer owns that setting.

`margin:` (default `0`) adds a blank border on the left and right sides of the art band: `1` is one 8x8 cell (8
pixels) per side. The whole picture is scaled down uniformly to the narrower inner width and centred, so its aspect
ratio is preserved; the small vertical remainder is background, not a top/bottom margin. The border uses the game's
`text_bg:` colour. Because the picture shrinks, a margin can only reduce the number of art tiles. A too-large value is
clamped so at least one pixel of picture remains. Like `dither:`, it is a per-system setting with no per-art override;
the Art tab's previews follow the Systems-tab control before a save and show the scaled picture inside the margins
without the blank border.

## Art

`# Art` declares the game's images. One `## <id>` block per art:

    # Art
    ## hall
    prompt: A grand hall with a marble staircase
    image: gen-1734289102000.png    # the chosen candidate (default: newest)
    refs: boat captain              # reference images to condition on
    crop: 12 0 76 100               # source rect, percent of the source
    seed: 41                        # optional overrides of the # Game defaults

The id is what a scene's `art:` names, and many scenes may share one art — reuse it rather than packing near-duplicates.

### Candidates

Every generation or upload writes a *new* PNG into `assets/art/<id>/` named `<action>-<epoch>.png` — `gen-` or
`up-` — so nothing is overwritten and earlier versions stay available. `image:` names the candidate
the build and previews use; when it is absent the newest PNG in the folder wins. The Art tab's picker shows all
candidates and picks among them; its × deletes a candidate and repoints `image:` to the newest remaining file. A
legacy flat `assets/gen/art_<id>.png` is still found when the folder is missing.

### Crop

`crop: <x> <y> <w> <h>` is the source rectangle, in percent of the source, that maps onto the art band. Absent means
the centred band-aspect window: the whole frame for a source that already matches the band's shape, otherwise a
full-width or full-height strip. The Art tab overlays a resizable box on the Original image (it always keeps the
band's aspect, so nothing distorts; dragging moves it, dragging its corners resizes it) and the previews refresh when
the drag is released. A stored crop whose aspect no longer suits the band — say after `art_rows:` changes — is
re-fitted and re-saved when the art is next shown.

### Conversion overrides

Each art may override any of the `# Game` conversion defaults — `match:`, `palette:`, `palette_colors:`,
`saturation:`, `contrast:`, `brightness:`, `gamma:` — plus the generation settings (`crop:` aside, they behave exactly
as described above). Dithering has no per-art override; it belongs to each build system. Write a line only when the art
differs from the game default; the serialiser drops lines that would just repeat it.

## References

`# References` holds images that other prompts are conditioned on, so a recurring design — a boat, a van, a
character — stays consistent across scenes:

    # References
    ## boat
    prompt: A small wooden fishing boat, side view

    # Art
    ## dock
    prompt: The boat moored at a wooden jetty
    refs: boat

A reference is generated on its own from its prompt into `assets/refs/<id>/` (same candidate rules as art) and is
*never* packed into the game — generation-only. `refs:` lists the reference ids an art should use; the generator sends
their chosen images alongside the prompt. It also appends a Qwen-Image reference clause automatically: `keep the same
design as in the reference image` for one reference, or `keep the same designs as in image 1, image 2[, ...]` for
several (in `refs:` order). Write the prompt as the new scene and let that clause carry the “like the reference”
instruction; do not repeat it by hand. Regenerating an art re-renders its references first, so the art always
conditions on the current versions; a full **Regenerate images** run re-renders every declared reference once, then
the arts. Reordering the reference rows in the editor sidebar rewrites the `# References` block order, which sets the
list order and the order references are rendered during a full regeneration.

## Songs

Music is declared, not generated: `# Game songs:` lists the ids and each id is backed by a PT3 module at
`assets/music/<id>.pt3` (at most 4158 bytes; the AY targets reserve the largest module in a resident player buffer, so
oversized modules are rejected). `music: <id>` on `# Game` names the default song, `off` stops it, `on` selects the
game default, and a scene's `music:` overrides the game default for that scene — including `off` to stop music there.
The player only restarts when the chosen song actually changes, so adjacent scenes with the same song play
continuously. PT3 plays directly on the ZX, ZX Next, CPC 6128/464 and MSX2 (all AY-compatible). The Master System build
converts it to an SN76489 PSG stream and the Game Boy Color build to a Game Boy APU register stream at build time.
The Commodore 64, NES and Oric Atmos builds currently ignore songs; they still build when `songs:`/`music:` are present.

The Music tab converts into `assets/music/`: **Convert MIDI → PT3** keeps the uploaded source as `<id>.mid` next to
the module, so a re-conversion with a different cut or style does not need a re-upload.

## Scenes

`# Scenes` holds the story, top to bottom, in story order; the first `## <id>` block is scene 0, where the game
starts. (Reordering blocks in the editor's sidebar renumbers nothing visible — references are by name — but the
first block is still the start.) Each block:

    # Scenes
    ## hall
    name: The Grand Hall        # optional on-screen title (defaults to the id)
    art: hall                   # which art to draw
    ending: won                 # optional; sets the flag when reached
    music: theme                # optional; overrides the # Game default
    text:                       # scene body, up to 8 logical lines per target (wrapped)
      Dust hangs in the light.
      The {{staircase}} spirals upward.
    opt: Climb the stairs -> upper_hall
    opt: Look around again -> - set looked

`name:` is the title drawn on row 0; without it the scene id is shown. `ending:` is a flag set when the scene is
reached, so a later branch (or a second ending scene) can gate on having seen it. `music:` follows the song rules
above.

### Text lines

`text:` lists the scene's logical lines, at most 8 after `system_*` conditions are folded for the target being
built. Each may be any length: the engine word-wraps it at spaces to the text band width (62 columns on ZX) and
hard-splits a word that is longer than a whole row. Blank lines are dropped and
the text is top-aligned in the band; wrapped rows, not source lines, count against the screen budget. Two per-line
devices change what is shown:

- **conditional lines** — append `-> if <flag-or-item>` / `-> unless <flag-or-item>` (repeat or mix either token, up
  to 8; every condition must hold). The line renders only then; hidden lines close up, so the body changes with the
  state. An old prefix spelling (`if <flag>: text`) is still read and normalised to the arrow form.
- **selectable words** — mark a word or phrase `{{like this}}` or `{{like this|flag}}`. It renders in the highlight
  colour, joins the cursor list above the option menu, and choosing it with ENTER sets the flag it names — the word
  itself by default, lowercased with anything but letters, digits and `_` as `_`. A chosen word renders as ordinary
  text from then on (one-shot), so lines and options gated on it change with the choice. Up to 8 per scene. The
  markers do not count toward the wrapped width. Keep a word or phrase short enough to stay on one wrapped row; the
  editor warns if a wrap would split it (only the first part could then be highlighted and selected). Put a text line
  a word reveals (`-> if <flag>`) directly below the line containing the word: text renders in source order, and the
  editor warns when the matching reveal line is elsewhere.

A condition (here and everywhere in the format) only *tests* a name; see
[Flags and inventory](#flags-and-inventory) for where names come from.

#### Build-time system flags

`system_zx128`, `system_zx48`, `system_next`, `system_sms`, `system_cpc`, `system_cpc464`, `system_msx2`,
`system_gb`, `system_c64`, `system_nes`, `system_oric` and `system_web` are reserved pseudo-flags that are true only
while
generating that target. `system_zx` is a legacy any-Spectrum flag true for both `zx128` and `zx48`, and
`system_cpc` is true for both `cpc` and `cpc464`. They are folded at build time: on a matching build an `if system_zx`
token disappears and the line/option is always shown, while on any other build the whole line/option is omitted.
`unless` is the inverse. They never receive a runtime flag id, are not affected by `clear`, and may appear only in
`if`/`unless`
conditions — declaring them, listing them in `start:`, using them with `set`/`unset`/`pick`/`leave`, as an `ending:`
or as a selectable-word flag is an error.

This is how one source can give each system its own instructions or credits, for example:

    text:
      Move the cursor with the arrow keys.
      Press ENTER to choose. -> if system_zx128
      Press SPACE to open the menu and ENTER or fire to choose. -> if system_cpc

The generated scene data (and therefore the ZX 128K/48K/Next/CPC/SMS/MSX2/GB builds) differs per target. Per-scene
limits such
as the 8 text lines and 6 options apply after this folding, so a scene may carry more source lines when each target
keeps only its own subset. The web export is not one of those systems, so all native system flags are false there;
keep a generic line for the web build.

### Options

`opt:` lines are the scene's menu, at most 6, each at most 62 columns wide (conditions and the `msg` tail after `->`
are not displayed and do not count):

    opt: <label> -> <target> [if <n>]... [unless <n>]... [set <f>] [unset <f>] [pick <i>] [leave <i>] [clear] [msg <text>]

- **target** is a scene id the player moves to, or `-` to re-enter the *current* scene: the option's effects are
  applied and the scene is redrawn, with no navigation. Use it for toggles, waits and other in-place actions.
- **`if` / `unless <flag-or-item>`** gate the entry: `if` shows it only when the name is set, `unless` only when it
  is not. Repeat or mix them, up to 8; every condition must hold (AND).
- **`set` / `unset <flag>`** turn a flag on or off.
- **`pick` / `leave <item>`** take and remove an inventory item. A `pick` entry hides itself while the item is
  held, so an item cannot be taken twice; `leave` makes it pickable again.
- **`clear`** is an explicit full reset: before the option's own effects it wipes *every* flag and item and
  re-grants the `# Game start:` names. The engine never clears state on its own, so ordinary navigation back to the
  first scene keeps the run — put `clear` on an ending's "Start again" option. `clear set seen_x` carries one flag
  into the fresh run.
- **`msg <text>`** shows the text in a modal popup before the option's effects and navigation run. The message
  consumes the rest of the line, so put every condition/effect before it; continuation lines are joined with spaces.
  It is plain text (selectable words are not parsed), wraps at the target's text width, and scrolls with UP/DOWN when
  it exceeds the pane. Any other key dismisses it (and so do UP at the top or DOWN at the bottom), so a short message
  still closes with any key. `popup_hint:` overrides the dismiss line (default "Press a key"). Absent means no popup.
  A message shares its scene's storage, so very long ones count against the scene budget below.

The player moves with the cursor keys or W/S and confirms with ENTER; the cursor never wraps, and pressing down past
the last entry moves onto the inventory band. Conditions may name items as well as flags, since items are flags too.

## Items

`# Items` is optional and gives inventory items their display side: a name, a description and their own options. The
item id itself comes from usage — a name used by `pick`/`leave`/`start:` or listed in `items:` — and a block here
joins the item list just like those:

    # Items
    ## lantern
    name: lámpada                # optional display name (<= 58 columns; default the id)
    desc: A dented brass lantern.
      The wick is still good. -> if room_lit
    opt: Light it -> - inscene cellar set lamp_lit leave matches
    opt: Drop it -> - leave lantern

- `name:` is what the inventory band and item list show; multi-word, at most 58 columns, defaulting to the id.
- `desc:` lines (up to 4 logical lines) print on the item screen; each following indented line is its own logical
  line, may be any length (it word-wraps like scene text), and may carry the same `-> if` / `-> unless` conditions as
  a text line.
- `opt:` lines (up to 6) apply their effects and then go to the arrow target: `-` redraws the current scene, a
  scene id navigates there (so an item can be a way into another scene). Every scene option token works, including
  **`msg <text>`**, plus **`inscene <scene-id>`**, which shows the option only when the item was opened from that
  scene (independent of the target) — the hook that gives a global item a room-specific action.

Opening a held item from the inventory band shows its title and description, then its options, the **Drop** entry
(only when `carry:` is set) and a **Back** entry. On the pinned layouts the entries sit at the bottom of the text band;
on the dialog layouts they start immediately below the description. `inventory_drop:` and `inventory_back:` rename those
two labels. Dropping sets the item off, and the scene is redrawn on return.

## Flags and inventory

Flags are a 32-byte bitmap. Ids 0..127 are game flags, set by `set` and by `ending:`; ids 128..191 are inventory
items, which are also flags — an `if` tests a held item exactly like a set flag, which is why conditions and words
may name either. An `if`, `unless`, text-condition or word flag must resolve to a *known* name: declared in `flags:`,
`items:` or a `# Items` block, assigned somewhere (`set`, `unset`, `pick`, `leave`, `start:`, `ending:` or a
selectable word), or be one of the build-time `system_*` flags described above. A typo is an error, never a new flag.

Held items render left-to-right along the bottom band (row 23) in display-name order — item ids are assigned in that
order — over a black bar NIRVANA+ never touches. The selected item is highlighted and marked `>`; earlier and later
hidden items are pointed at by `<` and `>` markers when the single line has to scroll. From the option cursor,
pressing down past the last option enters the band; there the cursor keys (or A/D) pick an item and ENTER opens its
screen, described under [Items](#items). The inventory can never soft-lock a `carry:` cap: a full pack hides `pick`
entries, and every item can always be dropped through its own screen.

## Authoring recommendations

These are conventions, not rules — the format accepts their opposite — but they make a game easier to read and
less mechanical on the small text band.

- **Reveal new text directly below the word that reveals it.** A selectable word is one-shot: choosing
  `{{brass key}}` sets the `brass_key` flag and the word turns back into plain text. Put the line gated on that flag
  immediately below the line containing the word, so the response appears where the player was looking:

      text:
        A {{brass key}} glints in the dust.
        It looks like it opens the cellar. -> if brass_key

- **Give item actions a `msg`.** `pick`, `leave` and an item's own `opt:` change state silently otherwise. Put
  `msg` at the very end of the option (it consumes the rest of the line) so the player sees the result before the
  scene redraws or navigates:

      opt: Take the lantern -> - pick lantern msg You take the brass lantern.
      opt: Light it -> - inscene cellar set lamp_lit msg The wick catches with a sputter.

- **Put character replies in a `msg` popup.** Keep scene text for narration and the room, and answer dialogue with
  the option's popup. It separates speech from description without another text system, and works on every target:

      opt: Ask about the boat -> - msg She is older than she looks, but she still floats.

- **Hide some progression in item screens.** A scene option is a signpost; an item option rewards opening the
  inventory. Move an advancing action onto the item's `opt:` (use `inscene <scene>` when it only works in one room)
  so the route is discoverable rather than listed in the main menu. The editor counts item-option targets as
  reachable, so a scene reached this way is valid:

      # Items
      ## captain_log
      opt: Read the last entry -> harbour_night

## Screen budgets

The ZX layout drives the budgets the editor validates:

| Thing | Limit |
|---|---|
| Scene text logical lines | 8 per target after `system_*` folding (wrapped rows must fit the band) |
| Option/label/title columns | 62 (item display names 58) |
| Scene text / item description | word-wrapped at 62 columns on ZX |
| Options per scene/item | 6 |
| Conditions per line/option | 8, ANDed |
| Selectable words per scene | 8 |
| Pinned scene (worst case) | wrapped text + options `<= 22 - art_rows` rows |
| Pinned item screen (worst case) | wrapped description + entries `<= 21 - art_rows` rows |
| Pop-up dialog scene text | scrolls; no fit limit |
| Popup `msg` text | scrolls; shares the scene's storage blob |

The title rides on row 0 and the inventory band on row 23, which is why the pinned budget excludes them. Scene text
is top-aligned in the band and options are pinned to its bottom, so a short text block still leaves the menu where
the player expects it. Conditional text lines and options can appear in different combinations: the editor checks the
worst case across every possible flag/item state, plus the one-row-per-entry menu. With `menu: popup` on ZX the options
leave the band, the text may use row 23, and overflowing scene text and item descriptions scroll (UP/DOWN, with
LEFT/RIGHT moving between highlighted words when present). Password and inventory labels are single band rows too
(62 columns). The other targets re-fit the same content to their own column counts and band heights (`# Systems`
settings); these are the caps the author writes against.

## Storage budget

On the ZX, all art, scene and inventory blobs — and song modules — share the five paged 16K banks, and blobs are
ZX0-compressed at build time (raw sizes shrink to roughly half, in effect doubling what fits). On the CPC 6128 the art
and song blobs share the four extra 16K banks; a music build leaves `BANK_2` free for the AY workspace, so art + music
must fit 64K. The CPC 464 has no extra banks: its story and a small load buffer are resident, and each art/song
blob is read from the `GAME.Bn` files on the disk when needed, so total art size is limited by the disk instead of
RAM. On the MSX2 the scene data is in bank 1, each art takes a bank from 2 up, and songs are packed into the
following ROM banks. On the Game Boy Color the scenes, art and converted APU streams are uncompressed in MBC1 banks;
each song starts at a bank boundary and may span several banks. The ZX raw figures to size against:

- a scene is about 175 bytes, plus its text, labels, conditions and `msg` popup strings;
- an art is `8*art_rows` bytes plus 48 per unique tile, at most `392*art_rows` (3920 bytes at the default 10).

On the ZX the scene workspace (`_scene_ws`) is sized to the largest single scene, so one very long popup can grow the
main image even when the bank pool has room; the build then fails with "home bank overflow". Shorten that scene's
text/messages or split the exposition across scenes. Rule of thumb at the defaults: about 13 arts with ~60 scenes fit,
~11 arts if every one is at maximum tile density, ~9-10 large arts at ~200 scenes. The build fails past the budget
with "scene/art data exceeds available banks"; the fix is to merge arts (repoint several scenes' `art:` to one id) or
drop detail from prompts, not to squeeze text.
The songs' 4158-byte cap is separate and enforced at conversion time.

The editor writes `game.md` atomically (keeping `game.md.bak`) and refuses a save that fails validation. It is fine
to hand-edit the file; the next structured save re-serialises it canonically, so formatting is normalised rather than
preserved, and old spellings are rewritten to the current ones in the process.