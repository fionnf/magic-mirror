# Ländle: the Remstal as a living map, and the Lennart film

Two pieces about Baden-Württemberg ("im Ländle"), both German-language, both personal to the author's friends. Rewrite or delete them for your own wall
(their entries are in `MODES` in `panel_setup/wall_control.py`).

## Ländle (`laend`, in the app under Art)

A long intro that plays once when the piece starts, then a living map of the Remstal that stays on the wall (Bittenfeld, Korb, Schorndorf, with Waiblingen, Winnenden and Backnang), with the live trains on it.
Code: `display/laend.py` (the map), `display/laend_intro.py` (the film), `display/laend_trains.py` (the trains), `tools/build_laend.py` (the map data).

### The intro (about 2 minutes, every caption in German)

`laend_intro.frame(t)` is a pure function of time. The scenes, in order: a yellow **"Nett hier. Fortunagasse 24. Aber warst du schon mal in Baden-Württemberg?" sticker** on a brick wall (after the real state-marketing slogan);
dawn over the Remstal; **Bittenfeld**, where Katha, Becky and Lennart pick apples in a Streuobstwiese (a counter, falling apples); **the vineyards** on the way to Korb; **Korb**, sunset on the Korber Kopf, where Katha gives Becky a plaster;
**Schorndorf**, half-timbered houses, fairy lights, Federweißer and Zwiebelkuchen, "Prost aufs Ländle!"; a night scene; and finally **the Wanderfeige** (the wild fig that is spreading through the area) overgrows everything, with a WANDER-FEIGE! title.
The friends are drawn in `person()` as little pixel figures with running jokes: Becky's heel blister (a speech bubble every few seconds until the plaster at `PLASTER_T`, thankful after), her chunky Salomon trail shoes, Lennart's TAGOS hiking gear.
Text uses a bold font with umlauts (`laend_intro.font()`: DejaVu on the Pi, Arial on a Mac). To change who is in it, edit `person()`, `CAPTIONS` and the scene functions; `LENGTH` is the total length in seconds.

### The map

Built once on a laptop by `python3 tools/build_laend.py` into `assets/maps/laend.npz` (about 1.2 MB, committed), so the wall needs no internet for it. North is up; 192 LEDs across is 20.5 km (107 m per LED), 256 LEDs is 27.4 km, centred on the valley.
Sources: AWS open terrain tiles (Mapzen Terrarium, zoom 12, for the relief) and OpenStreetMap through the Overpass API (vineyards, orchards, woods, built-up land, the Rems and its brooks, railways, stations, place names; (c) OpenStreetMap contributors, ODbL).
It is stored four times finer than the LEDs; at start the wall shades it into a night picture:

- hillshaded relief, valleys indigo, ridges warm;
- every **vineyard** as terrace lines that follow the contours, gold on sunlit slopes and plum in the shade;
- orchards as pale dots, woods as dark dither, towns as dark blocks with warm windows that breathe;
- the Rems as running blue water, brooks as a faint thread, the railway as a thin silver line;
- over it, every frame: evening fog lying in the valley and drifting (half resolution, sub-LED steps), fireflies, falling leaves and apples, and slow pulses from Bittenfeld, Korb and Schorndorf;
- the title "Ländle" and the place names (the three heroes bright with a dark halo, the neighbours dim);
- the map inks itself in from Korb outwards, and small **Wanderfeige colonies** start along the river and creep outwards very slowly for as long as the piece runs.

Everything per frame is a sparse update on precomputed pixel lists (a frame takes about 22 ms on the Pi 4; the first version took 77 ms and flickered). `DIM` in `laend.py` sets the overall brightness.

### Live trains

`laend_trains.py` shows the **S2** (red), the **S3** (orange) and the regional trains (blue: MEX 13/19, RE 90, ...) moving on the real track, with a `LIVE n` counter in the corner (`NO DATA` when offline).

- **Data**: the VVS departure monitor (EFA, `https://www3.vvs.de/mngvvs/XML_DM_REQUEST`, open, no key), polled every minute on a side thread for 11 stations along the Remstal and Murr valley lines (only while the piece is showing).
  Every departure carries its real, delay-corrected time. The same trip appears at several stations, which is what makes the positions possible.
- **Track**: the OpenStreetMap railway in the map file is turned into a graph; a shortest path through it joins station to station, and both corridors (Remstal: Waiblingen to Schorndorf; Murr valley: Waiblingen to Backnang) run on to the edge of the map.
- **Position**: between two stations a train is placed by interpolating the times at those stations along the track; beyond its first or last station it carries on at line speed. If the feed contradicts itself (times that do not run along the line one way) only the stop nearest to now is trusted.
  Each train is a bright head with a fading tail and a dark halo so it stands out from the busiest hillside.
- Trains only show when their stations list them within about seven minutes, so at night there are few.

To move the map: change `LON0`, `LAT_C` and `M_PER_LED` in `tools/build_laend.py`, the place list `PLACES`, and the station lists `REMS`, `MURR` and `POLL` in `laend_trains.py`, then rerun the builder.

## Lennart zeigt Fionn das Ländle (`lennart`, under Shows)

A standalone comedy of about 128 seconds (it loops), `display/lennart_film.py`, German captions and speech bubbles. Lennart shows Fionn the Ländle; Fionn steals apples (a counter) and Lennart holds him back; Fionn loves the Fachwerk; is amazed there are no hedges and walks across other people's Stückle, chased by a farmer;
steals grapes until his pockets are purple; looks for the sea and "finds" it three times (fog, the Schwäbische Alb, a duck pond); meets the vineyard mafia, whom Lennart pays off in apples; Karlstein at sunset, a kiss; and home in Bittenfeld under a blanket by the fire.
It reuses the backgrounds from `laend_intro.py`; its own people (Fionn, Lennart, a farmer, a mafioso) are in `_body()`.
