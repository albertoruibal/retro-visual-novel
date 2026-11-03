# game.md — authoring format for a game's art, scenes, items and songs

# Game

title: The Lantern Keeper
prompt: 1980s game screen, high contrast, flat colours, no text, no letters
negative_prompt: blurry, low resolution, jpeg artifacts, deformed, extra limbs, malformed, watermark, signature, text,
  letters
flags: asked_mara, asked_elias, asked_father, mara_trusted, mara_knows, mara_left, know_truth, cellar_lit, chest_open, lens_repaired, oiled, won, truth, dark, exam_coat, exam_lantern, exam_mercy, exam_mara, exam_journal, exam_cups, exam_chest, exam_log, exam_letter, exam_daughter, exam_lens, exam_reservoir, exam_grave, exam_mast, exam_green
items: key, oil_lantern, oil_can, matches, gear, flare
songs: theme
music: theme
hires: 2x
popup_hint: Continue
inventory_drop: Discard
inventory_back: Close
highlight_ink: yellow
seed: 1
steps: 45
cfg: 6
width: 512
height: 256

# Systems

## zx
art_rows: 12
title_ink: white

## next
art_rows: 12

## sms
art_rows: 10

## cpc
art_rows: 10
columns: 32
mode: 0

## msx2
art_rows: 10
columns: 64

## gb
art_rows: 6

# Art

## title
prompt: a storm-lashed lighthouse on a black rock at night, huge waves breaking below, a small supply boat approaching,
  one lit window, dramatic clouds, no text
image: gen-1793441722798.png
crop: 0 25 100 75

## jetty
prompt: a wet stone jetty below a lighthouse in a storm, a moored rowboat, a woman in a dark oilskin coat holding an oil
  lantern, rain and sea spray, no text
refs: mara
image: gen-1793442406565.png
crop: 0 0 100 75

## hall
prompt: the round stone entrance hall of an old lighthouse, an oilskin coat on a hook, an oil lantern on a shelf, iron
  stairs winding up, wooden doors, storm light through a porthole, no text
image: gen-1793443048461.png

## cottage
prompt: the keeper's cottage kitchen, a peat fire, a wooden table with two cups and an open journal, rain on the
  windows, a pantry door, a woman in a dark oilskin coat by the window, no text
refs: mara
image: gen-1793443731077.png

## cellar
prompt: a low stone cellar under a lighthouse, shelves of oil cans, an iron-bound sea chest, a ship's log on a crate, an
  oil lantern, damp walls, no text
image: gen-1793444372078.png

## workshop
prompt: the lamp room at the top of a lighthouse, a huge brass Fresnel lens, a missing gear, a dry reservoir, a
  workbench of tools, storm clouds outside the gallery windows, no text
image: gen-1793445012067.png

## garden
prompt: a walled clifftop garden in rain, a grave under a stone wall, a broken signal mast with frayed shutters, white
  waves on the rocks below, no text
image: gen-1793484116838.png

## ending
prompt: a lighthouse beam sweeping across a stormy sea at night, a small coastal steamer like the one in the reference
  image safe beyond the reef, dawn breaking, no text
refs: mercy
image: gen-1793446334949.png

## ending_truth
prompt: a revenue cutter with a white searchlight approaching a dark coastal steamer, an unlit lighthouse on the cliff,
  rain and spray, no text
refs: mara mercy
image: gen-1793447058386.png

## ending_dark
prompt: an empty rowboat on a black stormy sea, an unlit lighthouse on the cliff behind, wreckage and a vanishing green
  light in the distance, no text
refs: mercy
image: gen-1793447740548.png

# References

## mara
prompt: reference sheet of a woman in her late thirties, dark oilskin coat, soaked dark hair, holding an oil lantern,
  three-quarter view, isolated on a flat dark navy background, crisp black outlines, no water, no text
image: gen-1793440419525.png
seed: 42

## mercy
prompt: reference sheet of a small 1930s coastal steamer, dark hull with a white stripe, green sidelight, single funnel,
  three-quarter side view, whole ship visible, isolated on a flat dark navy background, crisp black outlines, no water,
  no text
image: gen-1793441081139.png
seed: 42

# Items

## key
name: Brass Key
desc: A small brass key ring from Elias's oilskin.
  It might fit the sea chest.
opt: Unlock the sea chest -> chest inscene cellar if cellar_lit if exam_chest unless chest_open set chest_open msg The key turns with a gritty snap. The lid lifts.

## oil_lantern
name: Oil Lantern
desc: A brass oil lantern with a glass chimney.
  The wick is dry. It needs a match.
opt: Light the oil lantern -> - inscene cellar if matches unless cellar_lit set cellar_lit msg The wick catches. A small flame pushes back the dark.

## oil_can
name: Oil Can
desc: A tin of lamp oil, half full.
  Enough for the great lamp.
opt: Fill the lamp reservoir -> - inscene lamp_room if exam_reservoir unless oiled set oiled leave oil_can msg The reservoir drinks the oil and settles.

## matches
name: Matches
desc: A damp box of matches.
  The heads are dry.
opt: Light the great lamp -> ending_light inscene the_hour if lens_repaired if oiled msg The match flares. The wick catches.

## gear
name: Brass Gear
desc: A cog wrapped in oilcloth.
  It fits the lens turntable.
opt: Fit the brass gear -> - inscene lamp_room if exam_lens unless lens_repaired set lens_repaired leave gear msg The gear slots home. The lens turns with a soft click.

## flare
name: Signal Flare
desc: A red signal flare in a waxed tube.
  Fired from the gallery, it would be seen from the mainland.
opt: Fire the signal flare -> ending_truth inscene the_hour if know_truth msg The flare hisses alight.

# Scenes

## start
name: The Lantern Keeper
art: title
text:
  Dunmore Light. 14 October 1936, twenty to midnight.
  The relief boat leaves you on the jetty.
  The lighthouse is dark.
  A woman waits by the door with a lantern.
opt: Call out to her -> jetty_mara msg Your voice is lost in the wind and surf.
opt: Climb to the lighthouse -> hall
opt: How to play -> help
opt: About -> about

## jetty_mara
name: Mara Vane
art: jetty
text:
  She is in her thirties, oilskin black with rain.
  "You're the new keeper. I'm Mara Vane. Elias was my father."
  "The {{Mercy Belle|exam_mercy}} is due at midnight. The relief ship."
  She says the name too quickly. -> if exam_mercy
  "The lamp has to be lit."
opt: "Why are you here?" -> - msg She looks past you at the lighthouse. "Someone has to keep it."
opt: "What happened to Elias?" -> - msg The wind takes her answer. "He drowned last October. They never found him."
opt: "I'll light the lamp." -> hall set mara_trusted msg Mara says "Thank you"
opt: Walk past her to the tower -> hall

## hall
name: The Keeper's Hall
art: hall
text:
  Salt, wet stone, cold ash.
  An {{oilskin coat|exam_coat}} hangs by the door.
  Something heavy hangs in the coat pocket. -> if exam_coat
  An oil lantern sits on the shelf.
  The stairs climb into darkness.
opt: Take the key ring -> - if exam_coat pick key msg The ring is cold. Two small keys and a bent brass tag.
opt: Take the oil lantern -> - unless oil_lantern pick oil_lantern msg The brass body is sound, but the chimney is cracked.
opt: Go to the kitchen -> kitchen
opt: Open the cellar door -> cellar
opt: Climb to the lamp room -> lamp_room

## kitchen
name: The Keeper's Kitchen
art: cottage
text:
  A peat fire ticks in the stove.
  Mara stands at the window, watching the sea.
  Two {{cups|exam_cups}} sit on the table.
  One is still warm. -> if exam_cups
  An open {{journal|exam_journal}} lies beside them.
  The last entry is torn at the corner. -> if exam_journal
opt: Read the torn entry -> journal if exam_journal
opt: Search the pantry -> pantry
opt: Talk to Mara -> mara_talk unless mara_left
opt: Step out to the garden -> garden
opt: Return to the hall -> hall

## journal
name: Elias's Journal
art: cottage
text:
  The hand is cramped and hurried.
  Most of it is weather and tides.
  The {{last entry|know_truth}} is torn at the corner.
  "The Mercy Belle is not a relief ship." -> if know_truth
  "Tobacco, brandy, rifles." -> if know_truth
  "They paid me to keep the light dark on the fourteenth." -> if know_truth
  "If I speak, they will take Mara." -> if know_truth
opt: Return to the kitchen -> kitchen

## pantry
name: The Pantry
art: cottage
text:
  Shelves of tinned beef, tea, and lamp oil.
  A tin of oil stands beside a box of matches.
  A small window looks out at the black sea.
opt: Take the oil can -> - unless oil_can pick oil_can msg The tin is heavy enough for one night.
opt: Take the matches -> - unless matches pick matches msg The heads rattle dryly in the box.
opt: Return to the kitchen -> kitchen

## cellar
name: The Cellar
art: cellar
text:
  The stairs end in cold darkness.
  You smell paraffin, salt, and old rope.
  It is too dark to search. -> unless cellar_lit
  The oil lantern gutters. -> if cellar_lit
  An iron-bound {{sea chest|exam_chest}} sits against the wall. -> if cellar_lit
  The lock is old. A small key would turn it. -> if exam_chest
  A ship's log rests on a crate. -> if cellar_lit
opt: Read the ship's log -> logbook if cellar_lit
opt: Search the open chest -> chest if chest_open
opt: Climb back to the hall -> hall

## chest
name: The Sea Chest
art: cellar
text:
  The lid creaks open.
  Inside: a brass gear wrapped in oilcloth,
  a red signal flare,
  and a {{folded letter|exam_letter}}.
  The letter is not in Elias's handwriting. -> if exam_letter
opt: Take the brass gear -> - unless gear pick gear
opt: Take the signal flare -> - unless flare pick flare
opt: Read the letter -> letter if exam_letter
opt: Close the chest -> cellar

## letter
name: The Letter
art: cellar
text:
  "Keep the light dark on the {{fourteenth|know_truth}} and the debt is paid."
  "If you speak, your {{daughter|exam_daughter}} pays it."
  There is no signature.
  The same night Elias drowned. -> if know_truth
  They knew about Mara. -> if exam_daughter
opt: Return to the chest -> chest

## logbook
name: The Ship's Log
art: cellar
text:
  The pages are swollen with damp.
  "Mercy Belle. Three runs this autumn."
  "Cargo: tobacco, brandy, rifles."
  Every entry is signed {{E.V.|know_truth}}.
  The fourteenth is circled in red. -> if know_truth
opt: Return to the cellar -> cellar

## lamp_room
name: The Lamp Room
art: workshop
text:
  The great lens fills the room like a frozen wave.
  The {{Fresnel lens|exam_lens}} is whole, but its turning gear is gone.
  The {{reservoir|exam_reservoir}} is dry.
  The wick is black and dry.
  Rain hammers the gallery glass. Far below, the sea is white.
opt: Go down to the hall -> hall
opt: Wait for midnight -> the_hour

## garden
name: The Cliff Garden
art: garden
text:
  A walled garden, salted by spray.
  A new {{grave|exam_grave}} waits under the wall.
  The {{signal mast|exam_mast}} leans, its shutter rope frayed.
  Below, the Needles break white.
  "Elias Vane. Died 14 October 1935." -> if exam_grave
  A flare fired from the gallery would be seen from the mainland. -> if exam_mast
opt: Return to the kitchen -> kitchen

## mara_talk
name: Mara
art: cottage
text:
  {{Mara|exam_mara}} stands by the window with her arms folded.
  "My father kept this light for twenty-two years," she says.
  "He would not have let it go dark."
  She keeps looking at the door. -> if exam_mara
  "He sent me away last October. I never saw him again." -> if asked_father
opt: Promise to light the lamp -> - unless mara_trusted set mara_trusted
opt: Tell her what you found -> mara_confront if know_truth unless mara_knows
opt: Ask about her father -> - set asked_father
opt: Leave her -> kitchen

## mara_confront
name: The Truth
art: cottage
text:
  You put the journal on the table.
  Mara reads it twice. Her face does not change.
  "He sent me away because of them," she says.
  "And I thought the Mercy Belle was bringing coal."
opt: "They threatened you. That's why he sent you away." -> mara_after if exam_daughter if know_truth set mara_knows
opt: "I'm sorry. I had to tell you." -> mara_after if mara_trusted if know_truth set mara_knows
opt: "You knew, didn't you?" -> mara_leaves set mara_left
opt: Say nothing -> kitchen

## mara_after
name: An Understanding
art: cottage
text:
  Mara wipes her eyes with the back of her hand.
  "If you mean to signal the cutter, you'll need this."
  She takes a red flare from her coat. -> unless flare
  You already have the flare from the sea chest. -> if flare
  "He gave it to me last year. I never knew what for."
opt: Take the flare -> - unless flare pick flare
opt: Go up to the lamp room -> lamp_room

## mara_leaves
name: She Leaves
art: cottage
text:
  Mara puts on her coat.
  "You didn't know him," she says. "Don't pretend you do."
  The kitchen door bangs shut behind her.
opt: Let her go -> kitchen

## the_hour
name: Midnight
art: workshop
text:
  The clock in the hall strikes twelve.
  Through the rain, a {{green light|exam_green}} blinks beyond the Needles.
  The Mercy Belle.
  A ship's sidelight, green against the black. -> if exam_green
  The lamp is ready. -> if lens_repaired if oiled if matches
  The matches are in your pocket. -> if matches
  The flare is in your pack. -> if flare
opt: Let the light die -> ending_dark msg You step back and let the darkness win.
opt: Go back down -> lamp_room

## ending_light
name: The Light
art: ending
ending: won
text:
  You strike a match. The wick catches.
  The great lens turns; the beam sweeps the Needles.
  The Mercy Belle answers with her horn and passes.
  At dawn, the cutter comes too late. The ship is gone.
  You post Elias's journal to the authorities. -> if know_truth
  Mara stays until the weather clears. -> if mara_knows
  You are alone with the light. -> unless mara_knows
opt: Start again -> start clear

## ending_truth
name: The Truth
art: ending_truth
ending: truth
text:
  You fire the flare. It climbs into the rain and bursts red.
  The cutter comes out of the dark with its searchlight on.
  The Mercy Belle turns, too late. Crates split on the rocks.
  By dawn, the lighthouse is full of police.
  Mara tells them everything. -> if mara_knows
  Mara is gone before they arrive. -> if mara_left
  Mara is not here. -> unless mara_knows unless mara_left
  Elias's name is in the paper. -> if know_truth
opt: Start again -> start clear

## ending_dark
name: The Dark
art: ending_dark
ending: dark
text:
  You let the lamp die.
  The green light reaches the Needles and vanishes.
  You take the rowboat. Behind you, the sea is loud.
  At dawn there is wreckage in the bay.
  And Elias's journal in your coat.
opt: Start again -> start clear

## help
name: How to Play
art: title
text:
  Move with the arrow keys or W/A/S/D.
  Press ENTER to choose. -> if system_zx
  Press ENTER to choose. -> if system_msx2
  Press SPACE for the menu; ENTER or fire chooses. -> if system_cpc
  Button 1 opens the menu; button 2 chooses. -> if system_sms
  A opens the menu; B chooses. -> if system_gb
  Highlighted words can be examined. Select a held item to use it.
  Held items are on the bottom row or in the menu.
opt: Back -> start

## about
name: About
art: title
text:
  The Lantern Keeper
  A short mystery for the Retro Visual Novel engine.
  Story, art and code made for the demo.
opt: Back -> start
