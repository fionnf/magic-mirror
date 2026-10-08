"""Mirror settings shared by the mirror (main.py), the AI client and the website.

Stored in panel_setup/mirror_settings.json (git-ignored) and re-read on every use, so changes
made in the web app apply to the very next photo with no restart.

  tone        0 (kind) .. 50 (cheeky, the default) .. 100 (affectionate roast)
  language    one of LANGUAGES
  recognise   greet enrolled people by name (opt-in; needs people enrolled in the app)
  smile       sparkles when someone smiles
  idle_art_minutes  nobody in front of the mirror for this long -> show art; 0 = never
  learn_faces keep fingerprints of unnamed faces that keep turning up, so they can be named in the
              app (OFF by default; see faces.py for exactly what is kept and for how long)
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(_HERE, "panel_setup", "mirror_settings.json")

LANGUAGES = {
    "English": "Reply in English.",
    "Deutsch": "Antworte auf Deutsch.",
    "Züridütsch": "Antworte uf Schwiizerdütsch (Züridütsch), mit Dialäkt-Uusdrück.",
    "Français": "Réponds en français.",
    "Drama queen": "Reply in English as the most dramatic, over-the-top drama queen alive.",
}
DEFAULTS = {"tone": 50, "language": "English", "recognise": True, "smile": True,
            "learn_faces": False, "idle_art_minutes": 10}


def load():
    try:
        with open(FILE) as fh:
            s = {**DEFAULTS, **json.load(fh)}
    except Exception:
        s = dict(DEFAULTS)
    try:
        s["tone"] = max(0, min(100, int(s["tone"])))
    except (TypeError, ValueError):
        s["tone"] = 50
    if s["language"] not in LANGUAGES:
        s["language"] = "English"
    try:
        s["idle_art_minutes"] = max(0, min(240, int(s["idle_art_minutes"])))
    except (TypeError, ValueError):
        s["idle_art_minutes"] = 10
    for k in ("recognise", "smile", "learn_faces"):
        s[k] = bool(s[k])
    return s


def save(updates):
    s = load()
    for k in DEFAULTS:
        if k in updates:
            s[k] = updates[k]
    s = {k: s[k] for k in DEFAULTS}
    tmp = FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(s, fh)
    os.replace(tmp, FILE)
    return load()


def tone_line(tone):
    """A sentence for the persona that sets how kind or roasty the line should be."""
    if tone <= 15:
        return "Be warm, sweet and encouraging - pure compliments, no teasing at all."
    if tone <= 40:
        return "Be kind and playful; gentle teasing at most."
    if tone <= 65:
        return "Be cheeky and playful, a mix of compliment and tease."
    if tone <= 85:
        return "Be sassy and teasing; roast lightly, but with obvious affection."
    return "Give a savage but affectionate roast: witty, specific, never cruel about bodies or identity."


def language_line(language):
    return LANGUAGES.get(language, LANGUAGES["English"])
