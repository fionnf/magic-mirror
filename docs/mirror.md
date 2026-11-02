# The mirror: photo and photobooth

In mirror mode the wall shows you, standing in front of it, in your own colours (a live silhouette from the camera).
It has exactly **two modes**: a plain **photo** and a **photobooth**. Start either from the app's **Mirror** tab
(*Start the mirror* or *Start the photobooth*); the service runs `main.py` with the right flags (`--no-touch --no-mqtt`, and `--booth` for the booth).
Everything on this page is in `main.py` (the state machine), `camera.py`, `vision.py`, `printer.py`, `hands.py` and `mirror_settings.py`.

## The two modes

| | Photo | Photobooth |
|---|---|---|
| Started by | the **Photo** tile, a tap, or an open palm | the **Photobooth strip** tile, a tap (in booth mode), a peace sign, or an open palm (in booth mode) |
| Sequence | 3, 2, 1 with a glowing frame, the flash, one photo | for each shot: 3, 2, 1, the flash, the photo (no prompts: just pose) |
| On the wall afterwards | the photo in colour for 5 s (no comment) or the AI line **appearing** over you (a fade-in, no scrolling, held long enough to read) | each photo full-screen in portrait, one after another, then all of them side by side |
| On paper | a portrait receipt: header, a framed photo, the AI line | one strip titled **HOUSE FORTUNA**: portrait photos, each the shape of a single printout, no numbers or captions, and a QR code |

**Photobooth mode** (the app's *Photobooth mode* switch, or *Start the photobooth*) makes the touch sensor and the Photo tile run the booth instead.
The wall then shows `PHOTOBOOTH` and a pulsing "high five to start" while it waits (an open palm starts it; so does a tap).

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

## The flash, timed with the photo

- **The border.** In mirror mode the wall always has a plain **2 LED warm-white frame** round its edge. It exists to light a raised hand for the hand-signal detector.
- **The countdown glows.** Round the dimmed silhouette the frame glows in time with 3, 2, 1: each number starts with a beat that fades, and the glow's floor rises with every count, so the flash feels charged.
- **The flash.** A 0.35 s pre-glow (the camera meters for the lit scene), then two whole frames at full power: the frame at full brightness and the whole wall washed warm gold (`FLASH_WARM = (255, 222, 158)`).
  **The photo is taken during those frames**: the wall simply holds the flash while the camera exposes. After a short hold the light decays like a flash tube (the wash in about 0.15 s, the glow in 0.5 s).
- Exposure: the camera is normally locked (see Flicker). During the flash `Camera.light_auto()` lets it meter, and `capture_still()` fixes the exposure it just metered for the exposure itself; `light_restore()` puts the locked values back afterwards.

### Setting up the gallery page's styled view (one time, 5 minutes)

The page works at once, but until it has a Google **API key** it shows the Drive folder inside a styled frame. With a key it lists the folder itself and draws the grid and big view above:

1. Google Cloud console (the project your Drive uploads use), *APIs & Services, Credentials, Create credentials, API key*.
2. Edit the key: *Application restrictions: Websites*, add `https://fionnf.github.io/*`; *API restrictions: Google Drive API*. (The key sits in the public page, which is fine because it can only call the Drive API from that website, and only reads folders that are shared by link.)
3. Give it to the site: `gh variable set GALLERY_API_KEY --body <the key>` in the repository (or *Settings, Secrets and variables, Actions, Variables*), then run the *Fortuna gallery* workflow (or push anything under `site/`). `tools/build_gallery.py` puts the key into `p/index.html`.

## Resolution: pictures are saved as the camera took them

A photo is taken in the camera's **still mode at the sensor's full resolution** (`config.STILL_SIZE`, 4608 x 2592 on a Camera Module 3), then cut to portrait around the people: about 1944 x 2592, 5 megapixels.
The live silhouette stays small and fast; only the photo is full size, and the live picture pauses for about a second while the camera switches mode. If the still cannot be taken the live frame is used (and the log says so).
Saved photos are JPEGs at `config.PHOTO_JPEG_QUALITY` (95, no chroma subsampling), about 2 to 4 MB each:

- `photos/receipt_*.jpg` (single photos) and `photos/strip_*_shotN.jpg` (every booth shot) at full resolution, plus `_thumb.jpg` (640 px) copies for the app's grid and the slideshow, and a small JSON each;
- Google Drive, if set up, gets the full-resolution originals too ([google-drive.md](google-drive.md));
- the printer and the AI get downscaled copies (they do not need more).

**Storage: a budget on the wall, Drive keeps the originals.** At about 3 MB a photo a USB stick is not needed. Every photo is uploaded to Drive in full size; the wall keeps a **budget** of full-size photos (More: *Photos on the wall*, `photos_gb`, default 1 GB, or `WALL_PHOTOS_MAX_GB`).
When the pictures on the wall go over it, the **oldest pictures that Drive has confirmed** are replaced in place by a small 640 px copy (`photo_store.prune`, run after every upload): the app's grid and the slideshow keep showing them, the original is in Drive. A photo is only shrunk after its upload succeeded (recorded in `photos/.backed_up.json`), so
anything not yet in Drive, or taken while the wall is offline or Drive is not set up, keeps its full size. Strips and the JSON files are never shrunk. Further safeguards: the Mirror tab shows what the pictures take, how much is backed up and how much disk is free;
below 400 MB free the mirror stops saving new pictures instead of filling the card; `WALL_PHOTOS_DIR` in `.env` moves the whole folder to a USB stick or SSD (mount it, e.g. at `/mnt/photos`).

## What it says

The AI line (4 to 9 words) comes from `ai_client.get_mirror_message`. The prompt (`config.MIRROR_PERSONA`) asks for one concrete thing it can see, with a twist; it is told the weekday, the time of day and the
month, who is in the picture if people are enrolled, whether they smile, and the last eight lines it said so it does not repeat itself. Tone (sweet to roast) and language are settings.
The photobooth no longer gives pose directions: the shots are just 3, 2, 1, flash. Turn the line off entirely with the **comment** switch ("no comment": the photo is shown and printed on its own).

**Write your own prompt.** The Mirror tab's *What it says* box (More: *Voice, faces and quiet hours*) holds the mirror's instructions in plain words, starting with the built-in ones (`config.MIRROR_PERSONA`). Edit them and press Save (`prompt` in `mirror_settings.json`); *Back to the built-in* restores them. Your text replaces the built-in persona **and** the random "voice for this photo" (`config.MIRROR_STYLES`: a nature-documentary narrator, a movie trailer, a sommelier...), so describe the voice yourself. The tone slider, the language and a fixed safety tail (`config.MIRROR_RULES`: one short line, no remarks about bodies or anything a person cannot choose) are always added after it.

## A look through the camera (More tab, without mirror mode)

*More, Look through the camera, Look now* shows what the wall's camera sees, live, like a webcam: from the sofa or from anywhere you can reach the app (outside the home network it needs the wall's password like everything else).
It works with the mirror off: the camera is opened only while someone is watching and closed 10 seconds after the last viewer leaves (`camera_live.py`). The camera is opened by a **small helper process** (`python3 camera_live.py --worker`), never by the web server itself: if the camera layer fails or crashes, only the helper dies, the app stays up and tells you why (the error text is shown under the picture; the helper's own output is in `panel_setup/logs/camera_live.log`). It is a light stream, about 6 pictures a second at 640 px (`/api/camera/live.mjpg`; `/api/camera/snapshot.jpg` gives one picture).
If the mirror is running it owns the camera, so the live view then takes its pictures from the mirror (`/api/frame.jpg` on the mirror's port); starting the mirror closes the live view's own camera first.
It is never hidden: **while anyone is watching, a small red dot blinks in the top-right corner of the wall** (`play.py` reads `panel_setup/liveview.on`, which the live view touches every second), the app says so, and each viewer is logged (`[camera] live view opened by <address>`).

## Sharing links from the app (More tab, *Share*)

- **Write on the wall**: the guest-message page (`/d`, works on the home Wi-Fi: by name, `http://<hostname>.local/d`, and by address). *Share* opens the phone's share sheet; *Copy* puts the link on the clipboard.
- **Photo galleries**: one Drive link per day (today's first), each opening that day's pictures in full size and no other day. The list comes from Drive (`cloud_uploader.list_day_folders`, `GET /api/share`); today's folder is made if it does not exist yet.
  It is the same link the QR code on a printed strip carries. Anyone who has a day's link can see that whole day, so share the right one.

## Settings (the Mirror tab and More tab; `panel_setup/mirror_settings.json`, re-read at every use, no restart)

| Key | Default | What it does |
|---|---|---|
| `tone` | 50 | 0 sweet, 50 cheeky, 100 affectionate roast |
| `language` | English | English, Deutsch, Züridütsch, Français, Drama queen |
| `comment` | on | The mirror says a line about you with every photo. Off = just the photo |
| `prompt` | empty | Your own instructions for what the mirror says (empty = the built-in prompt) |
| `photos_gb` | 1 | How many GB of full-size photos to keep on the wall; beyond it the oldest ones already in Drive shrink to small copies |
| `booth_shots` | 3 | Photos in one strip (2 to 6) |
| `booth_repeat` | off | Photobooth mode keeps going: another strip 7 s after the last while someone is still in front; it stops by itself 30 s after everyone has left |
| `gesture` | on | Hand signals |
| `smile` | on | Sparkles around a smiling face |
| `recognise`, `learn_faces` | on, off | Greet enrolled people by name; suggest names for regulars (see the panel_setup README) |
| `idle_art_minutes`, `wake_on_motion` | 10, off | Show art when nobody has been there for this long |

## Where the pictures go

- `photos/` on the Pi (never deployed, git-ignored): every photo and strip with a small JSON next to it.
- **Google Drive**, if set up ([google-drive.md](google-drive.md)): the cloud copy, one folder per day, "Photobooth YYYY-MM-DD", readable by anyone with its link.
- **The gallery page** (`site/photos.html`, published at `<GALLERY_URL>p/`): the QR code on a printed strip and the links in the app's *Share* section open `…/p/#<the day's Drive folder>`, a nicely styled page for **that day only**:
  the pictures in a masonry grid, tap for a big view with the mirror's line and a **Download** button (the full-size original from Drive), and the printed strips underneath. The folder id is in the `#` part of the link, which browsers never send to any server,
  and the page only asks Drive for that one folder, so there is no way from one day to another. Anyone with the link can see that whole day: do not post it publicly if that matters.
  (A public gallery of every photo was deliberately not built: a page in a public repository cannot hide other days.) Switch to plain Drive links with the `gallery_page` setting.
- **Mirror photos**, an art mode in the gallery: a slideshow of every picture the mirror took, in random order (`display/slideshow.py`).
- The app's **Mirror** tab lists every photo under a heading for each day, newest first.
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
`GET/POST /api/mirror/settings` reads and sets the table above, `GET /api/camera/live.mjpg`, `/api/camera/snapshot.jpg` and `/api/camera/status` are the live view, `POST /api/mirror/crop` switches the smart portrait crop. The mirror itself listens on port 5000 (`api.py`) for `/api/trigger/short` and `/api/trigger/long`.
