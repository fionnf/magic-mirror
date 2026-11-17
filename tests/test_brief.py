"""The Fortuna Brief: the pieces other code depends on must exist and behave (a refactor once dropped due() and the 07:30 print
silently stopped working).

    python3 -m pytest tests/test_brief.py      (or run the file directly)
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from display import brief  # noqa: E402


def test_api_surface_used_by_the_wall():
    for name in ("due", "DEFAULT_PRINT_AT", "data", "plan", "show_seconds", "slip_image", "print_slip", "print_once", "frame", "frame_en",
                 "thumb", "thumb_en", "render_scene", "weekend_dates", "mountain_text", "enrich", "set_lang"):
        assert hasattr(brief, name), f"display.brief.{name} is missing"


def test_daily_print_schedule():
    tz = brief._tz()
    at = lambda h, m: datetime.datetime(2026, 11, 5, h, m, tzinfo=tz)
    assert not brief.due({}, at(7, 0))
    assert brief.due({}, at(7, 30)) and brief.due({}, at(11, 29))
    assert not brief.due({}, at(11, 31)) and not brief.due({}, at(22, 0))
    assert not brief.due({"brief_printed": "2026-11-05"}, at(8, 0))
    assert not brief.due({"brief_print": False}, at(8, 0))
    assert brief.due({"brief_print_at": "06:00"}, at(6, 5))


def test_every_scene_draws():
    dat = brief._sample()
    dat["mountains"] = None
    dat["science"] = [{"topic": "Physics", "line": "One sentence."}]
    for lang in ("en",):
        dat["lang"] = lang
        brief.set_lang(lang)
        for name in ("clock", "weather", "hours", "outlook", "science", "news"):
            brief.render_scene(name, dat, t=3.0, k=0)
        assert brief.slip_image(dat, ai=False).width == 384


def test_the_slip_is_short():
    dat = brief._sample()
    dat["lang"] = "en"
    assert brief.slip_image(dat, ai=False).height < 1100


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
