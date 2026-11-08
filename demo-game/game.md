# game.md — authoring format for a game's art, scenes, items and songs

# Game

title: The Lighthouse Keeper
prompt: 1980s game screen, high contrast, flat colours, no text, no letters
negative_prompt: blurry, low resolution, jpeg artifacts, deformed, extra limbs, malformed, watermark, signature, text,
  letters
flags: asked_elias, asked_father, uxia_trusted, uxia_told, uxia_knows, uxia_left, know_truth, cellar_lit, chest_open, lens_repaired, oiled, won, truth, dark, exam_coat, exam_misericordia, exam_uxia, exam_journal, exam_cups, exam_chest, exam_letter, exam_daughter, exam_lens, exam_reservoir, exam_grave, exam_mast, exam_green, elias_rested, pena_met, pena_offered, pena_deal, pena_defied
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

## zx128
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

## cpc464
art_rows: 8
columns: 32
mode: 0

## msx2
art_rows: 10
columns: 64

## gb
art_rows: 6

## c64
art_rows: 6

## nes
art_rows: 10

# Art

## title
prompt: a storm-lashed granite lighthouse at Fisterra on the Galician Costa da Morte at night, huge Atlantic waves
  breaking below, a small supply boat approaching, one lit window, dramatic clouds, no text
image: gen-1793441722798.png
crop: 0 25 100 75

## jetty
prompt: a wet granite jetty below the Fisterra lighthouse in a storm, a moored rowboat, a woman in a dark oilskin coat
  holding an oil lantern, rain and Atlantic spray, no text
refs: uxia
image: gen-1793442406565.png
crop: 0 0 100 75

## hall
prompt: the round granite entrance hall of an old Galician lighthouse, an oilskin coat on a hook, an oil lantern on a
  shelf, iron stairs winding up, wooden doors, storm light through a porthole, no text
image: gen-1793443048461.png

## cottage
prompt: the keeper's cottage kitchen at Fisterra, a wood fire in a stone hearth, a wooden table with two cups and an
  open journal, rain on the windows, a pantry door, a woman in a dark oilskin coat by the window, no text
refs: uxia
image: gen-1793443731077.png

## cellar
prompt: a low granite cellar under a Galician lighthouse, shelves of oil cans, an iron-bound sea chest, a ship's log on
  a crate, an oil lantern, damp walls, no text
image: gen-1793444372078.png

## workshop
prompt: the lamp room at the top of the Fisterra lighthouse, a huge brass Fresnel lens, a missing gear, a dry reservoir,
  a workbench of tools, storm clouds outside the gallery windows, no text
image: gen-1793445012067.png

## garden
prompt: a walled clifftop garden in rain at Fisterra, a grave under a granite wall, a broken signal mast with frayed
  shutters, white Atlantic waves on the rocks below, no text
image: gen-1793484116838.png

## ending
prompt: the Fisterra lighthouse beam sweeping across a stormy Atlantic sea at night, a small 1930s coastal steamer like
  the one in the reference image safe beyond the rocks, dawn breaking, no text
refs: misericordia
image: gen-1793446334949.png

## ending_truth
prompt: a revenue cutter with a white searchlight approaching a dark coastal steamer, the unlit Fisterra lighthouse on
  the cliff, rain and spray, no text
refs: uxia misericordia
image: gen-1793447058386.png

## ending_dark
prompt: an empty rowboat on a black stormy Atlantic sea, the unlit Fisterra lighthouse on the cliff behind, wreckage and
  a vanishing green light in the distance, no text
refs: misericordia
image: gen-1793447740548.png

# References

## uxia
prompt: reference sheet of a Galician woman in her late thirties, dark oilskin coat, soaked dark hair, holding an oil
  lantern, three-quarter view, isolated on a flat dark navy background, crisp black outlines, no water, no text
image: gen-1793440419525.png
seed: 42

## misericordia
prompt: reference sheet of a small 1930s Galician coastal steamer, dark hull with a white stripe, green sidelight,
  single funnel, three-quarter side view, whole ship visible, isolated on a flat dark navy background, crisp black
  outlines, no water, no text
image: gen-1793441081139.png
seed: 42

# Items

## key
name: Brass Key
desc: A small brass key ring from Elías's oilskin.
  It already turned the sea chest. -> if chest_open
  It might fit the sea chest. -> unless chest_open
opt: Unlock the sea chest -> chest inscene cellar if cellar_lit if exam_chest unless chest_open set chest_open msg The key turns with a gritty snap. The lid lifts.

## oil_lantern
name: Oil Lantern
desc: A brass oil lantern with a glass chimney.
  The wick burns steadily. -> if cellar_lit
  The wick is dry. It needs a match. -> unless cellar_lit
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
name: The Lighthouse Keeper
art: title
text:
  Fisterra Light. 14 October 1936, twenty to midnight.
  The relief boat leaves you on the jetty.
  The lighthouse is dark.
  A woman waits by the door with a lantern.
opt: Call out to her -> jetty_uxia msg Your voice is lost in the wind and surf.
opt: Climb to the lighthouse -> hall
opt: How to play -> help
opt: About -> about

## jetty_uxia
name: Uxía Mariño
art: jetty
text:
  She is in her thirties, oilskin black with rain.
  "You're the new keeper. I'm Uxía Mariño. Elías was my father."
  "The {{Misericordia|exam_misericordia}} is due at midnight. The relief ship."
  She says the name too quickly. -> if exam_misericordia
  "The lamp has to be lit."
opt: "Why are you here?" -> - msg She looks past you at the lighthouse. "Someone has to keep it."
opt: "What happened to Elías?" -> - msg The wind takes her answer. "He drowned last October. They never found him."
opt: "I'll light the lamp." -> hall set uxia_trusted msg Uxía says "Thank you"
opt: Walk past her to the tower -> hall

## hall
name: The Keeper's Hall
art: hall
text:
  Salt, wet stone, cold ash.
  An {{oilskin coat|exam_coat}} hangs by the door.
  Something heavy hangs in the coat pocket. -> if exam_coat unless key
  An oil lantern sits on the shelf. -> unless oil_lantern
  The stairs climb into darkness.
opt: Take the key ring -> - if exam_coat unless key pick key msg The ring is cold. Two small keys and a bent brass tag.
opt: Take the oil lantern -> - unless oil_lantern pick oil_lantern msg The brass body is sound, but the chimney is cracked.
opt: Go to the kitchen -> kitchen
opt: Open the cellar door -> cellar
opt: Climb to the lamp room -> lamp_room

## kitchen
name: The Keeper's Kitchen
art: cottage
text:
  A wood fire crackles. Two {{cups|exam_cups}} sit on the table.
  One is still warm. -> if exam_cups
  Uxía stands at the window, watching the sea. -> unless uxia_left
  An open {{journal|exam_journal}} lies beside them.
  The last entry is torn at the corner. -> if exam_journal
opt: Read the torn entry -> journal if exam_journal
opt: Search the pantry -> pantry
opt: Talk to Uxía -> uxia_talk unless uxia_left
opt: Step out to the garden -> garden
opt: Return to the hall -> hall

## journal
name: Elías's Journal
art: cottage
text:
  The hand is cramped and hurried.
  Most of it is weather and tides.
  The {{last entry|know_truth}} is torn at the corner.
  "The Misericordia is not a relief ship." -> if know_truth
  "Tobacco, brandy, rifles." -> if know_truth
  "They paid me to keep the light dark on the fourteenth." -> if know_truth
  "If I speak, they will take Uxía." -> if know_truth
opt: Return to the kitchen -> kitchen

## pantry
name: The Pantry
art: cottage
text:
  Shelves of tinned beef, tea, and lamp oil.
  A tin of oil stands on the shelf. -> unless oil_can
  A box of matches sits beside it. -> unless matches
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
  The lock is old. A small key would turn it. -> if exam_chest unless chest_open
  A ship's log rests on a crate. -> if cellar_lit
opt: Read the ship's log -> logbook if cellar_lit
opt: Search the open chest -> chest if chest_open
opt: Climb back to the hall -> hall

## chest
name: The Sea Chest
art: cellar
text:
  The lid creaks open.
  A brass gear wrapped in oilcloth. -> unless gear
  A red signal flare. -> unless flare
  A {{folded letter|exam_letter}} lies inside.
  The letter is not in Elías's handwriting. -> if exam_letter
opt: Take the brass gear -> - unless gear pick gear
opt: Take the signal flare -> - unless flare pick flare
opt: Read the letter -> letter if exam_letter
opt: Close the chest -> cellar

## letter
name: The Letter
art: cellar
text:
  "Keep the light dark on the {{fourteenth|know_truth}} and the debt is paid."
  The same night Elías drowned. -> if know_truth
  "If you speak, your {{daughter|exam_daughter}} pays it."
  They knew about Uxía. -> if exam_daughter
  There is no signature.
opt: Return to the chest -> chest

## logbook
name: The Ship's Log
art: cellar
text:
  The pages are swollen with damp.
  "Misericordia. Three runs this autumn."
  "Cargo: tobacco, brandy, rifles."
  Every entry is signed {{E.M.|know_truth}}.
  The fourteenth is circled in red. -> if know_truth
opt: Return to the cellar -> cellar

## lamp_room
name: The Lamp Room
art: workshop
text:
  The great lens fills the room like a frozen wave.
  The {{Fresnel lens|exam_lens}} is whole, and its gear turns true. -> if lens_repaired
  The {{Fresnel lens|exam_lens}} is whole, but its turning gear is gone. -> unless lens_repaired
  The {{reservoir|exam_reservoir}} is full of oil. -> if oiled
  The {{reservoir|exam_reservoir}} is dry. -> unless oiled
  The wick is dry. Rain hammers the glass. The sea is white.
  A shape waits by the lens. -> unless elias_rested
  Through the rain, a man in grey waits on the cliff path. -> unless pena_defied
opt: Go down to the hall -> hall
opt: Speak to the shape at the lens -> elias unless elias_rested
opt: Wait for midnight -> the_hour

## elias
name: The Shape at the Lens
art: workshop
text:
  A tall shape stands at the lens, its coat white with salt.
  "Don't shout," it says. "The dead are shy."
  The voice is Elías Mariño's, or what the sea left of it.
  You have spoken to him before. -> if asked_elias
opt: "What happened on the fourteenth?" -> - set asked_elias msg "I kept the light twenty-two years. Then a man in grey found what I feared. They paid me to keep it dark. I tried to light it anyway. They were waiting."
opt: "Why did you take the money?" -> - set asked_elias msg "Uxía. They said they would take Uxía."
opt: "Who paid you?" -> - set asked_elias msg "A man in a grey coat. Dry boots. A silver cigarette case."
opt: "How do I repair the lamp?" -> - set asked_elias msg "The gear is in the sea chest. Oil is in the pantry. The rest is nerve."
opt: "I have your journal." -> - if know_truth set asked_elias msg "Then you know. Light her, keeper. Finish it."
opt: Rest, Elías. -> lamp_room set elias_rested msg The shape inclines its head, and the cold goes out of the room.

## garden
name: The Cliff Garden
art: garden
text:
  A walled garden, salted by spray.
  A {{grave|exam_grave}} waits under the wall.
  "Elías Mariño. Died 14 October 1935." -> if exam_grave
  The {{signal mast|exam_mast}} leans, its shutter rope frayed.
  A flare fired from the gallery would be seen from the mainland. -> if exam_mast
  Below, As Agullas break white.
  A man in grey waits on the cliff path. -> unless pena_defied
opt: Talk to the man in grey -> pena unless pena_defied
opt: Return to the kitchen -> kitchen

## uxia_talk
name: Uxía
art: cottage
text:
  {{Uxía|exam_uxia}} stands by the window with her arms folded.
  She keeps looking at the door. -> if exam_uxia
  "My father kept this light for twenty-two years," she says.
  "He would not have let it go dark."
opt: Promise to light the lamp -> - unless uxia_trusted set uxia_trusted msg "Uxía nods once. "Then we have a chance.""
opt: Ask about her father -> - unless asked_father set asked_father msg "He sent me away last October. I never saw him again."
opt: Tell her what you found -> - if know_truth unless uxia_told set uxia_told msg "You put the journal on the table. Uxía reads it twice. Her face does not change. "He sent me away because of them," she says."
opt: "I'm sorry. They threatened you." -> uxia_after if uxia_told unless uxia_knows set uxia_knows msg "Uxía wipes her eyes. "If you mean to signal the cutter, you'll need this. He gave it to me last year.""
opt: "You knew, didn't you?" -> kitchen if uxia_told unless uxia_left set uxia_left msg ""You didn't know him," she says. "Don't pretend you do.""
opt: Leave her -> kitchen

## uxia_after
name: An Understanding
art: cottage
text:
  Uxía holds out a red flare. -> unless flare
  You already have the flare from the sea chest. -> if flare
  Rain ticks at the window.
opt: Take the flare -> - unless flare pick flare msg The flare is warm from her coat.
opt: Go up to the lamp room -> lamp_room

## the_hour
name: Midnight
art: workshop
text:
  The clock in the hall strikes twelve.
  Through the rain, a {{green light|exam_green}} blinks beyond As Agullas.
  A ship's sidelight, green against the black. -> if exam_green
  The Misericordia.
  The lamp is ready. -> if lens_repaired if oiled if matches
  The matches are in your pocket. -> if matches
  The flare is in your pack. -> if flare
opt: Let the light die -> ending_dark msg You step back and let the darkness win.
opt: Go out to the cliff path -> pena unless pena_defied
opt: Go back down -> lamp_room

## pena
name: Anxo Pena
art: garden
text:
  He waits on the cliff path, dry in the rain.
  A silver cigarette case clicks shut in his hand.
  "Good evening," he says. "The lamp is not giving trouble?"
  He does not look at the tower. He looks at you.
opt: "Who are you?" -> - set pena_met msg "Anxo Pena," he says. "Revenue service." The Misericordia is due at midnight. Leave the light dark.
opt: "You paid Elías." -> - if know_truth set pena_met msg "Elías made a choice," he says. "You are making one now. There is still time to choose sensibly."
opt: "I will keep it dark." -> - unless pena_offered set pena_met set pena_offered msg "Pena takes a folded envelope from his coat. "For the keeper," he says. "For the silence." He holds it out."
opt: Take the envelope -> the_hour if pena_offered unless pena_deal set pena_deal msg The paper is dry and heavy. You put it in your coat.
opt: "I will not help you." -> garden set pena_met set pena_defied msg "Pena looks at you a long moment. "You are not the first keeper to mistake stubbornness for courage." He puts on his hat."
opt: Say nothing and go back -> garden

## ending_light
name: The Light
art: ending
ending: won
text:
  You fit the gear. The lens shudders, then turns.
  The match flares; the wick catches; the lamp gathers the dark.
  A white beam sweeps As Agullas, steady as a heartbeat.
  The Misericordia answers with her horn and turns away.
  The cutter is too late; the village wakes to a normal dawn.
  You keep Elías's journal. The truth can wait. -> if know_truth
  Uxía stays until the weather clears. -> if uxia_knows
  You are alone with the light and the empty stairs. -> unless uxia_knows
opt: Start again -> start clear

## ending_truth
name: The Truth
art: ending_truth
ending: truth
text:
  You fire the flare. It climbs into the rain and bursts red.
  The cutter comes out of the dark with its searchlight on.
  The Misericordia turns, too late. Crates split on the rocks.
  By dawn, the lighthouse is full of police.
  Uxía tells them everything. -> if uxia_knows
  Uxía is gone before they arrive. -> if uxia_left
  Uxía is not here. -> unless uxia_knows unless uxia_left
  Elías's name is in the paper. -> if know_truth
opt: Start again -> start clear

## ending_dark
name: The Dark
art: ending_dark
ending: dark
text:
  You let the lamp die.
  The green light reaches As Agullas and vanishes.
  You take the rowboat. Behind you, the sea is loud.
  At dawn there is wreckage in the bay.
  And Elías's journal in your coat. -> if know_truth
  Pena pays you in clean notes. -> if pena_deal
  The man in grey does not look at you. -> if pena_defied
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
  The Lighthouse Keeper
  A short mystery set at Fisterra, on the Galician Costa da Morte.
  Story, art and code made for the demo.
opt: Back -> start
