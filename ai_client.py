"""Claude (Anthropic API) calls for the wall: the mirror one-liner (vision), aura readings (vision +
structured output), photobooth pose prompts, and a small shared JSON helper used elsewhere.
Every call has a timeout and a fallback; usage is logged to config.USAGE_LOG.

Needs ANTHROPIC_API_KEY in .env. Model: config.AI_MODEL (claude-opus-5-5). Thinking is always on
for that model, so output depth is set with output_config.effort ("low" for these short lines).
Server-side refusal fallbacks are enabled (fallbacks="default") so a declined request is re-run on
a fallback model inside the same call instead of failing.
"""
import os
import io
import json
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
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _get_client():
    """One shared Anthropic client: reuses the connection and avoids re-importing."""
    global _client
    if _client is None:
        try:
            from dotenv import load_dotenv
            load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
        except Exception:
            pass
        import anthropic
        _client = anthropic.Anthropic(timeout=config.AI_TIMEOUT_SEC + 5, max_retries=1)
    return _client


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or _client is not None


def warm_up() -> None:
    """Import the SDK and build the client in the background at startup (the first import in a
    fresh environment can take longer than the reply limit)."""
    def run():
        try:
            _get_client().models.retrieve(config.AI_MODEL)   # cheap metadata call: warms TLS too
        except Exception:
            pass                                             # best effort only
    _executor.submit(run)


def _frame_to_b64_jpeg(frame: np.ndarray) -> str:
    if frame.ndim == 3 and frame.shape[2] == 3:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    else:
        rgb = frame
    img = Image.fromarray(rgb)
    img.thumbnail((512, 512))          # keeps image tokens low
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _image_block(frame: np.ndarray) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": _frame_to_b64_jpeg(frame)}}


def _log_usage(tokens_in: int, tokens_out: int) -> None:
    try:
        with open(config.USAGE_LOG, "a") as f:
            f.write(f"{datetime.datetime.now().isoformat()}\t{tokens_in}\t{tokens_out}\n")
    except Exception as e:
        print(f"[AI] usage log write failed: {e}")


def _text_of(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def ask(system: str, content, max_tokens: int = 2048, effort: str = "low", schema: dict = None,
        timeout: float = None):
    """One Claude call. `content` is a string or a list of content blocks. With `schema`, the reply
    is guaranteed to be JSON matching it (structured output) and is returned parsed.
    Returns (text_or_dict, input_tokens, output_tokens). Raises on refusal or API errors."""
    client = _get_client()
    kwargs = dict(model=config.AI_MODEL, max_tokens=max_tokens, system=system,
                  output_config={"effort": effort},
                  messages=[{"role": "user", "content": content}],
                  betas=[FALLBACK_BETA], fallbacks="default")
    if schema is not None:
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    if timeout is not None:
        client = client.with_options(timeout=timeout)
    try:
        resp = client.beta.messages.create(**kwargs)
    except TypeError:                                   # an older SDK without `fallbacks`
        kwargs.pop("fallbacks", None)
        kwargs.pop("betas", None)
        resp = client.beta.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("declined: " + str(getattr(resp.stop_details, "category", "") or ""))
    text = _text_of(resp)
    out = json.loads(text) if schema is not None else text
    usage = resp.usage
    return out, int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)


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
    text, tin, tout = ask(_persona(),
                          [{"type": "text", "text": ("Look at this person and speak. " + hint).strip()},
                           _image_block(frame)],
                          max_tokens=1024, effort="low", timeout=config.AI_TIMEOUT_SEC)
    return text.strip().strip('"\''), tin, tout


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
    schema = {"type": "object", "properties": {"prompts": {"type": "array", "items": {"type": "string"}}},
              "required": ["prompts"], "additionalProperties": False}
    j, _, _ = ask(config.BOOTH_AI_PROMPT_SYSTEM, f"Give me {n} pose directions for this session.",
                  max_tokens=1024, effort="low", schema=schema, timeout=config.AI_TIMEOUT_SEC)
    cleaned = []
    for ln in j.get("prompts", []):
        words = str(ln).strip(" -*•\"'").split()
        if not words:
            continue
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
    if not config.BOOTH_USE_AI_PROMPTS or not available():
        return random.sample(config.BOOTH_FALLBACK_PROMPTS, k=n)
    start = time.monotonic()
    future = _executor.submit(_call_booth_prompts, n)
    try:
        prompts = future.result(timeout=config.AI_TIMEOUT_SEC + 2)
        if len(prompts) < n:
            pool = [p for p in config.BOOTH_FALLBACK_PROMPTS if p not in prompts]
            extras = random.sample(pool, k=min(n - len(prompts), len(pool)))
            prompts = prompts + extras
        print(f"[AI] booth prompts ({time.monotonic() - start:.2f}s): {prompts}")
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
AURA_SCHEMA = {"type": "object",
               "properties": {"colour": {"type": "string"}, "hex": {"type": "string"},
                              "reading": {"type": "string"}},
               "required": ["colour", "hex", "reading"], "additionalProperties": False}


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
        "name (e.g. 'Rose Gold', 'Midnight Teal'). Give the colour name, a #rrggbb hex that matches it, "
        f"and a reading of at most 12 words, specific to what you see. {tone} {lang} "
        "Never mention body shape, age, ethnicity or identity.")


def _aura_call(frame: np.ndarray, hint: str):
    j, tin, tout = ask(_aura_prompt(),
                       [{"type": "text", "text": ("Read this person's aura. " + hint).strip()},
                        _image_block(frame)],
                       max_tokens=1024, effort="low", schema=AURA_SCHEMA, timeout=config.AI_TIMEOUT_SEC)
    _log_usage(tin, tout)
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
        print(f"[AI] aura {j['colour']} {j['hex']}: {j['reading']}")
        return j
    except Exception as e:
        print(f"[AI] aura fallback ({type(e).__name__}: {str(e)[:60]})")
        name, hexv, reading = random.choice(AURA_FALLBACKS)
        return {"colour": name, "hex": hexv, "reading": reading}
