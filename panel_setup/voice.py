"""Voice control for the wall: say "Hey Fortuna, show West Cork".

Runs inside wall_control.py as one background thread. Fully offline: Vosk (a small speech model) listens
with a *restricted vocabulary* (the wake word, mode names and a few commands), so it is cheap enough for a
Pi and rarely hears things that were not said. No audio leaves the wall. The wall has no speaker, so there
is no spoken reply: what it heard and did is in the status (`/api/voice`) and the log.

One microphone, one reader at a time: a USB mic cannot be opened twice. Music mode, and art that moves to music
(Music tab: "let all art move to music"), need it, so voice PAUSES while they run (the Runner calls `set_hold`) and
picks the mic up again when something else is on. Art that is not listening to music never opens the mic.

Setup on the Pi: `pip install vosk` and `./assets/models/get_models.sh` (downloads the model, ~40 MB).
Turn it on in the app (`/api/voice`), or set `WALL_VOICE=1`.
"""
import json
import os
import random
import re
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODEL_DIR = os.environ.get("VOSK_MODEL") or os.path.join(ROOT, "assets", "models", "vosk-model-small-en-us-0.15")
SR = 16000
AI_MIN_GAP = 4.0                          # seconds between AI checks
AI_MAX_PER_HOUR = 30                      # a cost cap: chatter that sounds like the wake word cannot run up a bill
ARM_SECONDS = 4.5                         # "Hey Fortuna" alone: the command may follow within this long
VOICE_FLAG = os.path.join(HERE, "voice_awake.json")       # the wall's display reads this to show its listening glow
COOLDOWN = 1.5                            # ignore a repeat of the same trigger this soon after acting

# What Vosk may hear as the wake word. "fortuna" is not in every small model, so the in-vocabulary
# lookalikes count too; the wake word is only ever checked against these.
WAKE = ("fortuna", "fortune", "for tuna", "fortunes")
WAKE_PREFIX = ("hey", "hi", "okay", "ok", "a", "hay", "he")

# mode id -> extra things people say (the mode title is always included)
ALIASES = {
    "lava": ["lava", "coral", "lava and coral"],
    "daily": ["art of the day", "daily art", "todays art", "the daily"],
    "flow": ["flow", "the gallery"],
    "shaders": ["shaders"],
    "glass": ["light art", "long exposure light"],
    "art": ["art gallery", "ink flow"],
    "pride": ["pride", "pride show", "disco ball"],
    "welcome": ["welcome", "wheel of fortune"],
    "ambient": ["art and trams"],
    "trams": ["trams", "tram board", "tram times"],
    "snapshots": ["mirror photos", "photos", "pictures", "snapshots"],
    "kilchberg": ["kilchberg", "kilchberg trains"],
    "zurichhb": ["zurich", "zurich trains", "zurich hb", "main station"],
    "planes": ["planes", "aeroplanes", "aircraft"],
    "limmat": ["limmat", "the river", "river"],
    "exposure": ["long exposure"],
    "westcork": ["west cork", "cork", "ireland lights", "lighthouses"],
    "westcork_dusk": ["west cork dusk", "cork dusk", "dusk"],
    "windch": ["wind over switzerland", "swiss wind", "wind switzerland"],
    "windie": ["wind over ireland", "irish wind", "wind ireland"],
    "windeu": ["wind over europe", "european wind", "wind europe"],
    "nighttrains": ["night trains", "night train"],
    "issday": ["space station", "the iss", "iss"],
    "wanderers": ["ocean wanderers", "wanderers", "turtles"],
    "skylines": ["skylines", "skyline"],
    "polarbears": ["polar bears", "bears"],
    "snow": ["snow"],
    "satellites": ["satellites"],
    "tides": ["tides", "the tide", "tide"],
    "tramlines": ["tram map", "tram lines"],
    "laend": ["landle", "ländle", "laendle"],
    "quakes": ["earthquakes", "quakes", "earthquake"],
    "radar": ["rain radar", "the rain radar", "radar", "the radar", "is it going to rain", "will it rain", "rain"],
    "brief": ["brief", "the brief", "fortuna brief", "the fortuna brief", "daily brief", "morning brief", "the news", "news",
              "the weather", "weather", "weekend", "the weekend", "weekend forecast", "mountains", "mountain weather", "snow report",
              "summary", "daily summary", "what is happening", "whats happening"],
    "mirror": ["mirror", "mirror mode", "camera"],
    "lennart": [], "dewa": ["dewas story", "dewa"], "maeva": ["maeva", "maeva in zurich"],
    "maxfionn": ["max and fionn"], "cow": [], "livecam": ["live cam", "webcam"],
    "shapes": ["shapes"], "artsy": ["artsy"], "piece": [],
}
NO_VOICE = {"music"}        # modes voice may never start: Music mode listens to the room, and voice pauses while it runs
MUSIC_WORDS = ["music", "party", "dance"]
PRINT_WORDS = ["print", "printout", "print out"]
OFF_WORDS = ["off", "turn off", "go dark", "stop", "screen off"]
SLEEP_WORDS = ["sleep", "go to sleep", "goodnight", "good night", "night night", "bedtime"]
WAKE_UP_WORDS = ["wake up", "wake", "good morning", "rise and shine"]
RANDOM_WORDS = ["surprise me", "something else", "something different", "something new", "next", "random"]
VERBS = ["show", "show me", "play", "put on", "switch to", "go to", "start", "display", "open", "turn on", "please", "the"]


NUM_EN = {"zero": 0, "five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
          "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "half": 50, "full": 100, "maximum": 100, "max": 100}
LAMP_EN = ["dining table lamp", "dining lamp", "dining table light", "dining light", "table lamp"]


def _percent(words, nums):
    """'forty', 'twenty five', 'fifty percent', 'half' -> 40, 25, 50, 50; None when no amount was said."""
    total, seen = 0, False
    for w in words:
        if w in nums:
            n = nums[w]
            if seen and n in (5,) and total >= 20 and total % 10 == 0:     # twenty five
                total += n
            elif not seen or n in (50, 100):
                total = n
            seen = True
    return total if seen else None


def _norm(s):
    s = s.lower().replace("&", " and ")
    s = s.replace("ü", "u").replace("ö", "o").replace("ä", "a").replace("é", "e")
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


TABLES = {
    "en": {"wake": WAKE, "prefix": WAKE_PREFIX, "aliases": ALIASES, "off": OFF_WORDS, "sleep": SLEEP_WORDS, "wake_up": WAKE_UP_WORDS,
           "random": RANDOM_WORDS, "music": MUSIC_WORDS, "print": PRINT_WORDS, "verbs": VERBS,
           "light": ["lights", "light"], "on": ["on", "up"], "off_l": ["off", "out"], "english": [],  "german": [],
           "extra": ["lights", "light", "on", "up", "out", "percent"] + list(NUM_EN), "norm": _norm, "use_titles": True,
           "lamp": LAMP_EN, "nums": NUM_EN, "percent": ["percent", "per cent"]},
}


class Commands:
    """Turns a transcribed phrase into an action; no audio, no hardware, so it can be tested alone. One per language."""

    def __init__(self, modes, random_pool=None, lang="en"):
        # modes: [(id, category, title, description)]
        self.lang = lang
        self.T = TABLES[lang]
        self.norm = self.T["norm"]
        self.phrases = {}                               # normalised phrase -> mode id
        self.random_pool = random_pool or [m[0] for m in modes if m[1] == "Art" and m[0] not in ("piece", "art")]
        self.modes = [m for m in modes if m[0] not in NO_VOICE]
        off = {self.norm(w) for w in self.T["off"]}
        for mid, _cat, title, _d in self.modes:
            for p in ([title] if self.T["use_titles"] else []) + self.T["aliases"].get(mid, []):
                n = self.norm(p)
                if n and n not in off:
                    self.phrases.setdefault(n, mid)
        if self.T["use_titles"]:
            self.phrases.setdefault("mirror", "mirror")

    def vocabulary(self):
        """Everything Vosk is allowed to hear (words from all phrases, the wake word, "[unk]")."""
        T = self.T
        words = set(T["prefix"])
        for p_ in T["lamp"]:
            words.update(self.norm(p_).split())
        for w in T["wake"]:
            words.update(w.split())
        for p in (list(self.phrases) + T["off"] + T["sleep"] + T["wake_up"] + T["random"] + T["music"] + T["print"] + T["verbs"]
                  + T["extra"] + T["english"] + T["german"]):
            words.update(self.norm(p).split())
        return sorted(words) + ["[unk]"]

    def split_wake(self, text):
        """(heard_wake_word, rest_of_the_sentence)."""
        t = " " + self.norm(text) + " "
        best = None
        for w in self.T["wake"]:
            i = t.find(f" {w} ")
            if i >= 0 and w in ("fortune", "fortunes"):                  # an ordinary word: only "hey fortune", not "wheel of fortune"
                before = t[:i].split()
                if not before or before[-1] not in self.T["prefix"]:
                    i = -1
            if i >= 0 and (best is None or i < best[0]):
                best = (i, w)
        if best is None:
            return False, self.norm(text)
        return True, t[best[0] + len(best[1]) + 2:].strip()

    def parse(self, rest):
        """-> ("play", mode_id) | ("off", None) | ("random", mode_id) | ("blocked", None) | ("print", lang) | ("lights", bool) | ("sleep", None) | ("wake", None) | None."""
        T = self.T
        t = " " + self.norm(rest) + " "
        if not t.strip():
            return None
        has = lambda words: any(f" {self.norm(w)} " in t for w in words)
        if has(T["lamp"]):                               # the dining table lamp: on, off, or a brightness
            toks = t.split()
            amount = _percent(toks, T["nums"])
            if amount is not None:
                return ("lamp", amount)
            if has(T["off_l"]):
                return ("lamp", False)
            return ("lamp", True) if (has(T["on"]) or True) else None
        t_modes = t
        for ph in self.phrases:                          # a named mode ("light art") must not read as the lights command
            t_modes = t_modes.replace(f" {ph} ", " ")
        has_nm = lambda words: any(f" {self.norm(w)} " in t_modes for w in words)
        if has_nm(T["light"]):                           # the living-room lights (the colour rods are not touched)
            if has(T["off_l"]):
                return ("lights", False)
            if has(T["on"]):
                return ("lights", True)
        if has(T["sleep"]):                              # sleep: the living-room lights off and the wall to rest
            return ("sleep", None)
        if has(T["wake_up"]):                            # and back again
            return ("wake", None)
        if has(T["off"]):                                # "turn the music off" is off, not music
            return ("off", None)
        if has(T["print"]):                              # a paper slip
            return ("print", None)
        if has(T["music"]):
            return ("blocked", None)                     # "Hey Fortuna, music": not by voice
        for w in sorted(T["random"], key=len, reverse=True):
            if f" {self.norm(w)} " in t:
                return ("random", random.choice(self.random_pool)) if self.random_pool else None
        hits = {}
        for p, mid in self.phrases.items():              # which modes were named, and by how long a phrase
            if f" {p} " in t:
                hits[mid] = max(hits.get(mid, 0), len(p))
        if len(hits) == 1:
            return ("play", next(iter(hits)))
        return None                                      # nothing named, or several at once: not a clean command


class Voice:
    def __init__(self, runner, modes):
        self.runner = runner
        self.cmds = {"en": Commands(modes, lang="en")}
        self.enabled = False
        self.error = ""
        self.listening = False
        self.heard = ""                # the last thing the wall caught (with or without the wake word)
        self.last_action = ""          # e.g. "play westcork"
        self.last_time = 0.0
        self._stop = threading.Event()
        self._thread = None
        self._proc = None
        self._hold = threading.Event()   # set while Music mode (or music-reactive art) needs the microphone
        self._armed_until = 0.0
        self._acted = (0.0, "")
        self.models = {}                 # language -> the Vosk model that was loaded
        self.ai_on = True              # ask the AI when unsure (the Settings switch)
        self.ai_busy = False
        self.ai_calls = []             # times of recent AI checks
        self.ai_verdict = ""           # what the AI last decided, and why

    # -- on / off
    def set_enabled(self, on):
        on = bool(on)
        if on == self.enabled and (not on or (self._thread and self._thread.is_alive())):
            return
        self.enabled = on
        if on:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            self._stop.set()
            p, self._proc = self._proc, None
            if p and p.poll() is None:
                p.terminate()
            self.listening = False

    def set_hold(self, hold):
        """Let go of the microphone (hold=True) for Music mode, or take it back. Returns once it is free."""
        if hold:
            self._hold.set()
            p = self._proc
            if p and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=2)
                except Exception:
                    p.kill()
            self.listening = False
        else:
            self._hold.clear()

    def status(self):
        return {"enabled": self.enabled, "listening": self.listening, "paused": self._hold.is_set(), "error": self.error, "heard": self.heard,
                "last_action": self.last_action, "last_time": self.last_time, "ai": self.ai_verdict, "ai_on": self.ai_on, "wake_word": "Hey Fortuna",
                "languages": sorted(self.models)}

    # -- the listening loop
    def _device(self):
        try:
            from display.music import find_pi_mic
            return os.environ.get("WALL_VOICE_MIC") or find_pi_mic()
        except Exception:
            return None

    def _run(self):
        try:
            import vosk
            vosk.SetLogLevel(-1)
        except Exception:
            self.error = "voice needs 'pip install vosk'"
            self.enabled = False
            print(f"[voice] {self.error}", flush=True)
            return
        if not os.path.isdir(MODEL_DIR):
            self.error = "voice model missing: run ./assets/models/get_models.sh"
            self.enabled = False
            print(f"[voice] {self.error}", flush=True)
            return
        self.models = {"en": vosk.Model(MODEL_DIR)}
        grammars = {lang: json.dumps(self.cmds[lang].vocabulary(), ensure_ascii=False) for lang in self.models}   # umlauts as they are, not as \\u escapes
        while not self._stop.is_set():
            if self._hold.is_set():                               # Music mode has the microphone
                self._stop.wait(0.5)
                continue
            dev = self._device()
            if not dev:
                self.error = "no microphone found (needs a USB sound card or USB mic)"
                self.listening = False
                self._stop.wait(5)
                continue
            recs = {lang: vosk.KaldiRecognizer(m, SR, grammars[lang]) for lang, m in self.models.items()}
            self._proc = subprocess.Popen(["arecord", "-q", "-D", dev, "-f", "S16_LE", "-r", str(SR), "-c", "1",
                                           "-t", "raw"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            utt = bytearray()                                         # this utterance's audio, for the AI's second opinion
            pending = []                                              # what each language's recogniser made of the utterance
            self.error, self.listening = "", True
            print(f"[voice] listening on {dev} ({' + '.join(sorted(self.models))}), say 'Hey Fortuna'", flush=True)
            while not self._stop.is_set():
                data = self._proc.stdout.read(3200)               # 0.1 s
                if not data:
                    break
                utt += data
                if len(utt) > SR * 2 * 15:
                    del utt[:len(utt) - SR * 2 * 15]
                done = False
                for lang, rec in recs.items():                    # every language listens to the same audio
                    if rec.AcceptWaveform(data):
                        done = True
                        raw = json.loads(rec.Result()).get("text") or ""
                        text = raw.replace("[unk]", " ").strip()
                        if text:
                            pending.append((time.time(), lang, text, "[unk]" in raw, bytes(utt)))
                if done:
                    utt.clear()
                if pending and (len(recs) == 1 or len(pending) >= len(recs) or time.time() - pending[0][0] >= 0.35):
                    self._resolve(pending)                        # the languages finish a moment apart: decide once, together
                    pending = []
            self.listening = False
            if self._hold.is_set():
                continue                                          # let go on purpose, not an error
            err = (self._proc.stderr.read() or b"").decode(errors="replace").strip() if self._proc else ""
            if not self._stop.is_set():
                self.error = f"voice microphone stopped: {err[:100]}" if err else "voice microphone stopped"
                self._stop.wait(2)

    # -- the glow on the wall
    @staticmethod
    def signal(kind, secs):
        """Tell the display to glow for a while ("wake": listening, "think": the AI is deciding, "ok": it did something)."""
        try:
            tmp = VOICE_FLAG + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"until": time.time() + secs, "kind": kind}, fh)
            os.replace(tmp, VOICE_FLAG)
        except OSError:
            pass

    # -- from words to action
    def _resolve(self, items):
        """Several languages heard the same utterance: act on the one whose words make a real command. Each recogniser forces what
        it hears into its own words, so the wrong language mostly produces nonsense that does not parse; where both parse, the more
        specific command (not "random") and the one that understood more words win."""
        if len(items) == 1:
            _t, lang, text, unk, audio = items[0]
            return self._heard(text, unk, audio, lang)
        now = time.time()
        scored = []
        for it in items:
            woke, rest = self.cmds[it[1]].split_wake(it[2])
            if not woke and now >= self._armed_until:
                continue                                          # speech without the wake word: ignored
            act = self.cmds[it[1]].parse(rest) if rest else None
            scored.append((act, len(rest.split()), it))
        if not scored:
            return
        pool = [x for x in scored if x[0] is not None] or scored
        best = max(pool, key=lambda x: (0 if (x[0] is None or x[0][0] == "random") else 1, x[1]))
        _t, lang, text, unk, audio = best[2]
        self._heard(text, unk, audio, lang)

    def _heard(self, text, had_unk=False, audio=b"", lang="en"):
        now = time.time()
        cmds = self.cmds[lang]
        woke, rest = cmds.split_wake(text)
        self.heard = text
        if woke:
            self.signal("wake", ARM_SECONDS if (not rest and not had_unk) else 3.0)      # the wall lights up: it heard its name
            if not rest and not had_unk and getattr(self.runner, "asleep", False):        # asleep: just "Hey Fortuna" wakes it
                self.runner.wake_up()
                self.signal("ok", 1.4)
                self.last_action, self.last_time = "wake", now
                print("[voice] the wake word on its own: waking up", flush=True)
                return
            if not rest and not had_unk:                          # just "Hey Fortuna": the command may follow
                self._armed_until = now + ARM_SECONDS
                print("[voice] wake word, waiting for a command", flush=True)
                return
        elif now < self._armed_until:
            rest = text
            if had_unk or len(rest.split()) > 5:                  # a follow-up after "Hey Fortuna" is short and clean, not a conversation
                self._armed_until = 0.0
                return
        else:
            return                                                # speech without the wake word: ignored
        self._armed_until = 0.0
        act = cmds.parse(rest) if rest else None
        if act is not None and act[0] in ("play", "random") and woke and (had_unk or len(rest.split()) > 7):
            act = None                                            # a long or garbled sentence that merely contains a mode name
        if act is None:                                           # unsure: the AI decides whether it was real
            if now - self.last_time < 2.5:
                return                                            # the other language's recogniser just understood it
            if self.ai_on:
                self._ask_ai(rest or text, audio, lang)
            else:
                print(f"[voice] heard '{rest or text}': no command (AI check is off)", flush=True)
            return
        if act[0] == "blocked":
            self.ai_verdict = "music cannot be started by voice"
            print("[voice] music mode cannot be started by voice", flush=True)
            return
        self._do(act, rest, now)

    def _do(self, act, said, now=None):
        now = now or time.time()
        key = f"{act[0]} {act[1] or ''}".strip()
        if key == self._acted[1] and now - self._acted[0] < COOLDOWN:
            return
        self._acted = (now, key)
        self.last_action, self.last_time = key, now
        self.signal("ok", 1.4)                                    # a moment of green: understood
        print(f"[voice] '{said}' -> {key}", flush=True)
        try:
            if act[0] == "print":
                self.runner.print_brief(act[1])
            elif act[0] == "lights":
                self.runner.lights(bool(act[1]))
            elif act[0] == "sleep":
                self.runner.sleep_mode()
            elif act[0] == "wake":
                self.runner.wake_up()
            elif act[0] == "lamp":
                self.runner.lamp(act[1])
            else:
                self.runner.play("off" if act[0] == "off" else act[1])
        except Exception as e:
            self.error = f"could not run '{key}': {e}"

    # -- the AI second opinion (text only: no audio is ever sent)
    def _ask_ai(self, said, audio, lang="en"):
        now = time.time()
        self.ai_calls = [t for t in self.ai_calls if now - t < 3600]
        if (self.ai_busy or (self.ai_calls and now - self.ai_calls[-1] < AI_MIN_GAP)
                or len(self.ai_calls) >= AI_MAX_PER_HOUR):
            print(f"[voice] heard '{said}': not sure, AI check skipped (busy or at the hourly limit)", flush=True)
            return
        self.ai_calls.append(now)
        self.signal("think", 8.0)                                 # amber while the AI decides
        self.ai_busy = True
        threading.Thread(target=self._ai_worker, args=(said, audio, lang), daemon=True).start()

    def _free_text(self, audio, lang="en"):
        """The same audio again with no restricted vocabulary: it can hear words the grammar had to throw away."""
        model = self.models.get(lang)
        if not audio or model is None:
            return ""
        try:
            import vosk
            r = vosk.KaldiRecognizer(model, SR)
            r.AcceptWaveform(audio + b"\0" * SR)
            return (json.loads(r.FinalResult()).get("text") or "").strip()
        except Exception:
            return ""

    def _ai_worker(self, said, audio, lang="en"):
        try:
            free = self._free_text(audio, lang)
            verdict = judge(said, free, self.cmds["en"].modes)
            self.ai_verdict = f"'{free or said}': {verdict.get('reason', '')}"
            act, mode = verdict.get("action"), verdict.get("mode")
            ids = {m[0] for m in self.cmds["en"].modes}
            if not verdict.get("real_command") or act == "none":
                print(f"[voice] AI: passing talk, ignored ('{free or said}': {verdict.get('reason', '')})", flush=True)
            elif act == "play" and mode in ids and mode != "brief":
                self._do(("play", mode), f"{free or said} (AI)")        # the AI may pick art, nothing more
            else:
                print(f"[voice] AI: '{free or said}' needs a clear spoken command (printing, the brief, lights, sleep and off are not left to a guess)", flush=True)
        except Exception as e:
            self.ai_verdict = f"AI check failed: {e}"
            print(f"[voice] {self.ai_verdict}", flush=True)
        finally:
            self.ai_busy = False


def _schema(ids):
    return {
        "type": "object", "additionalProperties": False,
        "required": ["reason", "real_command", "action", "mode"],
        "properties": {
            "reason": {"type": "string", "description": "one short sentence"},
            "real_command": {"type": "boolean"},
            "action": {"type": "string", "enum": ["play", "off", "print", "sleep", "wake", "lights_on", "lights_off", "none"]},
            "mode": {"type": "string", "enum": list(ids) + [""], "description": "the art id when action is play, else empty"},
        },
    }


def judge(heard, free, modes):
    """Ask the AI: was this a real command to the wall, and which art does it mean? Text only."""
    import ai_client
    listing = "\n".join(f"{m[0]}: {m[2]} - {m[3]}" for m in modes)
    system = (
        "You are the ear of an LED art wall that people control by voice. Its wake word is 'Hey Fortuna'. "
        "Speech recognition runs on a small offline model and is often wrong, so you get two noisy transcripts of "
        "one utterance (the person speaks English): A (restricted vocabulary) and B (free). The wall heard its wake word (or something like it, "
        "e.g. 'fortune') in this utterance. Decide whether the person really spoke to the wall to ask for something, "
        "or whether this is passing conversation (the word 'fortune' in an ordinary sentence, people talking to each "
        "other, a song, TV). If it is a real request, choose action 'play' with the id of the art that best matches "
        "what they asked for (names may be misheard or described loosely: 'something with the sea' could be tides; "
        "match by meaning and by sound), or action 'off' if they want the wall switched off, or action 'print' if they ask for the brief or summary on paper (a printed slip), or 'sleep' for going to sleep or goodnight (lights off and the wall at rest), 'wake' for waking up, 'lights_on' / 'lights_off' for the living-room lights. If it is passing talk, "
        "or nothing in the list fits, action 'none' and mode ''. Be conservative: a mishearing or ordinary talk is 'none'; only a clear request to the wall is real. Never choose music, party or dance: the wall "
        "cannot be put into music mode by voice. Give a one-sentence reason. When action is 'play', mode must be one of the ids.\n\nAvailable art (id: title - description):\n"
        + listing)
    user = f"A (restricted): {heard!r}\nB (free): {free!r}"
    out, _i, _o = ai_client.ask(system, user, max_tokens=200, effort="low", schema=_schema(m[0] for m in modes), timeout=15)
    return out
