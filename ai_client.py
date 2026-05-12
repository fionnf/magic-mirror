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


def _call_api(frame: np.ndarray) -> tuple[str, int, int]:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    b64 = _frame_to_b64_jpeg(frame)
    resp = client.chat.completions.create(
        model=config.AI_MODEL,
        max_tokens=config.AI_MAX_TOKENS,
        messages=[
            {"role": "system", "content": config.MIRROR_PERSONA},
            {"role": "user", "content": [
                {"type": "text", "text": "Look at this person and speak."},
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


def get_mirror_message(frame: np.ndarray) -> str:
    """Blocking call with timeout and fallback."""
    start = time.monotonic()
    future = _executor.submit(_call_api, frame)
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
