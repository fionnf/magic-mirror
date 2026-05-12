# Panel hardware
PANEL_ROWS = 32
PANEL_COLS = 64
CHAIN_LENGTH = 4
PARALLEL = 1
PIXEL_MAPPER = "U-mapper"
SCAN_RATE = 16
HARDWARE_MAPPING = "adafruit-hat"
GPIO_SLOWDOWN = 4

# Total canvas (2x2 U-mapped grid -> 128x64)
TOTAL_WIDTH = 128
TOTAL_HEIGHT = 64

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

# AI
AI_MODEL = "claude-opus-4-20250514"
AI_MAX_TOKENS = 80
AI_TIMEOUT_SEC = 10
MIRROR_PERSONA = (
    "You are an ancient magic mirror. "
    "The person in the image is standing before you. "
    "Respond with a single short sentence (max 12 words) — "
    "whimsical, slightly mysterious, and personal to what you observe. "
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

# Text rendering
TEXT_COLOUR = (255, 160, 50)
FONT_PATH = "assets/fonts/6x10.bdf"  # fallback to PIL default if missing

# Simulator
SIM_SCALE = 8
SIM_TITLE = "Magic Mirror Simulator — 128x64"

# Logging
USAGE_LOG = "usage.log"
