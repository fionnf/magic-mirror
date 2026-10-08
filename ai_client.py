"""OpenAI vision call with timeout, fallback, and usage logging."""
import os
import io
import base64
import time
import datetime
import concurrent.futures
import numpy as np
import cv2
from PIL import Image
import config


_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_client = None


def _get_client():
    """One shared OpenAI client: reuses the connection and avoids re-importing."""
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


def warm_up() -> None:
    """Import the OpenAI SDK and build the client in the background at startup.

    The very first import in a fresh environment can take longer than the 10 s
    reply limit, which made the first photo fall back to the canned line."""
    def run():
        try:
            _get_client().models.retrieve(config.AI_MODEL)   # free metadata call: warms TLS too
        except Exception:
            pass                                             # best effort only
    _executor.submit(run)


def _frame_to_b64_jpeg(frame: np.ndarray) -> str:
    if frame.ndim == 3 and frame.shape[2] == 3:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    else:
        rgb = frame
    img = Image.fromarray(rgb)
    # downscale to keep token cost low — vision models scale by pixel count.
    img.thumbnail((512, 512))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _log_usage(tokens_in: int, tokens_out: int) -> None:
    try:
        with open(config.USAGE_LOG, "a") as f:
            f.write(f"{datetime.datetime.now().isoformat()}\t{tokens_in}\t{tokens_out}\n")
    except Exception as e:
        print(f"[AI] usage log write failed: {e}")


def _persona() -> str:
    """The mirror's voice: base persona + tone (kind..roast) + language, from the web app."""
    try:
        import mirror_settings as ms
        st = ms.load()
        return (config.MIRROR_PERSONA + " " + ms.tone_line(st["tone"]) + " "
                + ms.language_line(st["language"]))
    except Exception:
        return config.MIRROR_PERSONA


def _call_api(frame: np.ndarray, hint: str = "") -> tuple[str, int, int]:
    client = _get_client()
    b64 = _frame_to_b64_jpeg(frame)
    resp = client.chat.completions.create(
        model=config.AI_MODEL,
        max_tokens=config.AI_MAX_TOKENS,
        messages=[
            {"role": "system", "content": _persona()},
            {"role": "user", "content": [
                {"type": "text", "text": ("Look at this person and speak. " + hint).strip()},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                               "detail": "low"}},
            ]},
        ],
        timeout=config.AI_TIMEOUT_SEC,
    )
    text = (resp.choices[0].message.content or "").strip().strip('"\'')
    usage = resp.usage
    return text, usage.prompt_tokens, usage.completion_tokens


def get_mirror_message(frame: np.ndarray, hint: str = "") -> str:
    """Blocking call with timeout and fallback. `hint` carries facts the camera knows
    (a recognised name, a smile), e.g. "The person is called Fionn. They are smiling."."""
    start = time.monotonic()
    future = _executor.submit(_call_api, frame, hint)
    try:
        text, tin, tout = future.result(timeout=config.AI_TIMEOUT_SEC + 2)
        elapsed = time.monotonic() - start
        _log_usage(tin, tout)
        print(f"[AI] {elapsed:.2f}s tokens in={tin} out={tout}: {text}")
        return text or config.AI_FALLBACK_MESSAGE
    except concurrent.futures.TimeoutError:
        print(f"[AI] timeout after {config.AI_TIMEOUT_SEC}s")
        return config.AI_FALLBACK_MESSAGE
    except Exception as e:
        print(f"[AI] error: {e}")
        return config.AI_FALLBACK_MESSAGE


def get_mirror_message_async(frame: np.ndarray) -> "concurrent.futures.Future[str]":
    return _executor.submit(get_mirror_message, frame)


# ---- photobooth direction prompts ----

def _call_booth_prompts(n: int) -> list[str]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=config.AI_MODEL,
        max_tokens=120,
        messages=[
            {"role": "system", "content": config.BOOTH_AI_PROMPT_SYSTEM},
            {"role": "user",
             "content": f"Give me {n} pose directions for this session."},
        ],
        timeout=config.AI_TIMEOUT_SEC,
    )
    text = (resp.choices[0].message.content or "").strip()
    lines = [ln.strip(" -*•\"'") for ln in text.splitlines()
             if ln.strip(" -*•\"'")]
    # trim long words / strip stray punctuation, keep the first n
    cleaned = []
    for ln in lines:
        words = ln.split()
        if len(words) > config.BOOTH_PROMPT_MAX_WORDS:
            words = words[:config.BOOTH_PROMPT_MAX_WORDS]
        cleaned.append(" ".join(words).rstrip(".!?,;:"))
        if len(cleaned) == n:
            break
    return cleaned


def get_booth_prompts(n: int = 3) -> list[str]:
    """Return `n` short photobooth direction prompts. Falls back to the
    curated list in config on any failure (no API key, timeout, parse error)."""
    import random
    if not config.BOOTH_USE_AI_PROMPTS or not os.environ.get("OPENAI_API_KEY"):
        return random.sample(config.BOOTH_FALLBACK_PROMPTS, k=n)
    start = time.monotonic()
    future = _executor.submit(_call_booth_prompts, n)
    try:
        prompts = future.result(timeout=config.AI_TIMEOUT_SEC + 2)
        if len(prompts) < n:
            # top up from the fallback bank if the model gave fewer than asked
            pool = [p for p in config.BOOTH_FALLBACK_PROMPTS if p not in prompts]
            extras = random.sample(pool, k=min(n - len(prompts), len(pool)))
            prompts = prompts + extras
        print(f"[AI] booth prompts ({time.monotonic() - start:.2f}s): "
              f"{prompts}")
        return prompts
    except Exception as e:
        print(f"[AI] booth prompts failed ({e}); using fallback")
        return random.sample(config.BOOTH_FALLBACK_PROMPTS, k=n)


# ---------------------------------------------------------------- aura ---

AURA_FALLBACKS = [
    ("Rose Gold", "#E8A0A0", "Soft heart, fierce timing. Glowing."),
    ("Electric Violet", "#9B5DE5", "Main-character energy, quietly loading."),
    ("Sea Glass", "#7FD1B9", "Calm waters hiding a very sharp wit."),
    ("Sunset Amber", "#FFA94D", "Warm, a little chaotic, entirely magnetic."),
]


def _aura_prompt() -> str:
    try:
        import mirror_settings as ms
        st = ms.load()
        tone, lang = ms.tone_line(st["tone"]), ms.language_line(st["language"])
    except Exception:
        tone, lang = "", ""
    return (
        "You are the mirror of House Fortuna, a fun, warm gay flatshare, reading someone's AURA. "
        "Look at the person's outfit, expression and mood and choose ONE aura colour with a poetic "
        "name (e.g. 'Rose Gold', 'Midnight Teal'). Reply ONLY with JSON: "
        '{"colour": the colour name, "hex": a #rrggbb hex that matches it, "reading": '
        "a reading of at most 12 words, specific to what you see}. "
        f"{tone} {lang} Never mention body shape, age, ethnicity or identity.")


def _aura_call(frame: np.ndarray, hint: str):
    import json
    client = _get_client()
    b64 = _frame_to_b64_jpeg(frame)
    resp = client.chat.completions.create(
        model=config.AI_MODEL, max_tokens=160, temperature=1.0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": _aura_prompt()},
                  {"role": "user", "content": [
                      {"type": "text", "text": ("Read this person's aura. " + hint).strip()},
                      {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}",
                                                          "detail": "low"}}]}],
        timeout=config.AI_TIMEOUT_SEC)
    j = json.loads(resp.choices[0].message.content or "{}")
    hexv = str(j.get("hex", "")).strip()
    if not (len(hexv) == 7 and hexv.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in hexv[1:])):
        raise ValueError("no usable colour")
    return {"colour": str(j.get("colour", "Aura"))[:24], "hex": hexv,
            "reading": str(j.get("reading", ""))[:100].strip()}


def get_aura(frame: np.ndarray, hint: str = "") -> dict:
    """{'colour', 'hex', 'reading'}; a built-in aura if the AI is unavailable."""
    import random
    future = _executor.submit(_aura_call, frame, hint)
    try:
        j = future.result(timeout=config.AI_TIMEOUT_SEC + 2)
        _log_usage(0, 0)
        print(f"[AI] aura {j['colour']} {j['hex']}: {j['reading']}")
        return j
    except Exception as e:
        print(f"[AI] aura fallback ({type(e).__name__}: {str(e)[:60]})")
        name, hexv, reading = random.choice(AURA_FALLBACKS)
        return {"colour": name, "hex": hexv, "reading": reading}
