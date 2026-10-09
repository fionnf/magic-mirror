import os
# Panel hardware — up to 12× 64x64 panels (256 mm square) in a 3-wide x 4-tall
# portrait layout, all on ONE chain from the Adafruit HAT.
PANEL_ROWS = 64
PANEL_COLS = 64
PANELS_WIDE = 3
PANELS_TALL = int(__import__("os").environ.get("WALL_PANELS_TALL", 3))   # 3 now; the full wall is 4 (192 x 256).
#                 WALL_PANELS_TALL=4 previews the full wall in the simulator; set 4 here when the row is wired
CHAIN_LENGTH = PANELS_WIDE * PANELS_TALL
PARALLEL = 1
# The built-in rpi-rgb-led-matrix mappers can't do a 3-column serpentine, so
# the driver runs the chain as a flat (64*12) x 64 strip and remaps the image
# in software (see led_matrix.py). Leave PIXEL_MAPPER empty.
PIXEL_MAPPER = ""
# Physical chain order, as (col, row) of each panel starting at the one the
# HAT cable plugs into. Currently a row serpentine starting at the bottom-left
# (see below). Edit to match your wiring; check with
# panel_setup/display_test.py --pattern numbers.
PANEL_CHAIN_ORDER = [            # row serpentine from the bottom-left, any number of rows
    (c if (PANELS_TALL - 1 - r) % 2 == 0 else PANELS_WIDE - 1 - c, r)
    for r in range(PANELS_TALL - 1, -1, -1) for c in range(PANELS_WIDE)
]
# 3 rows: (0,2) (1,2) (2,2) | (2,1) (1,1) (0,1) | (0,0) (1,0) (2,0)  - chain 0-2, 3-5, 6-8
# ^ measured on the wall (photo 2026-10-07): the cable enters at the BOTTOM-LEFT
#   panel and snakes by rows. Add the 4th row here when it is connected.
# Per-panel rotation in degrees (0/90/180/270) keyed by chain index, for
# panels mounted upside down. Missing = 0.
# Middle row (chain 3-5) is mounted upside down.
PANEL_ROTATE = {3: 180, 4: 180, 5: 180}
SCAN_RATE = 32  # most 64x64 panels are 1/32 scan — confirm from sticker
# CONFIRMED WORKING on Pi 4B (Fortuna) with the P3 64x64 FM6124 panels:
#   hardware_mapping "regular", gpio_slowdown 3, panel_type FM6126A, pwm_bits 7
# (FM6124 panels need the FM6126A init sequence, otherwise they stay dark/garbled.)
HARDWARE_MAPPING = "regular"
GPIO_SLOWDOWN = 7   # 7 = cleanest first panel (fewer data errors); refresh ~59.6 Hz max, locked at 58
                    # history: 3 streaky, 4 better, 5 good, 6 clean (~67 Hz), 8 = ~57 Hz banding returns
                    # 8 = ~57 Hz banding returns. 6-bit at slowdown 6 = ~77 Hz but colour banding.
MATRIX_PANEL_TYPE = "FM6126A"
# Long chain => low refresh rate. These are the main tuning knobs:
MATRIX_BRIGHTNESS = int(__import__("os").environ.get("WALL_BRIGHTNESS", 40))  # 0-100; the web panel sets WALL_BRIGHTNESS
# Power budget. PSU is 40 A @ 5 V; keep headroom for the Pi and wiring losses.
# The driver estimates current per frame from pixel values x brightness and
# scales the frame down if it would exceed MATRIX_MAX_AMPS.
MATRIX_MAX_AMPS = 28.0
# Conservative full-white draw of ONE 64x64 panel at 100% brightness (typical
# 3-4 A; measure yours and adjust).
MATRIX_AMPS_PER_PANEL = 4.0
MATRIX_PWM_BITS = 7            # 1-11; fewer bits = much higher refresh
MATRIX_PWM_DITHER_BITS = 0      # 0-2: smoother gradients at low pwm_bits, costs refresh
MATRIX_PWM_LSB_NS = 130        # lower = faster refresh (try 100-300)
MATRIX_REFRESH_LIMIT_HZ = 58   # lock refresh: animations at 29 fps = exactly 2 refreshes per frame (no judder)
MATRIX_MULTIPLEXING = 0        # change if the image looks striped/scrambled
MATRIX_ROW_ADDRESS_TYPE = 0    # 64x64 panels with ABCDE addressing: usually 0
MATRIX_SHOW_REFRESH = False    # print refresh rate to stdout

# Per-panel colour calibration (written by panel_setup/calibrate_colour.py).
# Per-panel, per-channel gains applied through a 256-entry LUT; missing file or
# MATRIX_APPLY_PANEL_GAINS=False = no correction.
PANEL_GAINS_FILE = "panel_setup/colour_calibration.json"
MATRIX_APPLY_PANEL_GAINS = True

# Total canvas: 3 panels wide x 4 panels tall = 192 wide x 256 tall (portrait)
TOTAL_WIDTH = PANELS_WIDE * PANEL_COLS
TOTAL_HEIGHT = PANELS_TALL * PANEL_ROWS

# GPIO — capacitive touch sensor (e.g. TTP223) wired to BUTTON_PIN.
# Most capacitive touch modules output HIGH on touch; set TOUCH_ACTIVE_HIGH=True.
# If your module is configured for active-LOW output, flip this.
BUTTON_PIN = 25
BUTTON_DEBOUNCE_MS = 300
TOUCH_ACTIVE_HIGH = True
# Many capacitive modules drive the line themselves and need no pull resistor.
# Set to "up", "down", or "off" depending on your module's output stage.
TOUCH_PULL = "down"

# Camera
CAMERA_WARMUP_SEC = 2
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
# Every captured frame is centre-cropped to this width/height ratio, so the AI,
# the receipt and the silhouette all see the same portrait picture.
CAMERA_ASPECT = 3 / 4
# Photos (AI / receipt / booth) are cut to portrait around the people (face detector, then motion,
# then centre). Set False to always centre-crop.
SMART_CROP = os.environ.get("WALL_SMART_CROP", "1") != "0"   # the web app sets WALL_SMART_CROP

# Silhouette
BG_HISTORY = 500
BG_THRESHOLD = 50
SILHOUETTE_COLOUR = (0, 210, 110)   # green (was blue (0, 100, 255))
# Live silhouette is continuously rendered as the always-on background of the
# mirror. Refresh rate (Hz) for the capture/extract loop:
LIVE_SILHOUETTE_FPS = 10
# Absdiff threshold (0-255) used when a static background frame is available.
SILHOUETTE_DIFF_THRESHOLD = 30
# Silhouette maths runs on this small size (w, h), not the full frame.
SILHOUETTE_PROC_SIZE = (160, 120)
# Flip the live silhouette left-right so the wall acts like a mirror. Only the
# display is flipped; photos for the AI / receipts stay as the camera saw them.
SILHOUETTE_MIRROR = True
# Dim factor applied to the live silhouette while text is overlaid.
SILHOUETTE_DIM_FACTOR = 0.2

# AI (Claude via the Anthropic API; vision-capable). Needs ANTHROPIC_API_KEY in .env
# The daily artist's mood board: a public Pinterest board, "user/board" (read via its RSS feed)
MOODBOARD = __import__("os").environ.get("WALL_MOODBOARD", "fionnferreira/motion-graphics")
AI_MODEL = "claude-opus-5-5"
AI_MAX_TOKENS = 30
AI_TIMEOUT_SEC = 10
MIRROR_PERSONA = (
    "You are the mirror in the entrance of a fun gay flatshare. "
    "The person in the image is standing before you. "
    "Reply with ONE very short line of 3 to 7 words. "
    "It can be critical, motivational, cheeky or thought-provoking, but always "
    "specific to what you see - look especially at expressions, outfit and pose. "
    "It can be a bit gay or naughty. Vary your openings; never start with "
    "'Embrace'. No quotation marks. No preamble."
)
AI_MAX_WORDS = 8   # hard cap applied after the reply comes back
AI_FALLBACK_MESSAGE = "The mirror sees all, but speaks slowly tonight."

# Display timing
IDLE_ANIMATION_FPS = 24
SILHOUETTE_DISPLAY_SEC = 1.5
MESSAGE_SCROLL_SPEED = 85  # pixels per second (bigger font = longer line)
MESSAGE_HOLD_SEC = 4
FADE_OUT_SEC = 1.0
TRIGGER_FLASH_MS = 50
# Photo-illumination flash. Both the matrix and the strip light up bright
# white just before the camera grabs the frame, then stay on briefly after
# so the flash doesn't feel "snapped". Total visible flash ≈ pre + post.
PHOTO_FLASH_PRE_MS = 220   # warm-up window for camera auto-exposure
PHOTO_FLASH_POST_MS = 180  # tail so the flash reads as a flash, not a blip

# Photobooth mode — long-press the touch sensor for LONG_PRESS_MS ms.
LONG_PRESS_MS = 2000
BOOTH_PHOTO_COUNT = 3
BOOTH_PER_PHOTO_COUNTDOWN = 3      # seconds (3-2-1 per shot)
BOOTH_PHOTO_HEIGHT = 280           # printed height in dots per photo
BOOTH_DISPLAY_SEC = 3              # strip on matrix after print
BOOTH_INTER_PHOTO_PAUSE_MS = 400   # tiny breath between shots
# Ask GPT for 3 short pose directions to show before each shot. Falls back
# to the curated list below if the API call fails.
BOOTH_USE_AI_PROMPTS = True
BOOTH_PROMPT_HOLD_SEC = 2.0          # how long each prompt stays on screen
BOOTH_PROMPT_MAX_WORDS = 6
BOOTH_AI_PROMPT_SYSTEM = (
    "You are directing a quick photobooth session in a flatshare hallway. "
    "Give exactly THREE short pose directions, one per line, no numbering, "
    "no quotes. Each direction should be max 6 words, imperative, playful, "
    "varied in mood (cheeky, dramatic, silly, sweet). Examples: "
    "'Best regal pose', 'Pretend you just lost your keys', "
    "'Fake-laugh at the worst joke', 'Show me chaos'."
)
BOOTH_FALLBACK_PROMPTS = [
    "Best regal pose",
    "Pretend you saw a ghost",
    "Fake-laugh at a joke",
    "Show me chaos",
    "Most mysterious look",
    "Act like a statue",
    "Pretend it's freezing",
    "Strike a power pose",
    "Look casually heartbroken",
    "Sing silently and loud",
]

# Text rendering
# Warm white with a black outline: readable over the live silhouette.
TEXT_COLOUR = (255, 235, 170)
TEXT_FONT_SIZE = 30                 # px; the wall is 192 px tall
TEXT_FONT_PATHS = [                 # first one that exists is used
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
TEXT_STROKE_WIDTH = 2               # black outline around letters (0 = off)
TEXT_STROKE_COLOUR = (0, 0, 0)
FONT_PATH = "assets/fonts/6x10.bdf"  # legacy fallback

# Simulator (the window is now 192 x 256 logical px; scale 4 keeps it
# comfortably on a laptop screen at 576 x 768 + strip border)
SIM_SCALE = 3
SIM_TITLE = "Magic Mirror Simulator — 192x256"
SIM_STRIP_BORDER_PX = 18  # thickness of the strip border in the sim window

# Thermal receipt printer (optional, ESC/POS over USB). Use `lsusb` on the
# Pi to find the vendor/product IDs of yours; defaults match the GOOJPRT /
# Xprinter family that your existing slack printer uses.
# Where the printer is: "usb" (on this Pi), "http://<other-pi>:8631" (another Pi in the room running
# tools/print_server.py), "tcp://<ip>:9100" (Wi-Fi printer) or "serial:/dev/rfcomm0" (Bluetooth).
# WALL_PRINTER in .env overrides it. Print quality settings live in print_out.py.
PRINTER = __import__("os").environ.get("WALL_PRINTER", "usb")
PRINTER_VENDOR_ID = 0x0416
PRINTER_PRODUCT_ID = 0x5011
# 57 mm paper: 48 mm printable at 203 dpi = 384 dots, the printer's full resolution. Drop to 360 if the right edge
# wraps; some clones lie about their printable width.
PRINTER_WIDTH_DOTS = 384
# Text wrap column at the chosen size. AI line printed at 1x bold = ~32 cols.
PRINTER_TEXT_COLS = 32
PRINTER_MESSAGE_FONT_SIZE = 34   # AI message on the receipt (px at 203 dpi)
PRINTER_HEADER_FONT_SIZE = 20
# width / height of the printed image. <1 = portrait; 0.75 = classic 3:4.
PRINTER_IMAGE_ASPECT = 0.75   # width/height of the printed photo (0.75 = 3:4 portrait)
PRINTER_TIMEOUT_MS = 0  # 0 = libusb default
# Bold header line printed above the timestamp. Empty string to omit.
PRINTER_HEADER = "FORTUNAGASSE 24"
# Image-tonemapping knobs. Thermal printers crush midtones to pure black,
# so we pre-process with a small autocontrast stretch + gamma boost + a
# Floyd–Steinberg dither for proper greyscale-looking output.
PRINTER_IMAGE_AUTOCONTRAST = 1   # 0-5, percentile to crop from each end
PRINTER_IMAGE_GAMMA = 0.7        # <1 brightens midtones; lower = brighter
PRINTER_IMAGE_BRIGHTNESS = 1.1   # multiplicative; 1.0 = unchanged
PRINTER_IMAGE_CONTRAST = 1.1     # multiplicative; 1.0 = unchanged
PRINTER_IMAGE_SHARPEN = True     # subtle unsharp pass before dithering

# Logging
USAGE_LOG = "usage.log"

# MQTT broker — runs on the Pi alongside the mirror process.
# Browsers connect via WebSocket on MQTT_WS_PORT; the mirror uses MQTT_PORT.
# Mosquitto config needed:
#   listener 1883
#   listener 9001
#   protocol websockets
MQTT_HOST   = "localhost"
MQTT_PORT   = 1883
MQTT_WS_PORT = 9001   # WebSocket port for browser access
MQTT_PREVIEW_INTERVAL_SEC = 1.0  # JPEG-encodes a frame each time; keep it slow

# Addressable LED strip (SK6812 RGBWW) around the mirror frame — optional.
# Driven by rpi_ws281x. If the library is missing or the strip won't init,
# the rest of the project keeps running with no strip behaviour at all.
#
# Pin choice matters: the Adafruit Matrix HAT uses GPIO 18 / PWM, so DON'T
# use the rpi_ws281x default (also GPIO 18 / PWM). Use SPI MOSI on GPIO 10
# instead — `rpi_ws281x` supports SPI, no PWM conflict. You may need to
# enable SPI in raspi-config and set `core_freq=250` in
# /boot/firmware/config.txt for stable timing.
LED_STRIP_COUNT = 600          # total LEDs around the perimeter
LED_STRIP_PIN = 10            # GPIO 10 = SPI0 MOSI; safe with the HAT
LED_STRIP_DMA = 10
LED_STRIP_CHANNEL = 0         # SPI channel
LED_STRIP_BRIGHTNESS = 180    # 0-255
LED_STRIP_FPS = 30
# Warm-white base level (0-255) when no hue band is active.
LED_STRIP_WARM_LEVEL = 70
# Hue drift cycles per second. Keep very low — the colour should feel like
# it's barely changing; one full rotation every couple of minutes.
LED_STRIP_HUE_SPEED = 0.008
# Width of the silhouette hue band as a fraction of strip length. Wider
# values produce a softer, less localised glow.
LED_STRIP_BAND_FRACTION = 0.45
# How aggressively the band tracks the silhouette. 0 = frozen, 1 = snaps
# instantly. Low values give that slow organic drift.
LED_STRIP_CENTROID_SMOOTHING = 0.015
# Peak intensity of the coloured band relative to full RGB. Lower = subtler.
LED_STRIP_BAND_INTENSITY = 0.55
# A tiny low-frequency wobble (two summed sines) is added to the band centre
# so it breathes a bit even when the person is perfectly still.
LED_STRIP_WOBBLE_AMPLITUDE = 0.04  # fraction of strip length
LED_STRIP_WOBBLE_HZ = (0.07, 0.11)  # two coprime-ish slow frequencies

# Google Drive archive (optional — uploads skipped if no auth file present)
# Two auth modes are supported. Set whichever fits your account:
#   1. OAuth user credentials (works on Workspace accounts blocked from
#      service-account key creation). Run `tools/auth_drive.py` on your
#      laptop once to generate `token.json`; copy it to the Pi.
#   2. Service-account JSON (works on personal Gmail / orgs without
#      iam.disableServiceAccountKeyCreation). Drop the downloaded key as
#      `gcp-credentials.json` in the project root.
# The uploader checks OAuth token first, then service account.
GOOGLE_OAUTH_TOKEN_PATH = "token.json"
GOOGLE_OAUTH_CLIENT_PATH = "oauth_client.json"
GOOGLE_CREDENTIALS_PATH = "gcp-credentials.json"
# Folder ID comes from .env (GOOGLE_DRIVE_FOLDER_ID)
