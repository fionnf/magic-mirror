"""Claude API vision call with timeout, fallback, and usage logging."""
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


def _frame_to_b64_jpeg(frame: np.ndarray) -> str:
    if frame.ndim == 3 and frame.shape[2] == 3:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    else:
        rgb = frame
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _log_usage(tokens_in: int, tokens_out: int) -> None:
    try:
        with open(config.USAGE_LOG, "a") as f:
            f.write(f"{datetime.datetime.now().isoformat()}\t{tokens_in}\t{tokens_out}\n")
    except Exception as e:
        print(f"[AI] usage log write failed: {e}")


def _call_api(frame: np.ndarray) -> tuple[str, int, int]:
    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    b64 = _frame_to_b64_jpeg(frame)
    resp = client.messages.create(
        model=config.AI_MODEL,
        max_tokens=config.AI_MAX_TOKENS,
        system=config.MIRROR_PERSONA,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": "Look at this person and speak."},
            ],
        }],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    text = text.strip('"\'')
    return text, resp.usage.input_tokens, resp.usage.output_tokens


def get_mirror_message(frame: np.ndarray) -> str:
    """Blocking call with timeout and fallback. Returns plain string."""
    start = time.monotonic()
    future = _executor.submit(_call_api, frame)
    try:
        text, tin, tout = future.result(timeout=config.AI_TIMEOUT_SEC)
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
    """Non-blocking variant returning a Future of the string."""
    return _executor.submit(get_mirror_message, frame)
