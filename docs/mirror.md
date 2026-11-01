# The mirror: photo and photobooth

In mirror mode the wall shows you, standing in front of it, in your own colours (a live silhouette from the camera).
It has exactly **two modes**: a plain **photo** and a **photobooth**. Start either from the app's **Mirror** tab
(*Start the mirror* or *Start the photobooth*); the service runs `main.py` with the right flags (`--no-touch --no-mqtt`, and `--booth` for the booth).
Everything on this page is in `main.py` (the state machine), `camera.py`, `vision.py`, `printer.py`, `hands.py` and `mirror_settings.py`.

## The two modes

| | Photo | Photobooth |
|---|---|---|
| Started by | the **Photo** tile, a tap, or an open palm | the **Photobooth strip** tile, a tap (in booth mode), a peace sign, or an open palm (in booth mode) |
| Sequence | 3, 2, 1, the flash, one photo | for each shot: a pose direction on the wall, 3, 2, 1, the flash, the photo |
| On the wall afterwards | the photo in colour for 5 s (no comment) or the AI line scrolling over you | each photo full-screen in portrait with its pose direction, one after another, then all of them side by side |
| On paper | a portrait receipt: header, a framed photo, the AI line | one strip of portrait photos, each the shape of a single printout, numbered, with its pose direction, and a QR code |

**Photobooth mode** (the app's *Photobooth mode* switch, or *Start the photobooth*) makes the touch sensor and the Photo tile run the booth instead.
The wall then shows `PHOTOBOOTH` and a pulsing "tap to start" while it waits.

## Starting a photo without touching anything: hand signals

Hold a hand up to the wall and keep it there for about 1.3 seconds. A gold (open palm) or pink (peace sign) ring fills around your hand while you hold it.

| Signal | Starts |
|---|---|
| Open palm, all four fingers out | the photo sequence (in photobooth mode: the strip) |
| Peace sign (index and middle out, ring and little finger folded) | the photobooth strip |

How it works: `hands.py` runs two small OpenCV Zoo models (MediaPipe palm detection and hand landmarks, ~4 MB each, in `assets/models/`,
Apache-2.0) with OpenCV's own DNN, entirely on the Pi. A finger counts as out when its tip is clearly further from the wrist than its middle joint, whichever way up the hand is.
It checks about three times a second (0.12 to 0.19 s per check on a Pi 4), only while the mirror is waiting **and a person-sized silhouette is in front of it**
(an empty, noisy hall costs nothing), and a signal can fire at most every 6 seconds. Switch it off with the *Hand signal* switch in the app (`gesture`).
Missing models just turn the feature off (`assets/models/get_models.sh` fetches them; they are also committed).

## The flash

Every photo, single or booth, gets a **bright warm-white frame round the screen edge** (26 LEDs deep, `FLASH_WARM = (255, 242, 210)`), with your silhouette dimmed in the middle so you can still see yourself.
It swells in 0.18 s, holds while the photo is taken, and fades over a quarter of a second. The camera normally has its exposure locked (see Flicker below); during the flash
`Camera.light_auto()` lets it meter for the lit scene and `light_restore()` puts the locked values back afterwards, so a lit face is neither dark nor blown out.

## What it says

The AI line (4 to 8 words) comes from `ai_client.get_mirror_message`. The prompt (`config.MIRROR_PERSONA`) asks for one concrete thing it can see, with a twist; it is told the weekday, the time of day and the
month, who is in the picture if people are enrolled, whether they smile, and the last eight lines it said so it does not repeat itself. Tone (sweet to roast) and language are settings.
Photobooth pose directions (`config.BOOTH_AI_PROMPT_SYSTEM`) build from an easy warm-up to a grand finale, with a random "flavour" (telenovela, heist film, boy-band album cover...) and a list of recent ones to avoid;
`config.BOOTH_FALLBACK_PROMPTS` is used when there is no key. Turn the line off entirely with the **comment** switch ("no comment": the photo is shown and printed on its own).

## Settings (the Mirror tab and More tab; `panel_setup/mirror_settings.json`, re-read at every use, no restart)

| Key | Default | What it does |
|---|---|---|
| `tone` | 50 | 0 sweet, 50 cheeky, 100 affectionate roast |
| `language` | English | English, Deutsch, Züridütsch, Français, Drama queen |
| `comment` | on | The mirror says a line about you with every photo. Off = just the photo |
| `booth_shots` | 3 | Photos in one strip (2 to 6) |
| `booth_repeat` | off | Photobooth mode keeps going: another strip 7 s after the last while someone is still in front; it stops by itself 30 s after everyone has left |
| `gesture` | on | Hand signals |
| `smile` | on | Sparkles around a smiling face |
| `recognise`, `learn_faces` | on, off | Greet enrolled people by name; suggest names for regulars (see the panel_setup README) |
| `idle_art_minutes`, `wake_on_motion` | 10, off | Show art when nobody has been there for this long |

## Where the pictures go

- `photos/` on the Pi (never deployed, git-ignored): every photo and strip with a small JSON next to it.
- **Google Drive**, if set up ([google-drive.md](google-drive.md)): one folder per day, "Photobooth YYYY-MM-DD", readable by anyone with its link. The QR code on a printed strip opens it, so a guest can
  browse and download every picture the wall took that day. Anyone with the link can see the whole day: do not post it publicly if that matters.
- The printer, wherever it is ([printing.md](printing.md)).

## Flicker: what was done and what to tune

A mirror image is the hardest thing for an LED wall (live, noisy, always changing), so the mirror pipeline is built to be steady:

1. **Locked camera light.** After warm-up `Camera._lock_light()` freezes exposure, gain and white balance (exposure rounded to whole mains-flicker periods: `config.CAMERA_MAINS_HZ`, 50 in Europe, 60 in the US).
   Auto-exposure re-adjusting to every white shirt or dark coat was the biggest single cause of pumping. If the room's brightness stays more than 35% away from the locked value for a minute (lights on, sunset) it re-meters for two seconds and locks again.
2. **A steady picture.** `vision._detail` smooths the contrast stretch over time and blends each new frame into the last one *per pixel*: where little changed (noise, mains flicker) most of the old picture stays, where something moved the new frame wins, so a moving person does not smear.
   On a synthetic test this roughly halves the frame-to-frame shimmer of a standing person.
3. **Paced by the panels.** `MagicMirror._show()` draws every frame held for a whole number of panel refreshes (25 fps at the 100 Hz refresh), instead of sleeping on a timer that drifts against the refresh. The idle loop eases towards each new picture per pixel (a little for noise, fast for real movement).
4. **Light on the CPU.** OpenCV is limited to two threads so the panel driver keeps its cores, and hand detection only runs when a person is there. Check the load with `top -H` on the Pi: the realtime `rt` thread is the panel refresh.

If you still see flicker: check `[CAMERA] light locked: ... us, gain ...` in `panel_setup/logs/mirror.log` (a gain near 16 means the room is very dark: add light), try a different `MATRIX_REFRESH_LIMIT_HZ`/`MATRIX_PWM_BITS` (see the panel_setup README), and keep the mirror's silhouette dim in a dark room.

## API (the app uses these; port 80 on the Pi)

`POST /api/mirror` `{camera, booth}` starts the mirror (booth: true for the photobooth), `POST /api/mirror/photo` takes a photo, `POST /api/mirror/booth` takes a strip,
`GET/POST /api/mirror/settings` reads and sets the table above, `POST /api/mirror/crop` switches the smart portrait crop. The mirror itself listens on port 5000 (`api.py`) for `/api/trigger/short` and `/api/trigger/long`.
