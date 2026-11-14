# game.md — authoring format for a game's art, scenes, items and songs

# Game

title: Juego de demostración
prompt: 1980s game screen, high contrast, flat colours, no text, no letters
negative_prompt: blurry, low resolution, jpeg artifacts, deformed, extra limbs, malformed, watermark, signature, text,
  letters
flags: asked_elias, asked_father, uxia_trusted, uxia_told, uxia_knows, uxia_left, know_truth, cellar_lit, chest_open, lens_repaired, oiled, won, dark, exam_coat, exam_misericordia, exam_uxia, exam_journal, exam_cups, exam_chest, exam_letter, exam_daughter, exam_lens, exam_reservoir, exam_grave, exam_green, elias_rested, pena_met, pena_offered, pena_deal, pena_defied
items: key, oil_lantern, oil_can, matches, gear, flare
songs: theme
music: off
hires: 2x
popup_hint: Continuar
inventory_drop: Descartar
inventory_back: Cerrar
highlight_ink: yellow
seed: 1
steps: 45
cfg: 6
width: 512
height: 256

# Systems

## zx128
margin: 1
title_ink: white

## next
art_rows: 12

## sms

## cpc
art_rows: 10
columns: 32
margin: 2
mode: 0

## cpc464
art_rows: 10
columns: 32
margin: 2
mode: 0

## msx1
margin: 2
menu: popup

## msx2
art_rows: 10
columns: 64
margin: 2

## gb
art_rows: 6

## c64
art_rows: 10
margin: 2

## nes
margin: 2

## oric
dither: bayer2
margin: 3

## zx48
dither: bayer2
margin: 5
title_ink: white

## web
art_rows: 16

# Art

## title
prompt: a storm-lashed granite lighthouse at Fisterra on the Galician Costa da Morte at night, huge Atlantic waves
  breaking below, a lone figure walking up the cliff path, one lit window, dramatic clouds, no text
refs: lighthouse
image: gen-1794257514079.png
crop: 0 6 100 63

## cliff_path
prompt: a wet granite path climbing to the Fisterra lighthouse in a storm, a woman in a dark oilskin coat holding an oil
  lantern, rain and Atlantic spray, no text
refs: uxia lighthouse
image: gen-1794258459814.png
crop: 0 0 100 75

## hall
prompt: the round granite entrance hall of an old Galician lighthouse, an oilskin coat on a hook, an oil lantern on a
  shelf, iron stairs winding up, wooden doors, storm light through a porthole, no text
image: gen-1794259303195.png
crop: 0 15 100 75

## cottage
prompt: the keeper's cottage kitchen at Fisterra, a wood fire in a stone hearth, a wooden table with two cups and an
  open journal, rain on the windows, a pantry door, a woman in a dark oilskin coat by the window, no text
refs: uxia
image: gen-1794260222779.png

## cellar
prompt: a low granite cellar under a Galician lighthouse, shelves of oil cans, an iron-bound sea chest, a ship's log on
  a crate, an oil lantern, damp walls, no text
image: gen-1794261078500.png
crop: 0 17 100 75

## workshop
prompt: the lamp room at the top of the Fisterra lighthouse, a huge brass Fresnel lens, a missing gear, a dry reservoir,
  a workbench of tools, storm clouds outside the gallery windows, no text
image: gen-1794261925051.png
crop: 0 25 100 75

## garden
prompt: a walled clifftop garden in rain at Fisterra, a grave under a granite wall, white Atlantic waves on the rocks
  below, an ordinary Galician villager in a plain grey wool coat and flat cap waiting on the cliff path, no text
refs: pena
image: gen-1794339481002.png
crop: 0 6 100 63

## ending
prompt: the Fisterra lighthouse beam sweeping across a stormy Atlantic sea at night, a small 1930s coastal steamer like
  the one in the reference image safe beyond the rocks, dawn breaking, no text
refs: misericordia lighthouse
image: gen-1794263968350.png

## ending_truth
prompt: wide night shot from the gallery of the Fisterra lighthouse: a woman in a dark oilskin coat seen from behind
  fires a red signal flare, its crimson glare lighting the wet rail and the storm; below, a revenue cutter's white
  searchlight beam cuts through the rain and fixes a dark coastal steamer with a green sidelight, turning away; waves
  break white on black rocks; the granite lighthouse tower frames the view, no text
refs: uxia misericordia lighthouse
image: gen-1794263091086.png

## ending_dark
prompt: black stormy Atlantic sea, the unlit Fisterra lighthouse on the cliff behind, wreckage in the distance, no text
refs: lighthouse
image: gen-1794279784949.png
crop: 0 0 100 75

## pena_talk
prompt: on the wet cliff path below the Fisterra lighthouse at night, a tense conversation: an ordinary Galician
  villager in his fifties in a plain grey wool coat and flat cap, weathered face, holding a small worn cigarette case,
  the keeper facing him, storm clouds and the dark lighthouse tower behind, no text
refs: pena
image: gen-1794340316471.png
crop: 0 6 100 63

## elias_talk
prompt: the lamp room at the top of the Fisterra lighthouse at night, the ghost of an old keeper standing at the great
  brass Fresnel lens, solid clearly drawn figure with sharp visible facial features and deep-set eyes, grey beard,
  weathered pale grey-blue skin, heavy salt-stained slate-blue coat, faint cool blue rim light instead of a white glow,
  only his boots fading into thin mist, the new keeper facing him, rain on the gallery glass, no text
refs: elias
image: gen-1794568170322.png
crop: 0 6 100 63

# References

## lighthouse
prompt: reference sheet of a tall square granite lighthouse tower at Fisterra, weathered grey stone blocks, a white
  gallery with an iron railing, a glass lantern room with a domed roof, small dark windows down the tower, a broad stone
  base, three-quarter view, whole tower visible, isolated on a flat dark navy background, crisp black outlines, no
  water, no text
image: gen-1794278979936.png

## misericordia
prompt: reference sheet of a small 1930s Galician coastal steamer, dark hull with a white stripe, green sidelight,
  single funnel, three-quarter side view, whole ship visible, isolated on a flat dark navy background, crisp black
  outlines, no water, no text
image: gen-1794255887899.png
seed: 42

## uxia
prompt: reference sheet of a Galician woman in her late thirties, dark oilskin coat, soaked dark hair, holding an oil
  lantern, three-quarter view, isolated on a flat dark navy background, crisp black outlines, no water, no text
image: gen-1794255109914.png
seed: 42

## elias
prompt: reference sheet of the ghost of a tall weathered Galician lighthouse keeper in his sixties, solid clearly drawn
  spectral figure, visible facial features and deep-set eyes, weathered pale grey-blue skin, grey beard, salt-crusted
  hair, heavy salt-stained slate-blue coat, faint cold blue rim light instead of a white glow, only his lower legs
  fading into thin mist, three-quarter view, full figure, isolated on a flat dark navy background, crisp dark outlines,
  no water, no text
image: gen-1794565578145.png

## pena
prompt: reference sheet of an ordinary Galician coastal villager in his fifties, weathered ruddy face, tired eyes, flat
  wool cap, plain grey wool coat, work trousers, damp leather boots, holding a small worn cigarette case, three-quarter
  view, full figure, isolated on a flat dark navy background, crisp black outlines, no water, no text
image: gen-1794337864221.png


# Items

## key
name: Llave de latón
desc: Un pequeño llavero de latón del impermeable de Elías.
  Ya abrió el cofre del mar. -> if chest_open
  Podría abrir el cofre del mar. -> unless chest_open
opt: Abrir el cofre del mar -> chest inscene cellar if cellar_lit if exam_chest unless chest_open set chest_open msg La llave gira con un chasquido arenoso. La tapa se levanta.

## oil_lantern
name: Farol de aceite
desc: Un farol de latón con chimenea de cristal.
  La mecha arde sin problemas. -> if cellar_lit
  La mecha está seca. Necesita una cerilla. -> unless cellar_lit
opt: Encender el farol -> - inscene cellar if matches unless cellar_lit set cellar_lit msg La mecha prende. Una pequeña llama aparta la oscuridad.

## oil_can
name: Lata de aceite
desc: Una lata de aceite de lámpara, medio llena.
  Suficiente para la gran lámpara.
opt: Llenar el depósito de la lámpara -> - inscene lamp_room if exam_reservoir unless oiled set oiled leave oil_can msg El depósito bebe el aceite y se asienta.

## matches
name: Cerillas
desc: Una caja de cerillas húmeda.
  Las cabezas están secas.
opt: Encender la gran lámpara -> ending_light inscene the_hour if lens_repaired if oiled msg La cerilla arde. La mecha prende.

## gear
name: Engranaje de latón
desc: Un engranaje envuelto en tela engrasada.
  Encaja en el giro de la lente.
opt: Colocar el engranaje de latón -> - inscene lamp_room if exam_lens unless lens_repaired set lens_repaired leave gear msg El engranaje encaja. La lente gira con un suave clic.

## flare
name: Bengala de señales
desc: Una bengala roja en un tubo encerado.
  Lanzada desde la galería, se vería desde tierra.
opt: Lanzar la bengala -> ending_truth inscene the_hour if know_truth msg La bengala silba al encenderse.

# Scenes

## start
name: Juego de demostración
art: title
music: theme
text:
  Fisterra. 14 de octubre de 1936, casi medianoche.
  Has subido el último kilómetro desde el pueblo.
  El faro está apagado.
  Una mujer espera junto a la puerta con un farol.
opt: Llamarla -> uxia_door msg Tu voz se pierde entre el viento y el oleaje.
opt: Subir al faro -> hall
opt: Cómo jugar -> help
opt: Acerca de -> about

## uxia_door
name: Uxía Mariño
art: cliff_path
text:
  Tiene treinta y tantos años, con impermeable negro.
  "Tú eres el nuevo farero. Soy Uxía Mariño. Elías era mi padre."
  "La {{Misericordia|exam_misericordia}} llega a medianoche."
  Dice el nombre demasiado rápido. -> if exam_misericordia
  "Hay que encender la lámpara."
opt: "¿Por qué estás aquí?" -> - msg Mira más allá de ti, hacia el faro. "Alguien tiene que cuidarlo."
opt: "¿Qué le pasó a Elías?" -> - msg El viento se lleva su respuesta. "Se ahogó en octubre. Nunca lo encontraron."
opt: "Encenderé la lámpara." -> hall set uxia_trusted msg Uxía dice "Gracias"
opt: Pasar a su lado hacia la torre -> hall

## hall
name: El vestíbulo del farero
art: hall
text:
  Sal, piedra mojada, ceniza fría.
  Un {{abrigo de hule|exam_coat}} cuelga junto a la puerta.
  Algo pesado cuelga del bolsillo. -> if exam_coat unless key
  Un farol de aceite está en el estante. -> unless oil_lantern
  Las escaleras suben hacia la oscuridad.
opt: Coger el llavero -> - if exam_coat unless key pick key msg El aro está frío. Dos llaves pequeñas y una placa de latón torcida.
opt: Coger el farol -> - unless oil_lantern pick oil_lantern msg El cuerpo de latón está bien, pero la chimenea está agrietada.
opt: Ir a la cocina -> kitchen
opt: Abrir la puerta del sótano -> cellar
opt: Subir a la sala de la lámpara -> lamp_room

## kitchen
name: La cocina del farero
art: cottage
text:
  Un fuego de leña crepita. Dos {{tazas|exam_cups}} en la mesa.
  Una aún está caliente. -> if exam_cups
  Uxía mira el mar junto a la ventana. -> unless uxia_left
  Un {{diario|exam_journal}} abierto está a su lado.
  La última entrada tiene la esquina arrancada. -> if exam_journal
opt: Leer la entrada rota -> journal if exam_journal
opt: Registrar la despensa -> pantry
opt: Hablar con Uxía -> uxia_talk unless uxia_left
opt: Salir al jardín -> garden
opt: Volver al vestíbulo -> hall

## journal
name: El diario de Elías
art: cottage
text:
  La letra es apretada y apresurada.
  Casi todo es tiempo y mareas.
  La {{última entrada|know_truth}} tiene la esquina arrancada.
  "La Misericordia no es un barco de socorro." -> if know_truth
  "Tabaco, brandy, rifles." -> if know_truth
  "Me pagaron para apagar la luz el catorce." -> if know_truth
  "Si hablo, se llevarán a Uxía." -> if know_truth
opt: Volver a la cocina -> kitchen

## pantry
name: La despensa
art: cottage
text:
  Estantes de carne en lata, té y aceite de lámpara.
  Una lata de aceite está en el estante. -> unless oil_can
  Una caja de cerillas está al lado. -> unless matches
  Una pequeña ventana da al mar negro.
opt: Coger la lata de aceite -> - unless oil_can pick oil_can msg La lata pesa lo suficiente para una noche.
opt: Coger las cerillas -> - unless matches pick matches msg Las cabezas suenan secas en la caja.
opt: Volver a la cocina -> kitchen

## cellar
name: El sótano
art: cellar
text:
  Las escaleras terminan en una oscuridad fría.
  Hueles a parafina, sal y cuerda vieja.
  Está demasiado oscuro para buscar. -> unless cellar_lit
  El farol parpadea. -> if cellar_lit
  Un {{cofre del mar|exam_chest}} con hierro está contra la pared. -> if cellar_lit
  La cerradura es vieja. Una llave podría girarla. -> if exam_chest unless chest_open
  Un cuaderno de bitácora descansa sobre una caja. -> if cellar_lit
opt: Leer el cuaderno de bitácora -> logbook if cellar_lit
opt: Registrar el cofre abierto -> chest if chest_open
opt: Subir al vestíbulo -> hall

## chest
name: El cofre del mar
art: cellar
text:
  La tapa se abre con un crujido.
  Un engranaje de latón envuelto en tela engrasada. -> unless gear
  Una bengala de señales roja. -> unless flare
  Una {{carta doblada|exam_letter}} está dentro.
  La letra no es la de Elías. -> if exam_letter
opt: Coger el engranaje -> - unless gear pick gear
opt: Coger la bengala -> - unless flare pick flare
opt: Leer la carta -> letter if exam_letter
opt: Cerrar el cofre -> cellar

## letter
name: La carta
art: cellar
text:
  "Mantén la luz apagada el {{catorce|know_truth}} y la deuda queda saldada."
  La misma noche en que Elías se ahogó. -> if know_truth
  "Si hablas, tu {{hija|exam_daughter}} lo pagará."
  Sabían lo de Uxía. -> if exam_daughter
  Sin firma.
opt: Volver al cofre -> chest

## logbook
name: El cuaderno de bitácora
art: cellar
text:
  Las páginas están hinchadas por la humedad.
  "Misericordia. Tres viajes este otoño."
  "Carga: tabaco, brandy, rifles."
  Todas las entradas están firmadas {{E.M.|know_truth}}.
  El catorce está rodeado en rojo. -> if know_truth
opt: Volver al sótano -> cellar

## lamp_room
name: La sala de la lámpara
art: workshop
text:
  La gran lente llena la sala como una ola.
  La {{lente Fresnel|exam_lens}} está entera y gira bien. -> if lens_repaired
  La {{lente Fresnel|exam_lens}} está entera, sin engranaje. -> unless lens_repaired
  El {{depósito|exam_reservoir}} está lleno de aceite. -> if oiled
  El {{depósito|exam_reservoir}} está seco. -> unless oiled
  La mecha está seca. La lluvia golpea el cristal. El mar es blanco.
  Una figura espera junto a la lente. -> unless elias_rested
  Un hombre de gris espera en el sendero. -> unless pena_defied
opt: Bajar al vestíbulo -> hall
opt: Hablar con la figura de la lente -> elias unless elias_rested
opt: Esperar a medianoche -> the_hour

## elias
name: La figura junto a la lente
art: elias_talk
text:
  Una figura alta está junto a la lente, blanca de sal.
  "No grites", dice. "Los muertos son tímidos."
  La voz es la de Elías Mariño, o lo que queda de ella.
  Ya has hablado con él antes. -> if asked_elias
opt: "¿Qué pasó el catorce?" -> - set asked_elias msg "Mantuve la luz veintidós años. Un hombre de gris descubrió lo que temía. Me pagaron para apagarla. Aun así intenté encenderla. Me esperaban."
opt: "¿Por qué aceptaste el dinero?" -> - set asked_elias msg "Uxía. Dijeron que se llevarían a Uxía."
opt: "¿Quién te pagó?" -> - set asked_elias msg "Un hombre de abrigo gris. Botas secas. Una pitillera de plata."
opt: "¿Cómo reparo la lámpara?" -> - set asked_elias msg "El engranaje está en el cofre del mar. El aceite, en la despensa. Lo demás es valor."
opt: "Tengo tu diario." -> - if know_truth set asked_elias msg "Entonces lo sabes. Enciéndela, farero. Termínalo."
opt: Descansa, Elías. -> lamp_room set elias_rested msg La figura inclina la cabeza y el frío abandona la sala.

## garden
name: El jardín del acantilado
art: garden
text:
  Un jardín amurallado, salpicado por el mar.
  Una {{tumba|exam_grave}} espera bajo el muro.
  "Elías Mariño. Murió el 14 de octubre de 1935." -> if exam_grave
  Abajo, As Agullas rompen en blanco.
  Un hombre de gris espera en el sendero. -> unless pena_defied
opt: Hablar con el hombre de gris -> pena unless pena_defied
opt: Volver a la cocina -> kitchen

## uxia_talk
name: Uxía
art: cottage
text:
  {{Uxía|exam_uxia}} está junto a la ventana con los brazos cruzados.
  No deja de mirar la puerta. -> if exam_uxia
  "Mi padre cuidó esta luz veintidós años", dice.
  "No habría dejado que se apagara."
opt: Prometer que encenderás la lámpara -> - unless uxia_trusted set uxia_trusted msg "Uxía asiente una vez. "Entonces tenemos una oportunidad.""
opt: Preguntar por su padre -> - unless asked_father set asked_father msg "Me echó el octubre pasado. Nunca volví a verlo."
opt: Contarle lo que has encontrado -> - if know_truth unless uxia_told set uxia_told msg "Pones el diario en la mesa. Uxía lo lee dos veces. Su cara no cambia. "Me echó por ellos", dice."
opt: "Lo siento. Te amenazaron." -> uxia_after if uxia_told unless uxia_knows set uxia_knows msg "Uxía se seca los ojos. "Si piensas avisar al guardacostas, necesitarás esto. Me lo dio el año pasado.""
opt: "Lo sabías, ¿verdad?" -> kitchen if uxia_told unless uxia_left set uxia_left msg ""No lo conocías", dice. "No finjas que sí.""
opt: Dejarla -> kitchen

## uxia_after
name: Un entendimiento
art: cottage
text:
  Uxía sostiene una bengala roja. -> unless flare
  Ya tienes la bengala del cofre del mar. -> if flare
  La lluvia repica en la ventana.
opt: Coger la bengala -> - unless flare pick flare msg La bengala está caliente por su abrigo.
opt: Subir a la sala de la lámpara -> lamp_room

## the_hour
name: Medianoche
art: workshop
text:
  El reloj del vestíbulo da las doce.
  Una {{luz verde|exam_green}} parpadea tras As Agullas.
  La luz de costado de un barco, verde contra el negro. -> if exam_green
  La Misericordia.
  La lámpara está lista. -> if lens_repaired if oiled if matches
  Las cerillas están en tu bolsillo. -> if matches
  La bengala está en tu mochila. -> if flare
opt: Dejar que la luz muera -> ending_dark msg Das un paso atrás y dejas que gane la oscuridad.
opt: Salir al sendero del acantilado -> pena unless pena_defied
opt: Bajar de nuevo -> lamp_room

## pena
name: Anxo Pena
art: pena_talk
text:
  Espera en el sendero, seco bajo la lluvia.
  Una pitillera de plata se cierra de golpe en su mano.
  "Buenas noches", dice. "¿La lámpara no da problemas?"
  No mira la torre. Te mira a ti.
opt: "¿Quién eres?" -> - set pena_met msg "Anxo Pena", dice. "Servicio de aduanas." La Misericordia llega a medianoche. Deja la luz apagada.
opt: "Le pagaste a Elías." -> - if know_truth set pena_met msg "Elías decidió", dice. "Ahora decides tú. Aún puedes elegir con sensatez."
opt: "Mantendré la luz apagada." -> - unless pena_offered set pena_met set pena_offered msg "Pena saca un sobre doblado del abrigo. "Para el farero", dice. "Por el silencio." Te lo tiende."
opt: Coger el sobre -> the_hour if pena_offered unless pena_deal set pena_deal msg El papel está seco y pesado. Lo guardas en el abrigo.
opt: "No te ayudaré." -> garden set pena_met set pena_defied msg "Pena te mira un largo instante. "No eres el primer farero que confunde terquedad con valor." Se pone el sombrero."
opt: No decir nada y volver -> garden

## ending_light
name: La luz
art: ending
ending: won
text:
  Colocas el engranaje. La lente tiembla y gira.
  La cerilla arde; la mecha prende; la lámpara reúne la oscuridad.
  Un haz blanco barre As Agullas, firme como un latido.
  La Misericordia responde con su sirena y se aleja.
  El guardacostas llega tarde; el pueblo despierta en calma.
  Te quedas con el diario de Elías. La verdad espera. -> if know_truth
  Uxía se queda hasta que mejora el tiempo. -> if uxia_knows
  Estás solo con la luz y las escaleras vacías. -> unless uxia_knows
opt: Empezar de nuevo -> start clear

## ending_truth
name: La verdad
art: ending_truth
ending: truth
text:
  Lanzas la bengala. Sube bajo la lluvia y estalla en rojo.
  La galería y la cara de Uxía se iluminan de carmesí.
  El guardacostas sale de la oscuridad con su reflector encendido.
  La Misericordia gira tarde; las cajas se parten. Al amanecer, hay policías en el faro.
  Uxía les cuenta todo. -> if uxia_knows
  Uxía se ha ido antes de que lleguen. -> if uxia_left
  Uxía no está aquí. -> unless uxia_knows unless uxia_left
  El nombre de Elías aparece en el periódico. -> if know_truth
opt: Empezar de nuevo -> start clear

## ending_dark
name: La oscuridad
art: ending_dark
ending: dark
text:
  Dejas que la lámpara muera.
  La luz verde alcanza As Agullas y desaparece.
  Bajas por el sendero. A tu espalda, el mar ruge.
  Al amanecer hay restos en la bahía.
  Y el diario de Elías en tu abrigo. -> if know_truth
  Pena te paga con billetes limpios. -> if pena_deal
  El hombre de gris no te mira. -> if pena_defied
opt: Empezar de nuevo -> start clear

## help
name: Cómo jugar
art: title
text:
  Muévete con las flechas o W/A/S/D.
  Pulsa ENTER para elegir. -> if system_zx
  Pulsa ENTER para elegir. -> if system_msx2
  Pulsa SPACE para el menú; ENTER o fuego elige. -> if system_cpc
  El botón 1 abre el menú; el botón 2 elige. -> if system_sms
  A abre el menú; B elige. -> if system_gb
  Las palabras resaltadas se examinan. Selecciona un objeto para usarlo.
  Los objetos están en la fila inferior o en el menú.
opt: Volver -> start

## about
name: Acerca de
art: title
text:
  Juego de demostración
  Un breve misterio en Fisterra, en la Costa da Morte gallega.
  Historia, arte y código creados para la demo.
opt: Volver -> start
