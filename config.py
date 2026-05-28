# Panel hardware — 6× 64x64 panels in a 2-wide x 3-tall portrait layout.
PANEL_ROWS = 64
PANEL_COLS = 64
CHAIN_LENGTH = 6
PARALLEL = 1
# Pixel mapper depends on how you physically chain the panels. Tune to your
# wiring; see https://github.com/hzeller/rpi-rgb-led-matrix#chains for
# options. The default `U-mapper` is a good starting point for a serpentine
# chain (top-left → top-right → middle-right → middle-left → bottom-left →
# bottom-right). If the image is mirrored or split, try `"U-mapper;Rotate:180"`,
# `"V-mapper"`, or wire the panels differently.
PIXEL_MAPPER = "U-mapper"
SCAN_RATE = 32  # most 64x64 panels are 1/32 scan — confirm from sticker
HARDWARE_MAPPING = "adafruit-hat"
GPIO_SLOWDOWN = 1  # Pi 5 (RP1) needs 1; Pi 4 needs 4

# Total canvas: 2 panels wide x 3 panels tall = 128 wide x 192 tall (portrait)
TOTAL_WIDTH = 128
TOTAL_HEIGHT = 192

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

# Silhouette
BG_HISTORY = 500
BG_THRESHOLD = 50
SILHOUETTE_COLOUR = (0, 100, 255)
# Live silhouette is continuously rendered as the always-on background of the
# mirror. Refresh rate (Hz) for the capture/extract loop:
LIVE_SILHOUETTE_FPS = 12
# Absdiff threshold (0-255) used when a static background frame is available.
SILHOUETTE_DIFF_THRESHOLD = 30
# Dim factor applied to the live silhouette while text is overlaid.
SILHOUETTE_DIM_FACTOR = 0.3

# AI (OpenAI Chat Completions, vision-capable model)
AI_MODEL = "gpt-4o-mini"
AI_MAX_TOKENS = 80
AI_TIMEOUT_SEC = 10
MIRROR_PERSONA = (
    "You are mirror. In a flatshare entrance of a fun gay flatshare."
    "The person in the image is standing before you. "
    "Respond with a single short sentence (max 12 words) — "
    "It can be critical, motivational, but always specific to what you see. Make them very creative and sometimes htought provoking. Look especially at expressions. They can be a bit gay or naughty."
    "No quotation marks. No preamble."
)
AI_FALLBACK_MESSAGE = "The mirror sees all, but speaks slowly tonight."

# Display timing
IDLE_ANIMATION_FPS = 30
SILHOUETTE_DISPLAY_SEC = 1.5
MESSAGE_SCROLL_SPEED = 40  # pixels per second
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
TEXT_COLOUR = (255, 160, 50)
FONT_PATH = "assets/fonts/6x10.bdf"  # fallback to PIL default if missing

# Simulator (the window is now 128 x 192 logical px; scale 4 keeps it
# comfortably on a laptop screen at 512 x 768 + strip border)
SIM_SCALE = 4
SIM_TITLE = "Magic Mirror Simulator — 128x192"
SIM_STRIP_BORDER_PX = 18  # thickness of the strip border in the sim window

# Thermal receipt printer (optional, ESC/POS over USB). Use `lsusb` on the
# Pi to find the vendor/product IDs of yours; defaults match the GOOJPRT /
# Xprinter family that your existing slack printer uses.
PRINTER_VENDOR_ID = 0x0416
PRINTER_PRODUCT_ID = 0x5011
# 56mm paper @ 203dpi -> 384 printable dots. Drop to 360 if the right edge
# wraps; some clones lie about their printable width.
PRINTER_WIDTH_DOTS = 384
# Text wrap column at the chosen size. AI line printed at 1x bold = ~32 cols.
PRINTER_TEXT_COLS = 32
# width / height of the printed image. <1 = portrait; 0.75 = classic 3:4.
PRINTER_IMAGE_ASPECT = 0.75
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
