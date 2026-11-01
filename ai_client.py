"""Claude (Anthropic API) calls for the wall: the mirror one-liner (vision), photobooth pose prompts, and a small shared JSON helper used elsewhere.
Every call has a timeout and a fallback; usage is logged to config.USAGE_LOG.

Needs ANTHROPIC_API_KEY in .env. Model: config.AI_MODEL (claude-opus-5-5). Thinking is always on
for that model, so output depth is set with output_config.effort ("low" for these short lines).
Server-side refusal fallbacks are enabled (fallbacks="default") so a declined request is re-run on
a fallback model inside the same call instead of failing.

A cheaper provider is the default now (config.AI_PROVIDER = "openai", model config.AI_OPENAI_MODEL,
key OPENAI_API_KEY in .env; "groq" works too with GROQ_API_KEY): the art of the day, its curator, the music brain and the mirror lines all
go through ask(). Set WALL_AI_PROVIDER=anthropic to use Claude again.
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


def provider() -> str:
    """The chosen provider, or Claude when the chosen one has no key but Claude has (a missing
    OPENAI_API_KEY secret must not cost the day its piece)."""
    p = (os.environ.get("WALL_AI_PROVIDER") or getattr(config, "AI_PROVIDER", "anthropic")).lower()
    if p != "anthropic":
        _load_env()
        if not os.environ.get(_compat(p)[1]) and os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
    return p


def model_name(art: bool = False) -> str:
    """The model behind a call (an edition records the one that made its piece: art=True)."""
    if provider() == "anthropic":
        return config.AI_MODEL
    if art and provider() == "openai":
        return os.environ.get("WALL_OPENAI_ART_MODEL", config.AI_OPENAI_ART_MODEL)
    return _compat(provider())[2]


_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    except Exception:
        pass


def available() -> bool:
    if provider() != "anthropic":
        _load_env()
        return bool(os.environ.get(_compat(provider())[1]))
    return bool(os.environ.get("ANTHROPIC_API_KEY")) or _client is not None


def warm_up() -> None:
    """Import the SDK and build the client in the background at startup (the first import in a
    fresh environment can take longer than the reply limit)."""
    if provider() != "anthropic":
        return                                               # plain HTTPS: nothing to warm
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


def _openai_content(content):
    """Claude-style content blocks -> OpenAI chat content parts."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content:
        if b.get("type") == "image":
            src = b["source"]
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:{src['media_type']};base64,{src['data']}"}})
        else:
            parts.append({"type": "text", "text": b.get("text", "")})
    return parts


# OpenAI-compatible providers: name -> (base url, key variable, model)
def _compat(name):
    if name == "groq":
        return ("https://api.groq.com/openai/v1", "GROQ_API_KEY",
                os.environ.get("WALL_GROQ_MODEL", getattr(config, "AI_GROQ_MODEL", "openai/gpt-oss-120b")))
    return ("https://api.openai.com/v1", "OPENAI_API_KEY", config.AI_OPENAI_MODEL)


def _has_image(content) -> bool:
    return not isinstance(content, str) and any(b.get("type") == "image" for b in content)


def _ask_openai(system, content, max_tokens, schema, timeout, effort="low", images="route", prov=None, art=False):
    import requests
    _load_env()
    prov = prov or provider()
    if prov == "groq" and _has_image(content):       # Groq's models cannot see pictures
        if images == "drop":
            content = [b for b in content if b.get("type") != "image"]
        else:
            prov = "openai"                          # a vision call goes to OpenAI instead
    base, keyvar, model = _compat(prov)
    if art and prov == "openai":
        model = model_name(art=True)
    key = os.environ.get(keyvar)
    if not key:
        raise RuntimeError(f"{keyvar} is not set")
    body = {"model": model,
            "max_completion_tokens": min(int(max_tokens), 32000),
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": _openai_content(content)}]}
    if prov == "openai" and model.startswith("gpt-5"):          # reasoning models think before the GLSL
        body["max_completion_tokens"] = min(int(max_tokens) + 8000, 32000)   # thinking counts against the cap
        body["reasoning_effort"] = {"low": "low", "medium": "medium"}.get(effort, "high")
    if prov == "groq":
        body["reasoning_effort"] = {"low": "low", "medium": "medium"}.get(effort, "high")   # gpt-oss thinks
    if schema is not None:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "reply", "schema": schema, "strict": False}}
    r = requests.post(base + "/chat/completions", json=body,
                      headers={"Authorization": f"Bearer {key}"},
                      timeout=timeout or config.AI_TIMEOUT_SEC + 5)
    if r.status_code != 200:
        raise RuntimeError(f"{prov} {r.status_code}: {r.text[:200]}")
    j = r.json()
    ch = j["choices"][0]
    if ch["message"].get("refusal"):
        raise RuntimeError("declined: " + str(ch["message"]["refusal"])[:80])
    text = (ch["message"].get("content") or "").strip()
    if not text:
        raise RuntimeError(f"{prov} sent an empty reply (finish_reason {ch.get('finish_reason')})")
    out = json.loads(text) if schema is not None else text
    u = j.get("usage", {})
    return out, int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0)


def ask(system: str, content, max_tokens: int = 2048, effort: str = "low", schema: dict = None,
        timeout: float = None, images: str = "route", art: bool = False):
    """One Claude call. `content` is a string or a list of content blocks. With `schema`, the reply
    is guaranteed to be JSON matching it (structured output) and is returned parsed.
    Returns (text_or_dict, input_tokens, output_tokens). Raises on refusal or API errors."""
    if provider() != "anthropic":
        return _ask_openai(system, content, max_tokens, schema, timeout, effort, images, art=art)
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


_recent_lines = []                     # what the mirror said lately (kept in memory): so it does not repeat itself


def _moment() -> str:
    """When it is, for the mirror: 'It is Saturday late evening.'"""
    now = datetime.datetime.now()
    part = ("late at night" if now.hour < 5 else "early morning" if now.hour < 9 else "morning" if now.hour < 12 else
            "lunchtime" if now.hour < 14 else "afternoon" if now.hour < 18 else "evening" if now.hour < 22 else "late evening")
    return f"It is {now.strftime('%A')}, {part}, {now.strftime('%B')}."


def _call_api(frame: np.ndarray, hint: str = "") -> tuple[str, int, int]:
    avoid = ("Lines you said recently (do not repeat their jokes or openings): "
             + " | ".join(_recent_lines[-8:]) + ".") if _recent_lines else ""
    text, tin, tout = ask(_persona(),
                          [{"type": "text", "text": " ".join(x for x in (
                              "Look at this person and speak.", hint, _moment(), avoid) if x).strip()},
                           _image_block(frame)],
                          max_tokens=1024, effort="low", timeout=config.AI_TIMEOUT_SEC)
    text = text.strip().strip('"\'')
    if text:
        _recent_lines.append(text)
        del _recent_lines[:-12]
    return text, tin, tout


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

_recent_booth = []


def _call_booth_prompts(n: int) -> list[str]:
    schema = {"type": "object", "properties": {"prompts": {"type": "array", "items": {"type": "string"}}},
              "required": ["prompts"], "additionalProperties": False}
    import random
    j, _, _ = ask(config.BOOTH_AI_PROMPT_SYSTEM.format(n=n),
                  f"Give me {n} pose directions for this session. Tonight's flavour: {random.choice(config.BOOTH_FLAVOURS)}. "
                  f"{_moment()} Avoid these (said recently): {'; '.join(_recent_booth[-8:]) or 'nothing yet'}.",
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
    _recent_booth.extend(cleaned)
    del _recent_booth[:-12]
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
