"""The Fortuna Brief: a short show of the day (a minute and a half to two minutes: every scene gets the time its content needs) - date, time, the weather at the house, the top news.

    brief.frame(t)        -> PIL image for the wall (the "brief" mode; loops every LOOP_SEC, fresh data each loop)
    brief.slip_image()    -> the same summary as a paper slip for the receipt printer
    brief.thumb()         -> a still for the app (no network)

Data (no accounts, no keys): Open-Meteo for the weather at the house, RSS for the news (The Local for
Switzerland, the BBC for the world). Everything is cached for a few minutes; with no internet the show still
runs (clock, date) and says what is missing. Set the place with WALL_BRIEF_LAT / WALL_BRIEF_LON / WALL_BRIEF_PLACE.
"""
import datetime
import json
import os
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import config

PACE = float(os.environ.get("WALL_BRIEF_PACE", "1.0"))                  # 1.0 = quick; 1.5 = slower (more time to read), 0.7 = faster
LOOP_SEC = 100.0                                                        # about how long the show is (it depends on what there is to read)
PLACE = os.environ.get("WALL_BRIEF_PLACE", "Fortunagasse 24, Zürich")
LAT = float(os.environ.get("WALL_BRIEF_LAT", "47.3715"))
LON = float(os.environ.get("WALL_BRIEF_LON", "8.5390"))
TZNAME = os.environ.get("WALL_BRIEF_TZ", "Europe/Zurich")
DEFAULT_LANG = os.environ.get("WALL_BRIEF_LANG", "en")
FEEDS = {
    "en": [("CH", ["https://feeds.thelocal.com/rss/ch", "https://www.srf.ch/news/bnf/rss/1890"]),   # English first, SRF (German) as a fallback
           ("WORLD", ["https://feeds.bbci.co.uk/news/world/rss.xml"])],
    "de": [("CH", ["https://www.nzz.ch/recent.rss", "https://www.srf.ch/news/bnf/rss/1890"]),       # NZZ, then SRF
           ("WORLD", ["https://www.zdf.de/rss/zdf/nachrichten", "https://www.tagesschau.de/ausland/index~rss2.xml"])],   # ZDF heute, then Tagesschau
}
MAX_STORIES = 6
CACHE_SEC = 600.0
FADE = 0.9                                   # seconds of dissolve between scenes

WMO_EN = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
       51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
       61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
       71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
       82: "Violent showers", 85: "Snow showers", 86: "Snow showers", 95: "Thunderstorm", 96: "Thunder, hail",
       99: "Thunder, hail"}


WMO_DE = {0: "Klar", 1: "Überwiegend klar", 2: "Teils bewölkt", 3: "Bedeckt", 45: "Nebel", 48: "Reifnebel",
          51: "Leichter Nieselregen", 53: "Nieselregen", 55: "Starker Nieselregen", 56: "Gefrierender Niesel", 57: "Gefrierender Niesel",
          61: "Leichter Regen", 63: "Regen", 65: "Starker Regen", 66: "Gefrierender Regen", 67: "Gefrierender Regen",
          71: "Leichter Schneefall", 73: "Schneefall", 75: "Starker Schneefall", 77: "Schneegriesel", 80: "Regenschauer", 81: "Regenschauer",
          82: "Heftige Schauer", 85: "Schneeschauer", 86: "Schneeschauer", 95: "Gewitter", 96: "Gewitter, Hagel", 99: "Gewitter, Hagel"}

_tl = threading.local()                                            # the language of whatever this thread is drawing or writing


def set_lang(lang):
    _tl.lang = lang if lang in ("en", "de") else "en"


def _lang():
    return getattr(_tl, "lang", "en")


class _Wmo:
    """The weather words in the language being drawn (WMO.get(code, default) as before)."""

    def get(self, code, default=""):
        return (WMO_DE if _lang() == "de" else WMO_EN).get(code, default)


WMO = _Wmo()

DE = {   # the fixed wording of the screens and the slip, in German (anything not listed stays as written)
    "F O R T U N A   B R I E F": "F O R T U N A   B R I E F I N G", "FORTUNA BRIEF": "FORTUNA BRIEFING",
    "Good morning": "Guten Morgen", "Good day": "Guten Tag", "Good evening": "Guten Abend", "Good night": "Gute Nacht",
    "WEATHER NOW": "WETTER JETZT", "FEELS": "GEFÜHLT", "FEELS LIKE": "GEFÜHLT", "HUMID": "FEUCHTE", "HUMIDITY": "FEUCHTE",
    "THE NEXT 24 HOURS": "DIE NÄCHSTEN 24 STUNDEN", "NEXT 24 HOURS": "NÄCHSTE 24 STUNDEN", "No forecast": "Keine Vorhersage",
    "No rain expected": "Kein Regen erwartet", "RAIN CHANCE %": "REGENCHANCE %", "THE DAYS AHEAD": "DIE KOMMENDEN TAGE",
    "Today": "Heute", "Weather offline": "Wetter nicht verfügbar", "MOUNTAIN WEEKEND": "BERGWOCHENENDE",
    "No mountain forecast": "Keine Bergvorhersage", "THE SHORT VERSION": "DIE KURZFASSUNG", "hi": "max", "cloud": "Wolken",
    "here": "hier", "no cloud": "keine Wolken", "no new snow": "kein Neuschnee", "SWITZERLAND": "SCHWEIZ", "WORLD": "WELT",
    "TOP STORIES": "SCHLAGZEILEN", "RESEARCH HIGHLIGHTS": "FORSCHUNGS-HIGHLIGHTS", "RESEARCH": "FORSCHUNG", "now": "jetzt", "Weather unavailable (offline).": "Wetter nicht verfügbar (offline).",
    "News unavailable (offline).": "Nachrichten nicht verfügbar (offline).", "Have a lovely day.": "Einen schönen Tag!",
}
DAYS_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
DAYS_DE_S = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
MONTHS_DE_S = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."]


def _loc(s):
    return DE.get(s, s) if _lang() == "de" else s


def _x(en, de):
    """Pick the wording for the language being drawn."""
    return de if _lang() == "de" else en


def _wd(d, short=False):
    """Weekday name of a date or datetime."""
    if _lang() == "de":
        return (DAYS_DE_S if short else DAYS_DE)[d.weekday()]
    return d.strftime("%a" if short else "%A")


def _mon(d, short=False):
    if _lang() == "de":
        return (MONTHS_DE_S if short else MONTHS_DE)[d.month - 1]
    return d.strftime("%b" if short else "%B")


def _long_date(n):
    """'Wednesday 04 November 2026' / 'Mittwoch, 4. November 2026'."""
    return f"{_wd(n)}, {n.day}. {_mon(n)} {n.year}" if _lang() == "de" else n.strftime("%A %d %B %Y")


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZNAME)
    except Exception:
        return None


def now():
    return datetime.datetime.now(_tz())


# ------------------------------------------------------------------ data ---

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cache_file(lang):
    return os.path.join(ROOT, "panel_setup", f"brief_cache_{lang}.json")


def _disk_load(max_age, lang):
    try:
        path = _cache_file(lang)
        if time.time() - os.path.getmtime(path) > max_age:
            return None
        with open(path) as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) and (d.get("weather") or d.get("news") or d.get("mountains")) else None
    except Exception:
        return None


def _disk_save(d, lang):
    try:
        path = _cache_file(lang)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({k: v for k, v in d.items() if not k.startswith("_")}, fh)
        os.replace(tmp, path)
    except Exception:
        pass


_cache = {}                                                        # language -> {"t": when, "data": the brief}
_lock = threading.Lock()
_busy = {}


def _get(url, timeout=7):
    import requests
    return requests.get(url, timeout=timeout, headers={"User-Agent": "fortuna-wall-brief/1.0"})


def fetch_weather():
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=%s&forecast_days=4"
           "&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,"
           "wind_speed_10m,is_day"
           "&hourly=temperature_2m,precipitation_probability,weather_code"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max,"
           "uv_index_max" % (LAT, LON, TZNAME.replace("/", "%2F")))
    j = _get(url).json()
    c, h, d = j["current"], j["hourly"], j["daily"]
    cur = {"temp": c["temperature_2m"], "feels": c["apparent_temperature"], "humidity": c["relative_humidity_2m"],
           "rain": c["precipitation"], "code": int(c["weather_code"]), "wind": c["wind_speed_10m"],
           "day": bool(c["is_day"]), "time": c["time"]}
    start = max(0, next((i for i, t in enumerate(h["time"]) if t >= c["time"][:13]), 0))
    hours = [{"time": h["time"][i][11:16], "temp": h["temperature_2m"][i], "pop": h["precipitation_probability"][i] or 0,
              "code": int(h["weather_code"][i])} for i in range(start, min(start + 24, len(h["time"])))]
    days = [{"date": d["time"][i], "code": int(d["weather_code"][i]), "max": d["temperature_2m_max"][i],
             "min": d["temperature_2m_min"][i], "pop": d["precipitation_probability_max"][i] or 0,
             "sunrise": d["sunrise"][i][11:16], "sunset": d["sunset"][i][11:16], "uv": d["uv_index_max"][i]}
            for i in range(len(d["time"]))]
    return {"now": cur, "hours": hours, "days": days}


REGIONS = [   # name, place, elevation in m (the forecast is for this height, not the valley)
    ("Valais", "Zermatt", 46.02, 7.75, 2500),
    ("Graubünden", "Davos", 46.80, 9.84, 2500),
    ("Central CH", "Engelberg", 46.77, 8.42, 2200),
    ("Bernese Alps", "Jungfrau", 46.55, 7.98, 2400),
    ("Eastern CH", "Säntis", 47.25, 9.34, 2200),
]


SLF = "https://measurement-api.slf.ch/public/api/imis"
LEVELS = [950, 925, 900, 850, 800, 750, 700, 650, 600, 500, 400]       # pressure levels for the cloud layers


def fetch_snow():
    """Measured snow depth (cm) at the SLF snow station nearest each region (and nearest its height): {region: {...}}."""
    import math
    stations = [x for x in _get(SLF + "/stations", 15).json() if "SNOW" in x.get("type", "") and x.get("country_code") == "CH"]
    out = {}
    for name, place, la, lo, elev in REGIONS:
        best = min(stations, key=lambda x: math.hypot((la - x["lat"]) * 111, (lo - x["lon"]) * 76) + abs(x["elevation"] - elev) / 100.0)
        try:
            m = [r for r in _get(f"{SLF}/station/{best['code']}/measurements", 15).json() if r.get("HS") is not None]
            now_cm = float(m[-1]["HS"])
            day_ago = float(m[max(0, len(m) - 49)]["HS"])
            out[name] = {"station": best["label"], "elev": int(best["elevation"]), "cm": round(now_cm, 1), "d24": round(now_cm - day_ago, 1)}
        except Exception:
            pass
    return out


def _cloud_layers(j, iso, base, elev):
    """The estimated cloud top at midday: the top of the cloudy pressure levels above the cloud base."""
    h = j["hourly"]
    try:
        k = h["time"].index(iso + "T12:00")
        lv = [(h[f"geopotential_height_{p}hPa"][k], h[f"cloud_cover_{p}hPa"][k] or 0) for p in LEVELS]
    except (ValueError, IndexError, KeyError):
        return None
    lv.sort()
    floor = (base - 500) if base else elev - 300
    top = None
    for z, cc in lv:
        if z >= floor and cc >= 40:
            top = z + 200 if top is None or z - top < 900 else top
    return int(round(top / 100.0) * 100) if top else None


def fetch_mountains():
    """The week in the Swiss mountains at height: weather, new snow, the freezing level and a cloud base estimate."""
    url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&elevation=%s&timezone=Europe%%2FZurich&forecast_days=9"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min,snowfall_sum,precipitation_sum,wind_gusts_10m_max,sunshine_duration"
           "&hourly=temperature_2m,dew_point_2m,cloud_cover,freezing_level_height"
           % (",".join(str(r[2]) for r in REGIONS), ",".join(str(r[3]) for r in REGIONS), ",".join(str(r[4]) for r in REGIONS)))
    lv_url = ("https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s&timezone=Europe%%2FZurich&forecast_days=9&hourly=%s"
              % (",".join(str(r[2]) for r in REGIONS), ",".join(str(r[3]) for r in REGIONS),
                 ",".join(f"cloud_cover_{p}hPa,geopotential_height_{p}hPa" for p in LEVELS)))
    try:
        layers = _get(lv_url, 15).json()
    except Exception:
        layers = [None] * len(REGIONS)
    try:
        snow = fetch_snow()
    except Exception as e:
        print(f"[brief] snow stations unavailable: {e}", flush=True)
        snow = {}
    out = []
    for (name, place, _la, _lo, elev), j, lj in zip(REGIONS, _get(url, 15).json(), layers):
        dly, hr = j["daily"], j["hourly"]
        days = {}
        cum = 0.0
        sn = snow.get(name)
        for i, iso in enumerate(dly["time"]):
            try:
                k = hr["time"].index(iso + "T12:00")                    # midday: the hours people are on the mountain
                t, td, cc, frz = hr["temperature_2m"][k], hr["dew_point_2m"][k], hr["cloud_cover"][k], hr["freezing_level_height"][k]
            except (ValueError, IndexError):
                t = td = cc = frz = None
            base = None
            if t is not None and td is not None and cc is not None and cc >= 25:
                base = int(round((elev + 125.0 * max(0.0, t - td)) / 100.0) * 100)   # the lifting condensation level, from the spread
            cum += dly["snowfall_sum"][i] or 0.0                               # new snow from today through this day
            top = _cloud_layers(lj, iso, base, elev) if (lj and base) else None
            if top is not None and base is not None and top < base + 100:
                top = base + 200
            days[iso] = {"top": top, "depth": round(sn["cm"] + cum, 1) if sn else None,
                         "code": int(dly["weather_code"][i]), "max": dly["temperature_2m_max"][i], "min": dly["temperature_2m_min"][i],
                         "snow": dly["snowfall_sum"][i] or 0.0, "precip": dly["precipitation_sum"][i] or 0.0,
                         "gust": dly["wind_gusts_10m_max"][i] or 0.0, "sun": (dly["sunshine_duration"][i] or 0.0) / 3600.0,
                         "cloud": cc, "base": base, "frz": int(round(frz / 100.0) * 100) if frz is not None else None}
        out.append({"name": name, "place": place, "elev": elev, "days": days, "snow": sn})
    return out


def weekend_dates(n=None):
    """The weekend to show: Saturday and Sunday of this week (on a Sunday: today, and next Saturday)."""
    n = n or now()
    d = n.date()
    wd = d.weekday()                                               # Mon 0 .. Sun 6
    if wd == 6:
        sat, sun = d + datetime.timedelta(days=6), d
        return [sun.isoformat(), sat.isoformat()]
    sat = d + datetime.timedelta(days=5 - wd)
    return [sat.isoformat(), (sat + datetime.timedelta(days=1)).isoformat()]


def mountain_text(elev, d):
    """(snow or weather condition, cloud line) for one region and day."""
    snow, hi, lo, code = d["snow"], d["max"], d["min"], d["code"]
    if snow >= 10:
        cond = f"Powder, {snow:.0f} cm new"
    elif snow >= 3:
        cond = f"Fresh snow, {snow:.0f} cm"
    elif snow >= 0.5:
        cond = f"Light snow, {snow:.1f} cm"
    elif code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82) and hi > 1:
        cond = "Rain, wet snow"
    elif hi <= 1:
        cond = "Cold, firm snow" if lo < -6 else "Cold, settled snow"
    elif hi > 3:
        cond = "Soft snow, thawing"
    else:
        cond = WMO.get(code, "")
    top = d.get("top")
    if d["base"] is None:
        cloud = "no cloud" if (d["cloud"] is not None and d["cloud"] < 25) else ""
    elif d["base"] < elev:
        cloud = f"in cloud up to {top} m" if top else f"in cloud, base {d['base']} m"
    else:
        cloud = f"cloud {d['base']}-{top} m" if top else f"cloud base {d['base']} m"
    return cond, cloud


MSUM_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["summary"], "properties": {"summary": {"type": "string"}}}


def mountain_summary(mt, lang=None):
    """Two or three short sentences on the mountain weekend, written by the AI from the forecast numbers only. -> str ('' if
    the AI is unavailable: the show then simply has no summary screen)."""
    lang = lang or DEFAULT_LANG
    set_lang(lang)
    try:
        import ai_client
        facts = {}
        for iso in weekend_dates():
            lines = []
            for r in mt:
                if iso in r["days"]:
                    dd = r["days"][iso]
                    cond, cloud = mountain_text(r["elev"], dd)
                    snow = f"snow depth about {round(dd['depth'])} cm" if dd.get("depth") is not None else "snow depth unknown"
                    lines.append(f"{REGION_DE.get(r['name'], r['name']) if lang == 'de' else r['name']} at {r['elev']} m: {cond}; {round(dd['min'])} to {round(dd['max'])} C; {cloud or WMO.get(dd['code'], '')}; "
                                 f"{snow}; freezing level {dd.get('frz')} m; sunshine {dd.get('sun', 0):.0f} h")
            facts[datetime.date.fromisoformat(iso).strftime("%A")] = lines
        system = ("You write the mountain weekend for a wall display in a Zurich flat. Give a SHORT summary of the Swiss Alps this "
                  "weekend: two short sentences, at most 150 characters in all: which day looks better and where it is clear, then "
                  "where snow falls or lies or where cloud sits low. Plain words, no emojis, no hype, British spelling. Use ONLY "
                  "the facts given; never add numbers, places or conditions that are not there."
                  + (" Write in German (Swiss spelling: ss, never the letter ß)." if lang == "de" else ""))
        j, _i, _o = ai_client.ask(system, json.dumps(facts, ensure_ascii=False), max_tokens=300, effort="low", schema=MSUM_SCHEMA, timeout=25)
        return str(j.get("summary", "")).strip()[:170]
    except Exception as e:
        print(f"[brief] no AI summary of the mountains: {e}", flush=True)
        return ""


def _clean(s):
    import html
    import re
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


IMG_DIR = os.path.join(ROOT, "panel_setup", "brief_images")
_MRSS = "{http://search.yahoo.com/mrss/}"


def _item_image(it):
    for tag in (_MRSS + "thumbnail", _MRSS + "content"):
        for e in it.iter(tag):
            if e.get("url"):
                return e.get("url")
    for e in it.iter("enclosure"):
        if "image" in (e.get("type") or "") and e.get("url"):
            return e.get("url")
    return None


def fetch_image(url):
    """Download a story picture once (kept small, on disk); -> its path, or None."""
    import hashlib
    import io
    try:
        os.makedirs(IMG_DIR, exist_ok=True)
        path = os.path.join(IMG_DIR, hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")
        if os.path.exists(path):
            return path
        r = _get(url, 9)
        if r.status_code != 200 or len(r.content) > 3_000_000:
            return None
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        if im.width > 520:
            im = im.resize((520, round(im.height * 520 / im.width)), Image.LANCZOS)
        if im.width < 90:
            return None
        im.save(path, "JPEG", quality=84)
        return path
    except Exception:
        return None


def _clean_images(days=3):
    try:
        for fn in os.listdir(IMG_DIR):
            p = os.path.join(IMG_DIR, fn)
            if time.time() - os.path.getmtime(p) > days * 86400:
                os.remove(p)
    except OSError:
        pass


SCIENCE_FEEDS = ["https://www.sciencedaily.com/rss/top/science.xml", "https://phys.org/rss-feed/", "https://www.nature.com/nature.rss",
                 "https://api.quantamagazine.org/feed/", "https://ethz.ch/en/news-and-events/eth-news/news.rss"]
SCI_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["picks"],
              "properties": {"picks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                  "required": ["id", "topic", "line"],
                                                                  "properties": {"id": {"type": "integer"}, "topic": {"type": "string"},
                                                                                 "line": {"type": "string"}}}}}}


def _parse_xml(content):
    """Parse a feed that may carry HTML entities or bare ampersands (some do), without giving up on it."""
    import re
    return ET.fromstring(re.sub(rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", b"&amp;", content))


def _local(e, name):
    for ch in e:
        if ch.tag.split("}")[-1] == name:
            return ch.text or ""
    return ""


def fetch_science(lang=None):
    """Three research highlights the AI picked from the day's science feeds: [{"topic", "line"}]. [] when unavailable."""
    lang = lang or DEFAULT_LANG
    cands = []

    def one(url):
        try:
            root = _parse_xml(_get(url, 9).content)
            out = []
            for it in root.iter():
                if it.tag.split("}")[-1] != "item":
                    continue
                title = _clean(_local(it, "title"))
                if title:
                    out.append({"title": title, "text": _clean(_local(it, "description"))[:260]})
                if len(out) >= 8:
                    break
            return out
        except Exception:
            return []
    with ThreadPoolExecutor(len(SCIENCE_FEEDS)) as ex:
        lists = list(ex.map(one, SCIENCE_FEEDS))
    for k in range(8):                                             # interleave the sources
        for lst in lists:
            if k < len(lst):
                cands.append(lst[k])
    if len(cands) < 6:
        return []
    try:
        import ai_client
        listing = "\n".join(f"{i}. {c['title']}" + (f" - {c['text']}" if c["text"] else "") for i, c in enumerate(cands))
        system = ("You pick research highlights in science for the wall of a Zurich flatshare. From the numbered candidates choose the THREE most "
                  "interesting and significant research results: real findings (not product news, opinion or hype), in different fields, "
                  "understandable to an educated reader. Give each a 'topic' (one or two words naming the field) and a 'line': one plain "
                  "sentence of at most 95 characters saying what was found, using ONLY what the headline and text say; never add facts."
                  + (" Write the topic and the line in German (Swiss spelling: ss, never the letter ß)." if lang == "de" else ""))
        j, _i, _o = ai_client.ask(system, listing, max_tokens=500, effort="low", schema=SCI_SCHEMA, timeout=30)
        out, seen = [], set()
        for pk in j.get("picks", []):
            i = pk.get("id")
            if isinstance(i, int) and 0 <= i < len(cands) and i not in seen and str(pk.get("line", "")).strip():
                seen.add(i)
                out.append({"topic": str(pk.get("topic", "")).strip()[:22], "line": str(pk["line"]).strip()[:120]})
        return out[:3]
    except Exception as e:
        print(f"[brief] no research highlights: {e}", flush=True)
        return []


CANDIDATES = 9                                                      # headlines taken from each feed, for the AI to choose from
PICKS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["picks"],
                "properties": {"picks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                                    "required": ["id", "why"],
                                                                    "properties": {"id": {"type": "integer"}, "why": {"type": "string"}}}}}}


def curate_news(cands, lang):
    """Ask the AI which stories are actually useful to know (not just the first headlines of each feed). -> [(index, why)] in the
    order to show them, at most MAX_STORIES; None when the AI is unavailable (the caller then takes the first ones)."""
    try:
        import ai_client
        listing = "\n".join(f"{i}. [{c['tag']}] {c['title']}" + (f" - {c['text'][:140]}" if c["text"] else "") for i, c in enumerate(cands))
        system = ("You choose the news for the wall of a flatshare in Zurich. From the numbered candidates pick the " + str(MAX_STORIES) +
                  " that are most USEFUL TO KNOW today: what affects daily life, safety, health, money, travel and the weather; Swiss politics "
                  "and economy; and the biggest world events. Skip sports results, celebrities, lifestyle and entertainment, clickbait, "
                  "opinion pieces, trivial local incidents, and repeats of one event (take the best one). Keep a mix: at least two Swiss "
                  "stories if there are good ones. Return the picks most important first, each with the candidate number and a reason of "
                  "at most six words" + (" (in German)" if lang == "de" else "") + ".")
        j, _i, _o = ai_client.ask(system, listing, max_tokens=500, effort="low", schema=PICKS_SCHEMA, timeout=30)
        out, seen = [], set()
        for pk in j.get("picks", []):
            i = pk.get("id")
            if isinstance(i, int) and 0 <= i < len(cands) and i not in seen:
                seen.add(i)
                out.append((i, str(pk.get("why", "")).strip()))
        return out[:MAX_STORIES] if len(out) >= 3 else None
    except Exception as e:
        print(f"[brief] the AI could not choose the news: {e}", flush=True)
        return None


def fetch_news(lang=None):
    """-> [{"tag", "title", "text", "img", "why"}]: the stories the AI judged most useful to know (Switzerland and the world)."""
    def one(feed):
        tag, urls = feed
        for url in urls:                                           # the first feed that answers with stories
            try:
                root = ET.fromstring(_get(url).content)
                out = []
                for it in root.iter("item"):
                    title = _clean(it.findtext("title"))
                    if title:
                        out.append({"tag": tag, "title": title, "text": _clean(it.findtext("description")), "url": _item_image(it)})
                    if len(out) >= CANDIDATES:
                        break
                if out:
                    return out
            except Exception:
                pass
        return []
    with ThreadPoolExecutor(2) as ex:
        lists = list(ex.map(one, FEEDS[lang or DEFAULT_LANG]))
    cands, seen = [], set()
    for k in range(CANDIDATES):
        for lst in lists:
            if k < len(lst) and lst[k]["title"] not in seen:
                seen.add(lst[k]["title"])
                cands.append(lst[k])
    picks = curate_news(cands, lang or DEFAULT_LANG) if len(cands) > MAX_STORIES else None
    if picks:
        mixed = [dict(cands[i], why=why) for i, why in picks]
        print("[brief] news chosen by the AI: " + " | ".join(f"{m['title'][:38]} ({m['why']})" for m in mixed), flush=True)
    else:
        mixed = cands[:MAX_STORIES]
    with ThreadPoolExecutor(6) as ex:                              # a picture for every story (when its feed has one)
        for st, path in zip(mixed, ex.map(lambda x: fetch_image(x["url"]) if x.get("url") else None, mixed)):
            st["img"] = path
    _clean_images()
    return mixed


def gather(lang=None):
    """Fetch everything now (weather, news and mountains in parallel); a failed part is None / empty."""
    lang = lang or DEFAULT_LANG
    out = {"weather": None, "news": [], "mountains": None, "mountain_ai": "", "science": [], "lang": lang, "when": time.time()}

    def w():
        try:
            out["weather"] = fetch_weather()
        except Exception as e:
            print(f"[brief] weather unavailable: {e}", flush=True)

    def n():
        out["news"] = fetch_news(lang)

    def m():
        try:
            out["mountains"] = fetch_mountains()
        except Exception as e:
            print(f"[brief] mountains unavailable: {e}", flush=True)
    def sc():
        out["science"] = fetch_science(lang)
    ts = [threading.Thread(target=f, daemon=True) for f in (w, n, m, sc)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(15)
    if out["mountains"]:                                           # the short summary the mountain screen opens with
        out["mountain_ai"] = mountain_summary(out["mountains"], lang)
    return out


def data(max_age=CACHE_SEC, wait=True, lang=None):
    """The cached brief data for a language. Refreshes when older than max_age: now (wait) or in the background. The cache is
    also kept on disk, so the show (its own process) and the controller (which prints) share one fetch and one story."""
    lang = lang or DEFAULT_LANG
    with _lock:
        ent = _cache.get(lang) or {"t": 0.0, "data": None}
        d, age = ent["data"], time.time() - ent["t"]
    if d is None:
        disk = _disk_load(max_age, lang)
        if disk is not None:
            with _lock:
                _cache[lang] = {"data": disk, "t": os.path.getmtime(_cache_file(lang))}
            return disk
    if d is not None and age < max_age:
        return d
    if d is not None and not wait:
        refresh_async(lang)
        return d
    fresh = gather(lang)
    if fresh["weather"] is None and not fresh["news"] and not fresh["mountains"] and d is not None:
        return d                                                   # offline: keep the old one
    with _lock:
        _cache[lang] = {"data": fresh, "t": time.time()}
    _disk_save(fresh, lang)
    return fresh


def refresh_async(lang=None):
    lang = lang or DEFAULT_LANG
    if _busy.get(lang):
        return
    _busy[lang] = True

    def run():
        try:
            fresh = gather(lang)
            if fresh["weather"] is not None or fresh["news"] or fresh["mountains"]:
                with _lock:
                    _cache[lang] = {"data": fresh, "t": time.time()}
                _disk_save(fresh, lang)
        finally:
            _busy[lang] = False
    threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------- fonts ---

_fonts = {}
_FILES = {"bold": ["DejaVuSans-Bold.ttf", "Arial Bold.ttf"], "regular": ["DejaVuSans.ttf", "Arial.ttf"],
          "light": ["DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf", "Arial.ttf"]}


def font(size, style="bold"):
    if style is True:
        style = "bold"
    elif style is False:
        style = "regular"
    key = (size, style)
    if key not in _fonts:
        dirs = ["/usr/share/fonts/truetype/dejavu", "/Library/Fonts", "/System/Library/Fonts/Supplemental"]
        f = None
        paths = [os.path.join(d, n) for n in _FILES[style] for d in dirs]
        if style == "bold":
            paths = list(config.TEXT_FONT_PATHS) + paths
        for p in paths:
            if os.path.exists(p):
                try:
                    f = ImageFont.truetype(p, size)
                    break
                except Exception:
                    pass
        if f is None:
            try:
                f = ImageFont.load_default(size=size)
            except TypeError:
                f = ImageFont.load_default()
        _fonts[key] = f
    return _fonts[key]


def wrap(draw, text, fnt, max_w, max_lines=None):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=fnt) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,.;:") + "…"
    return lines


def _weight(style, size):
    """Thin weights break up on an LED grid: small text is always bold."""
    return "bold" if style in ("regular", "light") and size < THIN else style


def sfont(size, style="bold"):
    """A font for the wall (never below 12 px once shrunk, and bold when small)."""
    size = max(int(size), MINPX)
    return font(size, _weight(style, size))


def fit(style, size, text, max_w, floor=None):
    """The largest font (down from `size`) whose `text` is at most max_w wide: nothing may run off the wall.
    On the wall it never goes below 11 px (22 at 2x); the paper slip passes its own floor."""
    text = _loc(text)
    wall = floor is None
    floor = MINPX if wall else floor
    while size > floor:
        f = font(int(size), _weight(style, size) if wall else style)
        if f.getlength(text) <= max_w:
            return f
        size -= max(1, size * 0.04)
    return font(int(floor), _weight(style, floor) if wall else style)


# ------------------------------------------------------------ the look ---
# Every scene is: a slowly moving field of colour behind (cheap, redone every frame), a crisp layer of glowing
# type and glass cards on top (drawn at 2x and shrunk, so edges are smooth; redrawn only when something changes),
# and a few drifting lights (rain, snow, stars, bokeh).

SS = 2                                                             # supersampling of the type layer
MINPX = 12 * SS                                                    # nothing smaller than 12 px on the wall: LEDs cannot draw it
THIN = 17 * SS                                                     # below this size only bold weights hold together on a coarse grid
WHITE = (255, 255, 255)


def _ramp(cols, f):
    f = np.clip(f, 0.0, 1.0) * (len(cols) - 1)
    i = np.minimum(f.astype(int), len(cols) - 2)
    k = (f - i)[..., None]
    c = np.asarray(cols, np.float32)
    return c[i] * (1 - k) + c[i + 1] * k


class Field:
    """A slowly breathing field of colour (a few drifting waves through a three-colour ramp), darker at the edges."""

    def __init__(self, W, H, seed=0.0):
        self.W, self.H, self.seed = W, H, seed
        w, h = max(8, W // 4), max(8, H // 4)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self.x, self.y = xx / w * 2.4, yy / h * 3.2
        self.vig = (1.0 - 0.42 * (((xx / w - 0.5) * 1.5) ** 2 + ((yy / h - 0.5) * 1.1) ** 2))[..., None]
        self.ygrad = (yy / h)

    def render(self, t, cols, drift=1.0):
        t = t * drift + self.seed
        x, y = self.x, self.y
        f = (0.5 + 0.22 * np.sin(x * 1.9 + t * 0.09) + 0.2 * np.sin(y * 1.4 - t * 0.07 + x * 1.1)
             + 0.12 * np.sin((x - y) * 2.6 + t * 0.05))
        f = 0.62 * f + 0.38 * (1.0 - self.ygrad)                   # lighter near the top, deeper below
        img = _ramp(cols, f) * self.vig
        x = np.clip((img / 255.0 - 0.05) / 0.95, 0.0, 1.0) ** 1.25      # contrast curve: deepen the darks, keep the colour
        img = x * 255.0
        return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((self.W, self.H), Image.BICUBIC)


def _layer(W, H):
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def glow_text(layer, xy, s, fnt, fill=WHITE, anchor="la", glow=None, radius=None, strength=0.6, shadow=True):
    """Crisp text with a soft coloured halo and a faint shadow so it reads on any colour."""
    s = _loc(s)
    d = ImageDraw.Draw(layer)
    l, t, r, b = d.textbbox(xy, s, font=fnt, anchor=anchor)
    rad = radius or max(3, int(fnt.size * 0.18))
    pad = rad * 3
    box = (max(0, int(l - pad)), max(0, int(t - pad)), min(layer.width, int(r + pad)), min(layer.height, int(b + pad)))
    if box[2] <= box[0] or box[3] <= box[1]:
        return
    mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
    ImageDraw.Draw(mask).text((xy[0] - box[0], xy[1] - box[1]), s, font=fnt, fill=255, anchor=anchor)
    if shadow:
        sh = mask.filter(ImageFilter.GaussianBlur(max(2, rad * 0.5))).point(lambda v: min(255, int(v * 1.5)))
        layer.alpha_composite(Image.merge("RGBA", (Image.new("L", mask.size, 0),) * 3 + (sh,)), (box[0], box[1] + max(1, rad // 3)))
    if glow:
        gl = mask.filter(ImageFilter.GaussianBlur(rad)).point(lambda v: min(255, int(v * strength * 1.6)))
        gc = Image.new("RGBA", mask.size, tuple(glow) + (0,))
        gc.putalpha(gl)
        layer.alpha_composite(gc, (box[0], box[1]))
    if shadow:                                                     # a thin dark edge round the letters
        o = max(1, int(round(fnt.size * 0.06)))
        for dx, dy in ((-o, 0), (o, 0), (0, -o), (0, o), (-o, -o), (o, o), (-o, o), (o, -o)):
            d.text((xy[0] + dx, xy[1] + dy), s, font=fnt, fill=(0, 0, 0, 200), anchor=anchor)
    d.text(xy, s, font=fnt, fill=tuple(fill) + (255,), anchor=anchor)


def glass(layer, box, r=None, fill=(0, 0, 0, 110), line=(255, 255, 255, 170), width=2):
    """A card: a dark translucent fill and a clear light edge (faint fills vanish on the panel's few colour steps)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    r = r if r is not None else min(x1 - x0, y1 - y0) // 4
    ov = _layer(layer.width, layer.height)
    ImageDraw.Draw(ov).rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=line, width=width)
    layer.alpha_composite(ov)


def pill(layer, cx, cy, text, fnt, fill, ink=(20, 20, 30)):
    text = _loc(text)
    d = ImageDraw.Draw(layer)
    w = d.textlength(text, font=fnt) + fnt.size * 1.2
    h = fnt.size * 1.7
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=h / 2, fill=tuple(fill) + (255,))
    d.text((cx, cy), text, font=fnt, fill=tuple(ink) + (255,), anchor="mm")


def _radial(W, H, cx, cy, r, colour, strength=1.0):
    """A soft round light (RGBA) of radius r centred at cx, cy."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    a = np.clip(1.0 - np.hypot(xx - cx, yy - cy) / r, 0, 1) ** 2 * strength
    im = Image.new("RGBA", (W, H), tuple(colour) + (0,))
    im.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    return im


# ----------------------------------------------------------------- icons ---

def icon(layer, code, day, cx, cy, r, plain=False):
    """A weather picture, soft and luminous: sun with a halo, moon, layered clouds, rain, snow, fog, lightning."""
    sun, cloud, rain, snow = (255, 207, 90), (226, 234, 250), (125, 185, 255), (245, 248, 255)
    W, H = layer.size
    code = int(code)
    d = ImageDraw.Draw(layer)
    wk = max(2, int(r // 7))
    show_sun = code in (0, 1, 2)
    if show_sun:
        if day:
            if not plain:
                layer.alpha_composite(_radial(W, H, cx, cy, r * 2.0, (255, 190, 80), 0.75))
            for k in range(12):
                a = k * math.pi / 6
                d.line([cx + math.cos(a) * r * 0.78, cy + math.sin(a) * r * 0.78,
                        cx + math.cos(a) * r * (1.05 if k % 2 else 0.95), cy + math.sin(a) * r * (1.05 if k % 2 else 0.95)],
                       fill=sun + (255,), width=wk)
            d.ellipse([cx - r * 0.56, cy - r * 0.56, cx + r * 0.56, cy + r * 0.56], fill=(255, 224, 130, 255))
            d.ellipse([cx - r * 0.42, cy - r * 0.48, cx + r * 0.2, cy + r * 0.14], fill=(255, 240, 190, 140))
        else:
            if not plain:
                layer.alpha_composite(_radial(W, H, cx, cy, r * 1.8, (160, 170, 255), 0.5))
            moon = _layer(W, H)
            ImageDraw.Draw(moon).ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], fill=(240, 240, 222, 255))
            cut = Image.new("L", (W, H), 0)
            ImageDraw.Draw(cut).ellipse([cx - r * 0.2, cy - r * 0.72, cx + r * 0.92, cy + r * 0.42], fill=255)
            moon.putalpha(ImageChops.subtract(moon.getchannel("A"), cut))
            layer.alpha_composite(moon)
        if code != 2:
            return
        cx, cy, r = cx + r * 0.3, cy + r * 0.35, r * 0.7
    if code in (45, 48):
        for k in range(4):
            y = cy - r * 0.5 + k * r * 0.36
            d.line([cx - r * (0.95 - 0.14 * (k % 2)), y, cx + r * (0.95 - 0.14 * ((k + 1) % 2)), y], fill=cloud + (230,), width=wk)
        return
    col = cloud if code not in (95, 96, 99) else (160, 165, 205)
    if not plain:
        sh = _layer(W, H)                                          # a soft shadow under the cloud
        ImageDraw.Draw(sh).ellipse([cx - r * 0.9, cy + r * 0.3, cx + r * 0.9, cy + r * 0.62], fill=(0, 0, 20, 90))
        layer.alpha_composite(sh.filter(ImageFilter.GaussianBlur(max(2, r * 0.12))))
    d.ellipse([cx - r * 0.95, cy - r * 0.15, cx - r * 0.15, cy + r * 0.5], fill=col + (255,))
    d.ellipse([cx - r * 0.55, cy - r * 0.62, cx + r * 0.38, cy + r * 0.36], fill=col + (255,))
    d.ellipse([cx - r * 0.02, cy - r * 0.36, cx + r * 0.95, cy + r * 0.5], fill=col + (255,))
    d.rectangle([cx - r * 0.55, cy + r * 0.05, cx + r * 0.55, cy + r * 0.5], fill=col + (255,))
    if not plain:
        d.ellipse([cx - r * 0.45, cy - r * 0.5, cx + r * 0.1, cy - r * 0.05], fill=(255, 255, 255, 90))
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        for k in range(3):
            x = cx - r * 0.5 + k * r * 0.5
            d.line([x, cy + r * 0.68, x - r * 0.16, cy + r * 1.05], fill=rain + (255,), width=wk)
    elif code in (71, 73, 75, 77, 85, 86):
        for k in range(3):
            x = cx - r * 0.5 + k * r * 0.5
            d.ellipse([x - r * 0.09, cy + r * 0.72, x + r * 0.09, cy + r * 0.9], fill=snow + (255,))
    elif code in (95, 96, 99):
        d.polygon([(cx + r * 0.08, cy + r * 0.45), (cx - r * 0.28, cy + r * 0.88), (cx, cy + r * 0.88),
                   (cx - r * 0.16, cy + r * 1.25), (cx + r * 0.34, cy + r * 0.72), (cx + r * 0.06, cy + r * 0.72)],
                  fill=(0, 0, 0, 0) if plain else sun + (255,))              # on paper the bolt is a hole in the cloud


def _kind(code):
    c = int(code)
    if c in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
        return "rain"
    if c in (71, 73, 75, 77, 85, 86):
        return "snow"
    if c in (45, 48):
        return "fog"
    return "clear" if c in (0, 1) else "cloud"


# ---------------------------------------------------------------- palettes ---

def _daypart(n):
    h = n.hour + n.minute / 60
    if 5 <= h < 9:
        return "morning", [(36, 20, 74), (196, 84, 120), (255, 196, 136)], "Good morning"
    if 9 <= h < 17:
        return "day", [(12, 36, 98), (38, 108, 196), (150, 214, 255)], "Good day" if h >= 12 else "Good morning"
    if 17 <= h < 21:
        return "evening", [(38, 14, 72), (176, 52, 112), (255, 152, 92)], "Good evening"
    return "night", [(6, 8, 30), (30, 24, 84), (96, 64, 168)], "Good night" if h >= 23 or h < 4 else "Good evening"


def _weather_palette(dat, n):
    w = dat.get("weather")
    if not w:
        return _daypart(n)[1]
    c = w["now"]
    k = _kind(c["code"])
    if not c["day"]:
        return [(5, 7, 26), (26, 30, 86), (86, 90, 170)] if k != "rain" else [(4, 8, 24), (14, 40, 80), (50, 100, 150)]
    return {"clear": [(14, 52, 128), (52, 134, 214), (255, 200, 120)], "cloud": [(24, 40, 82), (74, 100, 150), (170, 190, 220)],
            "rain": [(10, 28, 56), (26, 78, 120), (96, 160, 190)], "snow": [(40, 60, 100), (120, 150, 200), (225, 235, 250)],
            "fog": [(44, 44, 70), (110, 110, 140), (200, 200, 220)]}[k]


NEWS_PAL = {"CH": ([(34, 8, 24), (132, 26, 66), (240, 96, 92)], (255, 176, 120)),
            "WORLD": ([(6, 16, 44), (20, 72, 128), (84, 190, 226)], (150, 218, 255))}
HOURS_PAL = [(10, 16, 46), (32, 52, 126), (96, 150, 232)]
OUTLOOK_PAL = [(26, 14, 58), (84, 40, 124), (226, 122, 172)]


def _fmt_day(iso):
    return _wd(datetime.date.fromisoformat(iso), short=True)


def _date_str(n):
    return f"{n.day}. {_mon(n)} {n.year}" if _lang() == "de" else f"{n.day} {n.strftime('%B %Y')}"


# ------------------------------------------------------- graphic building blocks ---

_TEMP_STOPS = [(-12, (170, 205, 255)), (-2, (110, 215, 255)), (6, (120, 245, 190)), (13, (255, 235, 120)),
               (21, (255, 168, 80)), (30, (255, 96, 74))]


def temp_colour(t):
    """Temperature as a colour: icy blue, cyan, green, yellow, orange, red (bright, so it holds on a few colour steps)."""
    if t <= _TEMP_STOPS[0][0]:
        return _TEMP_STOPS[0][1]
    for (t0, c0), (t1, c1) in zip(_TEMP_STOPS, _TEMP_STOPS[1:]):
        if t <= t1:
            k = (t - t0) / float(t1 - t0)
            return tuple(int(c0[i] + (c1[i] - c0[i]) * k) for i in range(3))
    return _TEMP_STOPS[-1][1]


def gauge(layer, cx, cy, r, frac, colour, width=None):
    """A ring meter: a dim track over 270 degrees and the bright part filled to `frac` (0..1), round at both ends."""
    w = width or max(4, int(r * 0.26))
    d = ImageDraw.Draw(layer)
    box = [cx - r, cy - r, cx + r, cy + r]
    d.arc(box, 135, 405, fill=(255, 255, 255, 70), width=w)
    frac = max(0.02, min(1.0, frac))
    end = 135 + 270 * frac
    glow = _layer(*layer.size)
    ImageDraw.Draw(glow).arc(box, 135, end, fill=tuple(colour) + (255,), width=int(w * 1.9))
    layer.alpha_composite(Image.merge("RGBA", glow.split()[:3] + (glow.getchannel("A").filter(ImageFilter.GaussianBlur(w * 0.5)).point(lambda v: int(v * 0.45)),)))
    d.arc(box, 135, end, fill=tuple(colour) + (255,), width=w)
    for ang in (135, end):                                          # round caps
        x, y = cx + (r - w / 2) * math.cos(math.radians(ang)), cy + (r - w / 2) * math.sin(math.radians(ang))
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=(tuple(colour) + (255,)) if ang == end else (255, 255, 255, 70))


def droplet(layer, cx, cy, h, fill=(120, 190, 255, 255)):
    """A raindrop about h tall."""
    d = ImageDraw.Draw(layer)
    r = h * 0.32
    d.ellipse([cx - r, cy + h * 0.5 - 2 * r, cx + r, cy + h * 0.5], fill=fill)
    d.polygon([(cx, cy - h * 0.5), (cx - r * 0.92, cy + h * 0.5 - 1.35 * r), (cx + r * 0.92, cy + h * 0.5 - 1.35 * r)], fill=fill)


def _hm(t):
    h, m = t.split(":")
    return int(h) + int(m) / 60.0


# ------------------------------------------------------------- the scenes ---
# each returns the type layer (RGBA, W*SS x H*SS); `palette` says which colours the field behind uses

CLOCK_LINE = (0.18, 0.82, 0.462)          # the seconds line under the time: x from, x to (of the width), y (of the height)


def scene_clock(W, H, n, dat):
    L = _layer(W, H)
    part, pal, greet = _daypart(n)
    acc = pal[2]
    glow_text(L, (W // 2, int(H * 0.07)), "F O R T U N A   B R I E F", sfont(int(W * 0.05)), (235, 235, 255), "mm", glow=acc, shadow=False)
    glow_text(L, (W // 2, int(H * 0.145)), greet, fit("regular", W * 0.075, greet, W * 0.8), (255, 246, 230), "mm", glow=acc)
    tm = n.strftime("%H:%M")
    glow_text(L, (W // 2, int(H * 0.30)), tm, fit("bold", W * 0.5, "88:88", W * 0.86), (255, 252, 244), "mm", glow=acc, radius=int(W * 0.045), strength=0.9)
    x0, x1, ly = CLOCK_LINE                                         # the track of the seconds line (the moving part is drawn per frame)
    d = ImageDraw.Draw(L)
    d.rounded_rectangle([W * x0, H * ly - W * 0.006, W * x1, H * ly + W * 0.006], radius=W * 0.006, fill=(255, 255, 255, 60))
    wd = _wd(n)
    glow_text(L, (W // 2, int(H * 0.555)), wd, fit("bold", W * 0.14, wd, W * 0.88), WHITE, "mm", glow=acc)
    ds = _date_str(n)
    glow_text(L, (W // 2, int(H * 0.645)), ds, fit("regular", W * 0.09, ds, W * 0.88), (240, 240, 255), "mm", glow=acc, strength=0.5)
    w = dat.get("weather")
    if w:
        c = w["now"]
        glass(L, (W * 0.12, H * 0.725, W * 0.88, H * 0.845))
        icon(L, c["code"], c["day"], W * 0.235, H * 0.785, W * 0.058)
        txt = f"{round(c['temp'])}°  {WMO.get(c['code'], '')}"
        glow_text(L, (W * 0.35, int(H * 0.785)), txt, fit("bold", W * 0.075, txt, W * 0.5), WHITE, "lm")
    glow_text(L, (W // 2, int(H * 0.93)), PLACE, fit("regular", W * 0.055, PLACE, W * 0.88), (230, 230, 246), "mm")
    return L


def scene_weather(W, H, n, dat):
    L = _layer(W, H)
    w = dat.get("weather")
    pal = _weather_palette(dat, n)
    if not w:
        glow_text(L, (W // 2, H // 2), "Weather offline", sfont(int(W * 0.1)), (255, 228, 170), "mm", glow=(255, 190, 90))
        return L
    c = w["now"]
    acc = (255, 214, 140)
    glow_text(L, (W // 2, int(H * 0.055)), "WEATHER NOW", sfont(int(W * 0.056)), (240, 244, 255), "mm", glow=pal[2], shadow=False)
    icon(L, c["code"], c["day"], W // 2, int(H * 0.215), int(W * 0.165))
    tt = f"{round(c['temp'])}°"
    glow_text(L, (W // 2, int(H * 0.455)), tt, fit("light", W * 0.34, tt, W * 0.7), temp_colour(c["temp"]) if c["temp"] < 4 else (255, 255, 255), "mm", glow=pal[2], radius=int(W * 0.05))
    cond = WMO.get(c["code"], "")
    glow_text(L, (W // 2, int(H * 0.594)), cond, fit("bold", W * 0.1, cond, W * 0.9), acc, "mm", glow=(255, 160, 70), strength=0.6)
    # three ring meters: how it feels, the wind, the air's wetness
    r = W * 0.122
    for i, (lab, val, frac, col, unit) in enumerate((
            ("FEELS", f"{round(c['feels'])}°", (c["feels"] + 15) / 50.0, temp_colour(c["feels"]), ""),
            ("WIND", f"{round(c['wind'])}", c["wind"] / 60.0, (150, 228, 255), "km/h"),
            ("HUMID", f"{round(c['humidity'])}%", c["humidity"] / 100.0, (125, 175, 255), ""))):
        cx, cy = W * (0.19 + 0.31 * i), H * 0.77
        gauge(L, cx, cy, r, frac, col)
        glow_text(L, (cx, cy - (r * 0.12 if unit else 0)), val, sfont(int(W * 0.07)), WHITE, "mm")
        if unit:
            glow_text(L, (cx, cy + r * 0.62), unit, sfont(int(W * 0.04)), (225, 238, 255), "mm")
        glow_text(L, (cx, cy + r * 1.42), lab, sfont(int(W * 0.05)), (236, 242, 255), "mm")
    glow_text(L, (W // 2, int(H * 0.962)), PLACE, fit("bold", W * 0.054, PLACE, W * 0.9), (232, 238, 252), "mm", shadow=False)
    return L


def _smooth(vals, up=8):
    """Cubic-ish smoothing of a short series for a flowing curve."""
    v = np.asarray(vals, np.float32)
    x = np.arange(len(v))
    xs = np.linspace(0, len(v) - 1, (len(v) - 1) * up + 1)
    y = np.interp(xs, x, v)
    k = np.hanning(up * 2 + 1)
    k /= k.sum()
    pad = np.pad(y, up, mode="edge")
    return xs, np.convolve(pad, k, mode="same")[up:-up]


def scene_hours(W, H, n, dat):
    L = _layer(W, H)
    w = dat.get("weather")
    glow_text(L, (W // 2, int(H * 0.055)), "THE NEXT 24 HOURS", sfont(int(W * 0.056)), (240, 244, 255), "mm", glow=HOURS_PAL[2], shadow=False)
    if not w or len(w["hours"]) < 4:
        glow_text(L, (W // 2, H // 2), "No forecast", sfont(int(W * 0.1)), (255, 228, 170), "mm", glow=(255, 190, 90))
        return L
    hrs = w["hours"][:24]
    temps = [h["temp"] for h in hrs]
    lo, hi = min(temps), max(temps)
    span = max(5.0, hi - lo)
    X0, X1, Y0, Y1 = W * 0.10, W * 0.90, H * 0.30, H * 0.575
    xs, ys = _smooth(temps)
    px = X0 + (X1 - X0) * xs / (len(hrs) - 1)
    py = Y1 - (Y1 - Y0) * (ys - lo) / span
    # the ribbon: the area under the curve fades down, every column in the colour of that hour's temperature
    cols = np.array([temp_colour(float(v)) for v in ys], np.float32)
    yy = np.arange(H, dtype=np.float32)[:, None]
    xi = np.clip(np.round(px).astype(int), 0, W - 1)
    line_y = np.full(W, Y1, np.float32)
    colr = np.zeros((W, 3), np.float32)
    for k in range(len(px) - 1):
        a0, a1 = int(round(px[k])), int(round(px[k + 1]))
        for x in range(max(0, a0), min(W, a1 + 1)):
            u = 0.0 if a1 == a0 else (x - a0) / float(a1 - a0)
            line_y[x] = py[k] + (py[k + 1] - py[k]) * u
            colr[x] = cols[k] + (cols[k + 1] - cols[k]) * u
    depth = np.clip((yy - line_y[None, :]) / max(1.0, (Y1 + H * 0.02) - Y0), 0, 1)
    inside = np.zeros(W, bool)
    inside[max(0, int(round(px[0]))):min(W, int(round(px[-1])) + 1)] = True                       # only under the curve
    alpha = np.where((yy >= line_y[None, :]) & inside[None, :], np.clip(1.0 - depth, 0, 1) ** 1.3 * 0.62, 0.0)
    area = np.zeros((H, W, 4), np.uint8)
    area[..., :3] = colr[None, :, :].astype(np.uint8)
    area[..., 3] = (alpha * 255).astype(np.uint8)
    area[: int(Y0 - H * 0.04)] = 0
    L.alpha_composite(Image.fromarray(area, "RGBA"))
    d = ImageDraw.Draw(L)
    glow = _layer(W, H)
    gd = ImageDraw.Draw(glow)
    lw = max(3, int(W * 0.018))
    for k in range(len(px) - 1):                                           # the line itself, coloured hour by hour
        col = tuple(int(v) for v in cols[k])
        gd.line([px[k], py[k], px[k + 1], py[k + 1]], fill=col + (255,), width=int(lw * 2.2))
        d.line([px[k], py[k], px[k + 1], py[k + 1]], fill=col + (255,), width=lw)
    L.alpha_composite(Image.merge("RGBA", glow.split()[:3] + (glow.getchannel("A").filter(ImageFilter.GaussianBlur(W * 0.016)).point(lambda v: int(v * 0.5)),)))
    for k in range(len(px) - 1):
        d.line([px[k], py[k], px[k + 1], py[k + 1]], fill=tuple(int(v) for v in cols[k]) + (255,), width=lw)
    i_hi, i_lo = temps.index(hi), temps.index(lo)
    for i in sorted({0, i_hi, i_lo}):                                       # now, the high and the low, each with its temperature
        x = X0 + (X1 - X0) * i / (len(hrs) - 1)
        y = Y1 - (Y1 - Y0) * (temps[i] - lo) / span
        r = W * (0.026 if i == 0 else 0.022)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 255), outline=tuple(temp_colour(temps[i])) + (255,), width=max(2, int(W * 0.01)))
        glow_text(L, (min(max(x, W * 0.11), W * 0.89), int(y - W * 0.078)), f"{round(temps[i])}°", sfont(int(W * 0.072)), tuple(temp_colour(temps[i])), "mm")
    for i in range(0, len(hrs), 3):                                        # the hours along the foot, with the weather above them
        x = X0 + (X1 - X0) * i / (len(hrs) - 1)
        glow_text(L, (x, int(Y1 + H * 0.052)), hrs[i]["time"][:2], sfont(int(W * 0.052)), (232, 240, 255), "mm")
    for k, i in enumerate((0, 6, 12, 18)):
        x = X0 + (X1 - X0) * (i + 1.5) / (len(hrs) - 1) if i else X0 + W * 0.06
        icon(L, hrs[i]["code"], 6 <= int(hrs[i]["time"][:2]) < 21, x, H * 0.165, W * 0.07)
    # rain: drops for every third hour, one to three by the chance of rain (or just a line when it stays dry)
    if max(h["pop"] for h in hrs) < 10:
        droplet(L, W * 0.21, H * 0.79, H * 0.07, (255, 255, 255, 120))
        glow_text(L, (W * 0.56, int(H * 0.79)), "No rain expected", fit("bold", W * 0.075, "No rain expected", W * 0.62), (235, 244, 255), "mm")
    else:
        glow_text(L, (W // 2, int(H * 0.715)), "RAIN CHANCE %", sfont(int(W * 0.05)), (200, 226, 255), "mm")
        for k, i in enumerate(range(0, len(hrs), 3)[:8]):                    # one drop per three hours: the bigger, the wetter
            x = X0 + (X1 - X0) * i / (len(hrs) - 1)
            pop = hrs[i]["pop"]
            dh = H * (0.028 + 0.075 * pop / 100.0)
            droplet(L, x, H * 0.835 - dh * 0.5, dh, (120, 190, 255, 255) if pop >= 10 else (255, 255, 255, 90))
            glow_text(L, (x, int(H * 0.895)), str(pop), sfont(int(W * 0.056)), (232, 242, 255) if pop >= 10 else (180, 200, 230), "mm")
    hl = _x(f"high {round(hi)}° at {hrs[i_hi]['time'][:2]}h  ·  low {round(lo)}° at {hrs[i_lo]['time'][:2]}h",
            f"max. {round(hi)}° um {hrs[i_hi]['time'][:2]} Uhr  ·  min. {round(lo)}° um {hrs[i_lo]['time'][:2]} Uhr")
    glow_text(L, (W // 2, int(H * 0.955)), hl, fit("bold", W * 0.055, hl, W * 0.92), (238, 244, 255), "mm", shadow=False)
    return L


def scene_outlook(W, H, n, dat):
    L = _layer(W, H)
    w = dat.get("weather")
    glow_text(L, (W // 2, int(H * 0.055)), "THE DAYS AHEAD", sfont(int(W * 0.056)), (244, 238, 255), "mm", glow=OUTLOOK_PAL[2], shadow=False)
    if not w:
        glow_text(L, (W // 2, H // 2), "No forecast", sfont(int(W * 0.1)), (255, 228, 170), "mm", glow=(255, 190, 90))
        return L
    days = w["days"][:4]
    lo, hi = min(x["min"] for x in days), max(x["max"] for x in days)
    span = max(6.0, hi - lo)
    Y0, Y1 = H * 0.335, H * 0.60                                            # the shared temperature scale for all four days
    d = ImageDraw.Draw(L)
    cw = W * 0.2
    for i, dy in enumerate(days):
        cx = W * (0.14 + 0.24 * i)
        glow_text(L, (cx, int(H * 0.115)), "Today" if i == 0 else _fmt_day(dy["date"]), sfont(int(W * 0.066)), WHITE, "mm")
        icon(L, dy["code"], True, cx, H * 0.195, W * 0.074)
        ytop = Y1 - (Y1 - Y0) * (dy["max"] - lo) / span
        ybot = Y1 - (Y1 - Y0) * (dy["min"] - lo) / span
        ybot = max(ybot, ytop + W * 0.08)
        # a capsule floating between the day's low and high, blue at the bottom into the colour of the high at the top
        cap = Image.new("RGBA", (int(W * 0.1) + 2, int(ybot - ytop) + 2), (0, 0, 0, 0))
        cc, ch = cap.size
        grad = np.zeros((ch, cc, 4), np.uint8)
        t_top, t_bot = temp_colour(dy["max"]), temp_colour(dy["min"])
        for yv in range(ch):
            u = yv / max(1, ch - 1)
            grad[yv, :, :3] = [int(t_top[k] + (t_bot[k] - t_top[k]) * u) for k in range(3)]
            grad[yv, :, 3] = 255
        mask = Image.new("L", cap.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cc - 1, ch - 1], radius=cc // 2, fill=255)
        capl = Image.fromarray(grad, "RGBA")
        capl.putalpha(mask)
        halo = capl.filter(ImageFilter.GaussianBlur(W * 0.014))
        L.alpha_composite(Image.merge("RGBA", halo.split()[:3] + (halo.getchannel("A").point(lambda v: int(v * 0.5)),)), (int(cx - cc / 2), int(ytop)))
        L.alpha_composite(capl, (int(cx - cc / 2), int(ytop)))
        d.rounded_rectangle([cx - cc / 2, ytop, cx + cc / 2, ytop + ch - 2], radius=cc // 2, outline=(255, 255, 255, 190), width=max(1, int(W * 0.006)))
        glow_text(L, (cx, int(ytop - H * 0.032)), f"{round(dy['max'])}°", sfont(int(W * 0.074)), tuple(t_top), "mm")
        glow_text(L, (cx, int(ybot + H * 0.034)), f"{round(dy['min'])}°", sfont(int(W * 0.066)), tuple(t_bot), "mm")
        # rain: a drop and the chance
        droplet(L, cx - W * 0.05, H * 0.697, H * 0.042, (125, 190, 255, 255) if dy["pop"] >= 10 else (255, 255, 255, 110))
        glow_text(L, (cx + W * 0.025, int(H * 0.697)), f"{dy['pop']}%", sfont(int(W * 0.056)), (232, 242, 255) if dy["pop"] >= 10 else (190, 205, 230), "mm")
    # the sun's day: an arc from sunrise to sunset with the sun where it is right now
    t0 = w["days"][0]
    sr, ss = _hm(t0["sunrise"]), _hm(t0["sunset"])
    hnow = n.hour + n.minute / 60.0
    ax0, ax1, ay, ah = W * 0.17, W * 0.83, H * 0.915, H * 0.085
    glass(L, (W * 0.05, H * 0.745, W * 0.95, H * 0.985))
    d = ImageDraw.Draw(L)
    dl = ss - sr
    glow_text(L, (W // 2, int(H * 0.778)), _x(f"{int(dl)}h {int(round((dl % 1) * 60)):02d}m of daylight", f"{int(dl)} h {int(round((dl % 1) * 60)):02d} min Tageslicht"), sfont(int(W * 0.062)), (240, 244, 255), "mm")
    d.line([ax0 - W * 0.05, ay, ax1 + W * 0.05, ay], fill=(255, 255, 255, 130), width=max(1, int(W * 0.007)))
    steps = 40
    arc = [(ax0 + (ax1 - ax0) * k / steps, ay - ah * math.sin(math.pi * k / steps)) for k in range(steps + 1)]
    for k in range(0, steps, 2):
        d.line([arc[k], arc[k + 1]], fill=(255, 214, 140, 255), width=max(3, int(W * 0.012)))
    u = (hnow - sr) / max(0.1, dl)
    if 0 <= u <= 1:                                                         # the sun, where it is now
        sx, sy = ax0 + (ax1 - ax0) * u, ay - ah * math.sin(math.pi * u)
        L.alpha_composite(_radial(W, H, sx, sy, W * 0.13, (255, 200, 90), 0.9))
        d.ellipse([sx - W * 0.03, sy - W * 0.03, sx + W * 0.03, sy + W * 0.03], fill=(255, 232, 150, 255), outline=(255, 255, 255, 255), width=2)
    glow_text(L, (ax0, int(ay + H * 0.034)), t0["sunrise"], sfont(int(W * 0.062)), (255, 232, 190), "mm")
    glow_text(L, (ax1, int(ay + H * 0.034)), t0["sunset"], sfont(int(W * 0.062)), (255, 232, 190), "mm")
    return L


WEEKEND_PAL = [(6, 18, 40), (22, 66, 116), (150, 208, 248)]
SUMMITS = {"Valais": 4400, "Graubünden": 3200, "Central CH": 3240, "Bernese Alps": 4160, "Eastern CH": 2500}    # a peak per region, drawn to scale
REGION_DE = {"Valais": "Wallis", "Graubünden": "Graubünden", "Central CH": "Zentralschweiz", "Bernese Alps": "Berner Alpen", "Eastern CH": "Ostschweiz"}
ABBR = {"Valais": "ZER", "Graubünden": "DAV", "Central CH": "ENG", "Bernese Alps": "JUN", "Eastern CH": "SÄN"}
ZMIN, ZMAX = 1000, 4500


def scene_weekend(W, H, n, dat, k):
    """Saturday (k=0) or Sunday (k=1) in the Swiss Alps as a cross-section: five peaks to scale, the cloud as a band between its
    base and its top, the 0 degree line, a snow cap above it, and below each peak the temperature and the snow depth."""
    L = _layer(W, H)
    mt = dat.get("mountains")
    iso = weekend_dates(n)[k]
    day = datetime.date.fromisoformat(iso)
    glow_text(L, (W // 2, int(H * 0.038)), "MOUNTAIN WEEKEND", sfont(int(W * 0.052)), (225, 238, 255), "mm", glow=WEEKEND_PAL[2], shadow=False)
    title = f"{_wd(day).upper()} {day.day}. {_mon(day, True).upper()}" if _lang() == "de" else f"{_wd(day).upper()} {day.day} {_mon(day, True).upper()}"
    glow_text(L, (W // 2, int(H * 0.088)), title, fit("bold", W * 0.088, title, W * 0.92), WHITE, "mm", glow=WEEKEND_PAL[2])
    if not mt or any(iso not in r["days"] for r in mt):
        glow_text(L, (W // 2, H // 2), "No mountain forecast", fit("bold", W * 0.09, "No mountain forecast", W * 0.9), (255, 228, 170), "mm")
        return L
    X0, X1, Y0, Y1 = W * 0.115, W * 0.985, H * 0.215, H * 0.675
    zy = lambda z: Y1 - (Y1 - Y0) * (min(max(z, ZMIN), ZMAX) - ZMIN) / float(ZMAX - ZMIN)
    glass(L, (W * 0.015, H * 0.135, W * 0.992, H * 0.70), r=int(W * 0.03))
    d = ImageDraw.Draw(L)
    for z in (2000, 3000, 4000):                                           # the height scale
        d.line([X0 - W * 0.02, zy(z), X1, zy(z)], fill=(255, 255, 255, 55), width=1)
        glow_text(L, (W * 0.065, zy(z)), f"{z // 1000}k", sfont(int(W * 0.052)), (220, 236, 255), "mm")
    colw = (X1 - X0) / len(mt)
    snow_total = 0
    for i, r in enumerate(mt):
        dd = r["days"][iso]
        cx = X0 + colw * (i + 0.5)
        half = colw * 0.47
        peak = SUMMITS.get(r["name"], r["elev"] + 600)
        # the mountain: rock below the freezing level, snow above it
        pts = [(cx - half, Y1), (cx - half * 0.5, zy(ZMIN + (peak - ZMIN) * 0.78)), (cx - half * 0.12, zy(ZMIN + (peak - ZMIN) * 0.93)),
               (cx, zy(peak)), (cx + half * 0.3, zy(ZMIN + (peak - ZMIN) * 0.8)), (cx + half * 0.58, zy(ZMIN + (peak - ZMIN) * 0.62)), (cx + half, Y1)]
        rock = _layer(W, H)
        ImageDraw.Draw(rock).polygon(pts, fill=(58, 74, 108, 255))
        L.alpha_composite(rock)
        frz = dd.get("frz")
        if frz:
            above = Image.new("L", (W, H), 0)
            ImageDraw.Draw(above).rectangle([0, 0, W, int(zy(frz))], fill=255)
            snow = _layer(W, H)
            ImageDraw.Draw(snow).polygon(pts, fill=(238, 246, 255, 255))
            snow.putalpha(ImageChops.multiply(snow.getchannel("A"), above))
            L.alpha_composite(snow)
        d.line(pts, fill=(255, 255, 255, 110), width=1, joint="curve")
        d = ImageDraw.Draw(L)
        if frz:                                                            # the 0 degree line
            y = zy(frz)
            for x in range(int(cx - colw * 0.5), int(cx + colw * 0.5), max(6, int(W * 0.026))):
                d.line([x, y, x + max(3, int(W * 0.014)), y], fill=(110, 225, 255, 255), width=max(2, int(W * 0.008)))
        # the cloud: a soft white band from its base to its top
        base, top = dd.get("base"), dd.get("top")
        if base:
            z0, z1 = base, (top if top and top > base else base + 250)
            band = _layer(W, H)
            bd = ImageDraw.Draw(band)
            y0, y1 = zy(z1), max(zy(z0), zy(z1) + W * 0.07)
            hgt = y1 - y0
            fillc, edge = (232, 238, 250, 222), (150, 172, 205, 255)        # a grey-white band, edged so it shows against the snow
            for off, rr in ((-0.26, 0.2), (0.0, 0.26), (0.27, 0.2)):         # a puffy top
                bd.ellipse([cx + colw * (off - rr), y0 - W * 0.035, cx + colw * (off + rr), y0 + W * 0.05], fill=fillc, outline=edge, width=2)
            bd.rounded_rectangle([cx - colw * 0.5, y0 + W * 0.012, cx + colw * 0.5, y1], radius=int(min(hgt / 2, W * 0.05)), fill=fillc, outline=edge, width=2)
            for off, rr in ((-0.26, 0.2), (0.0, 0.26), (0.27, 0.2)):         # (the puffs again, without their outline, to join them to the band)
                bd.ellipse([cx + colw * (off - rr) + 2, y0 - W * 0.035 + 2, cx + colw * (off + rr) - 2, y0 + W * 0.05], fill=fillc)
            L.alpha_composite(band)
            d = ImageDraw.Draw(L)
        # the forecast height: where the numbers apply
        ey = zy(r["elev"])
        d.ellipse([cx - W * 0.014, ey - W * 0.014, cx + W * 0.014, ey + W * 0.014], fill=(255, 214, 120, 255), outline=(20, 20, 30, 255), width=1)
        icon(L, dd["code"], True, cx, H * 0.172, W * 0.052)
        # below the peak: the name, the day's high, the snow depth (now plus what is forecast), the new snow
        glow_text(L, (cx, int(H * 0.735)), ABBR.get(r["name"], r["name"][:3].upper()), sfont(int(W * 0.062)), WHITE, "mm")
        glow_text(L, (cx, int(H * 0.795)), f"{round(dd['max'])}°", sfont(int(W * 0.066)), tuple(temp_colour(dd["max"])), "mm")
        depth = dd.get("depth")
        glow_text(L, (cx, int(H * 0.855)), f"{round(depth)}" if depth is not None else "-", sfont(int(W * 0.066)), (236, 246, 255), "mm")
        if dd["snow"] >= 0.5:
            glow_text(L, (cx, int(H * 0.91)), f"+{dd['snow']:.0f}" if dd["snow"] >= 1 else f"+{dd['snow']:.1f}", sfont(int(W * 0.056)), (130, 215, 255), "mm")
            snow_total += 1
    # the key, so the picture explains itself
    d = ImageDraw.Draw(L)
    glow_text(L, (W * 0.012, int(H * 0.795)), "hi", sfont(int(W * 0.04)), (200, 222, 250), "lm", shadow=False)
    glow_text(L, (W * 0.012, int(H * 0.855)), "cm", sfont(int(W * 0.04)), (200, 222, 250), "lm", shadow=False)
    ky = int(H * 0.962)
    d.rounded_rectangle([W * 0.045, ky - W * 0.02, W * 0.115, ky + W * 0.02], radius=int(W * 0.02), fill=(255, 255, 255, 235))
    glow_text(L, (W * 0.125, ky), "cloud", sfont(int(W * 0.05)), (236, 244, 255), "lm")
    for x in range(int(W * 0.40), int(W * 0.50), int(W * 0.03)):
        d.line([x, ky, x + int(W * 0.016), ky], fill=(110, 225, 255, 255), width=max(2, int(W * 0.009)))
    glow_text(L, (W * 0.515, ky), "0°C", sfont(int(W * 0.05)), (236, 244, 255), "lm")
    d.ellipse([W * 0.70, ky - W * 0.014, W * 0.728, ky + W * 0.014], fill=(255, 214, 120, 255))
    glow_text(L, (W * 0.74, ky), "here", sfont(int(W * 0.05)), (236, 244, 255), "lm")
    return L


def story_picture(path, w, h, radius):
    """The story's picture cropped to fill w x h (a little above centre, where faces are), lifted for an LED wall (more contrast
    and colour), with rounded corners. -> RGBA or None."""
    try:
        from PIL import ImageEnhance
        im = Image.open(path).convert("RGB")
        scale = max(w / im.width, h / im.height)
        im = im.resize((max(w, int(im.width * scale + 0.5)), max(h, int(im.height * scale + 0.5))), Image.LANCZOS)
        left = (im.width - w) // 2
        top = int((im.height - h) * 0.35)
        im = im.crop((left, top, left + w, top + h))
        im = ImageEnhance.Contrast(im).enhance(1.22)
        im = ImageEnhance.Color(im).enhance(1.25)
        im = ImageEnhance.Sharpness(im).enhance(1.4)
        out = im.convert("RGBA")
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        out.putalpha(mask)
        return out
    except Exception:
        return None


def scene_weekend_summary(W, H, n, dat):
    """The mountain weekend in a few words (written by the AI), with the numbers it rests on."""
    L = _layer(W, H)
    mt = dat.get("mountains") or []
    glow_text(L, (W // 2, int(H * 0.05)), "MOUNTAIN WEEKEND", sfont(int(W * 0.056)), (225, 238, 255), "mm", glow=WEEKEND_PAL[2], shadow=False)
    glow_text(L, (W // 2, int(H * 0.105)), "THE SHORT VERSION", fit("bold", W * 0.088, "THE SHORT VERSION", W * 0.92), WHITE, "mm", glow=WEEKEND_PAL[2])
    d = ImageDraw.Draw(L)
    text = dat.get("mountain_ai") or ""
    for fs in (0.084, 0.076, 0.068, 0.062):                        # the largest size at which the summary fits above the numbers
        tf = sfont(int(W * fs))
        lines = wrap(d, text, tf, W * 0.86)
        lh = int(W * fs * 1.32)
        if lh * len(lines) <= H * 0.50:
            break
    y = H * 0.185
    d.rounded_rectangle([W * 0.045, y + 2, W * 0.045 + W * 0.014, y + lh * len(lines) - 4], radius=W * 0.007, fill=tuple(WEEKEND_PAL[2]) + (255,))
    for ln in lines:
        glow_text(L, (W * 0.085, y), ln, tf, (248, 250, 255), "la")
        y += lh
    # the two days in numbers: the range of highs, the most new snow, the lowest cloud
    isos = weekend_dates(n)
    for j, iso in enumerate(isos):
        rows = [r["days"][iso] for r in mt if iso in r["days"]]
        if not rows:
            continue
        x0 = W * (0.05 + 0.475 * j)
        glass(L, (x0, H * 0.745, x0 + W * 0.425, H * 0.945))
        day = _wd(datetime.date.fromisoformat(iso), short=True).upper()
        cw = W * 0.4
        glow_text(L, (x0 + W * 0.2125, int(H * 0.775)), day, sfont(int(W * 0.064)), WHITE, "mm")
        hi, lo = max(r["max"] for r in rows), min(r["max"] for r in rows)
        t1 = _x(f"{round(lo)}° to {round(hi)}°", f"{round(lo)}° bis {round(hi)}°")
        glow_text(L, (x0 + W * 0.2125, int(H * 0.822)), t1, fit("bold", W * 0.062, t1, cw), tuple(temp_colour((hi + lo) / 2)), "mm")
        snow = max(r["snow"] for r in rows)
        t2 = (_x(f"+{snow:.0f} cm snow", f"+{snow:.0f} cm Schnee") if snow >= 1 else
              (_x(f"+{snow:.1f} cm snow", f"+{snow:.1f} cm Schnee") if snow >= 0.5 else "no new snow"))
        glow_text(L, (x0 + W * 0.2125, int(H * 0.866)), t2, fit("bold", W * 0.054, t2, cw), (150, 220, 255), "mm")
        bases = [r["base"] for r in rows if r.get("base")]
        t3 = _x(f"cloud {min(bases) // 100 / 10:.1f}k m+", f"Wolken ab {min(bases) // 100 / 10:.1f}k m") if bases else "no cloud"
        glow_text(L, (x0 + W * 0.2125, int(H * 0.911)), t3, fit("bold", W * 0.054, t3, cw), (236, 244, 255), "mm")
    return L


SCI_PAL = [(4, 24, 30), (12, 84, 96), (120, 232, 200)]
SCI_ACCENTS = [(120, 232, 200), (255, 214, 120), (170, 190, 255)]


def scene_science(W, H, n, dat):
    """Three research highlights, each a card with its field and one plain sentence."""
    L = _layer(W, H)
    items = dat.get("science") or []
    glow_text(L, (W // 2, int(H * 0.055)), "RESEARCH HIGHLIGHTS", fit("bold", W * 0.064, "RESEARCH HIGHLIGHTS", W * 0.92), WHITE, "mm", glow=SCI_PAL[2])
    d = ImageDraw.Draw(L)
    top, gap = H * 0.115, H * 0.014
    rh = (H * 0.975 - top - gap * 2) / 3
    for i, it in enumerate(items[:3]):
        y = top + i * (rh + gap)
        acc = SCI_ACCENTS[i % 3]
        glass(L, (W * 0.04, y, W * 0.96, y + rh))
        d.rounded_rectangle([W * 0.04, y + rh * 0.06, W * 0.04 + W * 0.018, y + rh * 0.94], radius=W * 0.009, fill=tuple(acc) + (255,))
        tf = sfont(int(W * 0.05))
        pill(L, W * 0.1 + (d.textlength(it["topic"].upper(), font=tf) + tf.size * 1.2) / 2, y + rh * 0.17, it["topic"].upper(), tf, acc)
        for fs in (0.064, 0.058, 0.052):                           # the sentence, as large as fits the card
            bf = sfont(int(W * fs))
            lh = int(W * fs * 1.28)
            lines = wrap(d, it["line"], bf, W * 0.84)
            if lh * len(lines) <= rh * 0.60:
                break
        lines = wrap(d, it["line"], bf, W * 0.84, max(2, int(rh * 0.60 / lh)))
        yy = y + rh * 0.35
        for ln in lines:
            glow_text(L, (W * 0.1, yy), ln, bf, (246, 249, 252), "la")
            yy += lh
    return L


def scene_news(W, H, n, dat, k):
    L = _layer(W, H)
    story = dat["news"][k]
    total = len(dat["news"])
    pal, acc = NEWS_PAL[story["tag"]]
    d = ImageDraw.Draw(L)
    soft = _layer(W, H)
    tagname = _loc("SWITZERLAND" if story["tag"] == "CH" else "WORLD")
    tf = sfont(int(W * 0.05))
    pill(soft, W * 0.05 + (d.textlength(tagname, font=tf) + tf.size * 1.2) / 2, H * 0.05, tagname, tf, acc)
    glow_text(soft, (W * 0.95, H * 0.05), f"{k + 1:02d} / {total:02d}", sfont(int(W * 0.05), "regular"), (240, 242, 250), "rm", shadow=False)
    pic = None
    if story.get("img") and os.path.exists(story["img"]):
        pw, ph = int(W * 0.9), int(H * 0.285)
        pic = story_picture(story["img"], pw, ph, int(W * 0.035))
    if pic is not None:                                                   # a picture banner, then the headline
        px, py = int(W * 0.05), int(H * 0.095)
        glow = _layer(W, H)
        ImageDraw.Draw(glow).rounded_rectangle([px - 4, py - 4, px + pic.width + 4, py + pic.height + 4], radius=int(W * 0.04), fill=tuple(acc) + (255,))
        soft.alpha_composite(Image.merge("RGBA", glow.split()[:3] + (glow.getchannel("A").filter(ImageFilter.GaussianBlur(W * 0.02)).point(lambda v: int(v * 0.55)),)))
        soft.alpha_composite(pic, (px, py))
        ImageDraw.Draw(soft).rounded_rectangle([px, py, px + pic.width, py + pic.height], radius=int(W * 0.035), outline=(255, 255, 255, 210), width=max(2, int(W * 0.007)))
        y = H * 0.41
        for fs in (0.08, 0.072, 0.066):                                   # the largest size at which the whole headline fits in 3 lines
            hf = sfont(int(W * fs))
            lines = wrap(d, story["title"], hf, W * 0.84)
            lh = int(W * fs * 1.2)
            if len(lines) <= 3:
                break
        else:
            lines = wrap(d, story["title"], hf, W * 0.84, 4)
        room_lines = 2
    else:                                                                 # no picture: the headline takes the space
        y = H * 0.115
        hf = sfont(int(W * 0.088))
        lines = wrap(d, story["title"], hf, W * 0.84, 6)
        lh = int(W * 0.088 * 1.22)
        room_lines = None
    ImageDraw.Draw(soft).rounded_rectangle([W * 0.05, y + 4, W * 0.05 + W * 0.014, y + lh * len(lines) - 6], radius=W * 0.007, fill=tuple(acc) + (255,))
    for ln in lines:
        glow_text(soft, (W * 0.095, y), ln, hf, WHITE, "la", glow=acc, strength=0.28, radius=int(W * 0.018))
        y += lh
    y += lh * 0.4
    bf = sfont(int(W * 0.066), "regular")
    blh = int(W * 0.066 * 1.34)
    room = max(0, int((H * 0.915 - y) / blh))
    if room_lines:
        room = min(room, room_lines + 1)
    if story["text"] and room >= 2:
        for ln in wrap(d, story["text"], bf, W * 0.86, room):
            glow_text(soft, (W * 0.095, y), ln, bf, (245, 247, 252), "la", shadow=True)
            y += blh
    for j in range(total):                                                # which story we are on
        cx = W / 2 + (j - (total - 1) / 2) * W * 0.055
        r = W * (0.016 if j == k else 0.01)
        ImageDraw.Draw(soft).ellipse([cx - r, H * 0.955 - r, cx + r, H * 0.955 + r], fill=tuple(acc) + (255 if j == k else 90,))
    L.alpha_composite(soft)
    return L


# ------------------------------------------------------------ the show -----

class Sprite:
    """A pre-rendered soft round light for bokeh."""

    def __init__(self, r, colour):
        size = int(r * 2 + 2)
        self.im = _radial(size, size, r + 1, r + 1, r, colour, 0.9)
        self.r = r


def _overlay(name, t, img, W, H, dat, state):
    """Drifting lights on top: rain, snow, stars, bokeh (cheap: a few dozen small things per frame)."""
    rng = state.setdefault("rng", np.random.default_rng(7))
    if "p" not in state:
        state["p"] = rng.random((46, 4)).astype(np.float32)
        state["sp"] = [Sprite(r, c) for r, c in ((W * 0.05, (255, 220, 170)), (W * 0.08, (190, 200, 255)), (W * 0.035, (255, 255, 255)))]
    P = state["p"]
    d = ImageDraw.Draw(img, "RGBA")
    w = dat.get("weather")
    if name == "clock":
        nw = now()
        sec = (nw.second + nw.microsecond / 1e6) / 60.0
        x0, x1, ly = CLOCK_LINE
        acc = _daypart(nw)[1][2]
        ya, xa = H * ly, W * x0 + W * (x1 - x0) * sec
        for gw, ga in ((5, 40), (3, 90)):                              # a soft glow under the bright line
            d.line([W * x0, ya, xa, ya], fill=tuple(acc) + (ga,), width=gw)
        d.line([W * x0, ya, xa, ya], fill=(255, 250, 235, 255), width=1)
        d.ellipse([xa - 2, ya - 2, xa + 2, ya + 2], fill=(255, 255, 255, 255))
    if name == "weather" and w:
        kind, day = _kind(w["now"]["code"]), w["now"]["day"]
        if kind == "rain":
            for x, y0, sp, ln in P[:40]:
                y = ((y0 + t * (0.55 + sp * 0.5)) % 1.0) * (H + 20) - 10
                xx = x * W + y * 0.12
                d.line([xx, y, xx - W * 0.012, y + W * 0.05 * (0.6 + ln)], fill=(170, 210, 255, 150), width=1)
            return
        if kind == "snow":
            for x, y0, sp, ln in P[:40]:
                y = ((y0 + t * (0.05 + sp * 0.05)) % 1.0) * (H + 10) - 5
                xx = x * W + math.sin(t * 0.7 + ln * 9) * W * 0.02
                r = 0.8 + ln * 1.6
                d.ellipse([xx - r, y - r, xx + r, y + r], fill=(255, 255, 255, 190))
            return
        if not day:
            for x, y0, sp, ln in P[:26]:
                if 0.2 < x < 0.8 and y0 * 0.55 > 0.1:                    # keep the middle clear: the icon and the temperature
                    continue
                tw = 0.5 + 0.5 * math.sin(t * (0.25 + sp * 0.4) + ln * 20)
                r = 0.6 + ln * 0.9
                d.ellipse([x * W - r, y0 * H * 0.55 - r, x * W + r, y0 * H * 0.55 + r], fill=(255, 255, 255, int(70 + 150 * tw)))
            return
    if name != "clock":
        return
    for i in range(9):                                                   # bokeh: slow lights drifting up
        x, y0, sp, ln = P[i]
        s = state["sp"][i % 3]
        y = (1.1 - ((y0 + t * (0.006 + sp * 0.01)) % 1.2)) * H
        xx = x * W + math.sin(t * 0.1 + ln * 7) * W * 0.04
        if 0 <= xx - s.r and xx + s.r < W and 0 <= y - s.r and y + s.r < H:
            img.alpha_composite(s.im, (int(xx - s.r), int(y - s.r)))


def _read_secs(words, base=3.0, per_word=0.16, lo=5.5, hi=11.0):
    """How long a screen of text needs: a fixed glance plus a little per word (it is quickly skimmed, not studied)."""
    return max(lo, min(hi, base + per_word * words)) * PACE


def plan(dat):
    """[(name, seconds, drawer)]: the day, the mountains, the news. Each scene gets the time its content needs, so the whole
    show is only as long as it has to be; scenes with nothing to show are left out."""
    parts = [("clock", 5.0 * PACE, scene_clock)]
    if dat.get("weather"):
        parts += [("weather", 7.0 * PACE, scene_weather), ("hours", 8.0 * PACE, scene_hours), ("outlook", 8.0 * PACE, scene_outlook)]
    if dat.get("mountains"):                                       # the weekend in the mountains, always (Saturday, then Sunday)
        if dat.get("mountain_ai"):                                 # the short version first, then Saturday, then Sunday
            parts.append(("weekend_sum", _read_secs(len(dat["mountain_ai"].split()) * 0.9 + 6), scene_weekend_summary))
        parts += [("weekend0", 9.0 * PACE, lambda W, H, n, d: scene_weekend(W, H, n, d, 0)),
                  ("weekend1", 9.0 * PACE, lambda W, H, n, d: scene_weekend(W, H, n, d, 1))]
    if dat.get("science"):                                         # a few research highlights between the mountains and the news
        parts.append(("science", _read_secs(sum(len(i["line"].split()) for i in dat["science"]) * 0.8 + 4, hi=13.0), scene_science))
    for k, st in enumerate(dat.get("news") or []):
        words = len(st["title"].split()) * 1.6 + min(len(st["text"].split()), 26) * 0.8      # the headline is read, the summary skimmed
        parts.append((f"news{k}", _read_secs(words), (lambda W, H, n, d, k=k: scene_news(W, H, n, d, k))))
    return parts


def _palette(name, dat, n):
    if name == "clock":
        return _daypart(n)[1]
    if name == "weather":
        return _weather_palette(dat, n)
    if name == "hours":
        return HOURS_PAL
    if name == "outlook":
        return OUTLOOK_PAL
    if name.startswith("weekend"):
        return WEEKEND_PAL
    if name == "science":
        return SCI_PAL
    return NEWS_PAL[dat["news"][int(name[4:])]["tag"]][0]


class Show:
    def __init__(self, lang=None):
        self.lang = lang or DEFAULT_LANG
        set_lang(self.lang)
        self.dat = data(lang=self.lang)                            # first run: waits for the network (a few seconds)
        self.t0 = None                                             # when the current loop began
        self._busy = False                                         # a next scene is being prepared in the background
        self.looped = False                                        # no dissolve "in" from the last scene on the very first frame
        self.cache = {}
        self.fields = {}
        self.state = {}
        self._replan(self.dat)

    def _replan(self, dat):
        self.dat = dat
        self.plan = plan(dat)
        self.loop_len = sum(sec for _, sec, _ in self.plan)

    def _scene_at(self, tt):
        acc = 0.0
        for i, (name, sec, fn) in enumerate(self.plan):
            if tt < acc + sec:
                return i, tt - acc, sec
            acc += sec
        return len(self.plan) - 1, 0.0, self.plan[-1][1]

    def _type_layer(self, i, W, H):
        """The crisp layer for a scene, drawn at 2x and shrunk; redrawn when the minute or the data changes."""
        name = self.plan[i][0]
        n = now()
        key = (name, id(self.dat), n.minute if name == "clock" else 0)
        hit = self.cache.get(name)
        if hit and hit[0] == key:
            return hit[1]
        set_lang(self.lang)                                        # (this may run in the background thread that prepares the next scene)
        big = self.plan[i][2](W * SS, H * SS, n, self.dat)
        layer = big.resize((W, H), Image.LANCZOS)
        self.cache[name] = (key, layer)
        return layer

    def _prefetch(self, i, W, H):
        """Draw a scene's text layer ahead of time, in the background, so the dissolve into it never waits (it costs the Pi
        a quarter of a second to draw)."""
        name = self.plan[i][0]
        hit = self.cache.get(name)
        key = (name, id(self.dat), now().minute if name == "clock" else 0)
        if self._busy or (hit and hit[0] == key):
            return
        self._busy = True

        def run():
            try:
                self._type_layer(i, W, H)
            except Exception:
                pass
            finally:
                self._busy = False
        threading.Thread(target=run, daemon=True).start()

    def _scene_frame(self, i, t, W, H):
        name = self.plan[i][0]
        f = self.fields.setdefault(name, Field(W, H, seed=hash(name) % 97))
        base = f.render(t, _palette(name, self.dat, now())).convert("RGBA")
        _overlay(name.rstrip("0123456789") if name.startswith("news") else name, t, base, W, H, self.dat, self.state)
        base.alpha_composite(self._type_layer(i, W, H))
        return base

    def frame(self, t):
        set_lang(self.lang)
        W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
        if self.t0 is None:
            self.t0 = t                                            # the show starts when it is first asked for a frame
        tt = t - self.t0
        if tt < 0:                                                 # time went backwards (a restart of the clock): begin again
            self.t0, tt = t, 0.0
        if tt >= self.loop_len:                                    # a new loop: refresh in the background and plan it afresh
            self._replan(data(wait=False, lang=self.lang))
            self.cache = {}
            self.looped = True
            self.t0, tt = t, 0.0
        i, into, sec = self._scene_at(tt)
        n, half = len(self.plan), FADE / 2.0
        img = self._scene_frame(i, t, W, H)
        if n > 1 and into > 1.0:
            self._prefetch((i + 1) % n, W, H)
        # ONE dissolve per boundary, centred on it: the last half-fade of a scene into the next, and (continuing from
        # exactly that picture) the first half-fade of the next scene
        if n > 1:
            if into < half and (i > 0 or self.looped):
                img = Image.blend(self._scene_frame((i - 1) % n, t, W, H), img, 0.5 + into / FADE)
            elif into > sec - half:
                img = Image.blend(img, self._scene_frame((i + 1) % n, t, W, H), (into - (sec - half)) / FADE)
        out = img.convert("RGB")
        d = ImageDraw.Draw(out)                                    # a thin glowing line along the bottom: where the show is
        d.rectangle([0, H - 2, int(W * tt / self.loop_len), H - 1], fill=(255, 205, 120))
        return out


_shows = {}


def _frame_for(lang, t):
    if lang not in _shows:
        _shows[lang] = Show(lang)
    return _shows[lang].frame(t)


def frame(t):
    """The show in the default language (German)."""
    return _frame_for(DEFAULT_LANG, t)


def frame_en(t):
    """The show in English."""
    return _frame_for("en", t)


def _sample():
    return {"when": time.time(), "weather": {
        "now": {"temp": 14.0, "feels": 12.0, "humidity": 71, "rain": 0.0, "code": 2, "wind": 9.0, "day": True, "time": ""},
        "hours": [{"time": f"{(10 + i) % 24:02d}:00", "temp": 10 + 4 * math.sin(i / 4.0), "pop": [0, 0, 10, 40, 70, 20, 0, 0][i % 8],
                   "code": [2, 3, 61, 63, 3, 1, 0, 0][i % 8]} for i in range(24)],
        "days": [{"date": (datetime.date.today() + datetime.timedelta(days=i)).isoformat(), "code": [2, 61, 3, 0][i],
                  "max": 15 - i, "min": 7 - i, "pop": [20, 70, 40, 5][i], "sunrise": "07:12", "sunset": "17:05", "uv": 2.0}
                 for i in range(4)]},
        "news": [{"tag": "CH", "title": "Swiss parliament debates the new energy law in a lively session",
                  "text": "Lawmakers in Bern argued for hours over how fast the country should expand solar and wind power."},
                 {"tag": "WORLD", "title": "Leaders gather for climate talks as a new report warns of faster warming",
                  "text": "Delegates are expected to agree on a package of measures by the end of the week."}]}


def thumb(lang=None):
    """A still for the app: sample data, no network."""
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    dat = _sample()
    dat["lang"] = lang or DEFAULT_LANG
    set_lang(dat["lang"])
    n = now()
    base = Field(W, H).render(0.0, _weather_palette(dat, n)).convert("RGBA")
    base.alpha_composite(scene_weather(W * SS, H * SS, n, dat).resize((W, H), Image.LANCZOS))
    return base.convert("RGB")


def thumb_en():
    return thumb("en")


def render_scene(name, dat=None, t=0.0, k=0):
    """One finished scene as an RGB image (for previews and tests)."""
    dat = dat or data()
    set_lang(dat.get("lang") or DEFAULT_LANG)
    W, H = config.TOTAL_WIDTH, config.TOTAL_HEIGHT
    n = now()
    fn = {"clock": scene_clock, "weather": scene_weather, "hours": scene_hours, "outlook": scene_outlook, "science": scene_science}.get(name)
    if name == "weekend_sum":
        layer = scene_weekend_summary(W * SS, H * SS, n, dat).resize((W, H), Image.LANCZOS)
        pal = _palette(name, dat, n)
    elif name.startswith("weekend"):
        k = int(name[7:] or 0)
        layer = scene_weekend(W * SS, H * SS, n, dat, k).resize((W, H), Image.LANCZOS)
        pal = _palette(name, dat, n)
    else:
        layer = (fn(W * SS, H * SS, n, dat) if fn else scene_news(W * SS, H * SS, n, dat, k)).resize((W, H), Image.LANCZOS)
        pal = _palette(name if fn else f"news{k}", dat, n)
    base = Field(W, H).render(t, pal).convert("RGBA")
    _overlay(name if fn else "news", t, base, W, H, dat, {})
    base.alpha_composite(layer)
    return base.convert("RGB")


# ------------------------------------------------------------ the paper slip ---

def _slip_icon(code, day, size):
    """A flat black weather picture for paper (a mask: opaque where the icon is)."""
    S = size * 4
    layer = _layer(S, S)
    icon(layer, code, day, S / 2, S / 2, S * 0.36, plain=True)
    return layer.getchannel("A").resize((size, size), Image.LANCZOS)


def slip_image(dat=None, width=384, ai=True):
    """The Fortuna Brief on paper, short: a black masthead, a short intro, the weather today in one block with sunrise and sunset,
    and the six headlines. Text is drawn in pure black and white (no anti-aliasing), the crispest the printer can do."""
    dat = dat or data()
    set_lang(dat.get("lang") or DEFAULT_LANG)
    n = now()
    words = enrich(dat) if ai else None                           # the AI's intro (or None)
    PAD = 16
    img = Image.new("L", (width, 2400), 255)
    d = ImageDraw.Draw(img)
    d.fontmode = "1"                                              # hinted, un-smoothed glyphs: sharp on a thermal head
    cx = width // 2
    y = 0

    def paste_icon(code, day, size, x, yy):
        img.paste(Image.new("L", (size, size), 0), (int(x), int(yy)), _slip_icon(code, day, size))

    def text(xy, s_, f, fill=0, anchor="la"):
        d.text(xy, _loc(s_), font=f, fill=fill, anchor=anchor)

    def section(title):
        nonlocal y
        title = _loc(title)
        y += 8
        f = font(16)
        w = d.textlength(title, font=f)
        text((PAD, y), title, f)
        d.rectangle([PAD + w + 10, y + 8, width - PAD, y + 9], fill=0)
        y += 26

    # -- the masthead
    d.rectangle([0, 0, width, 70], fill=0)
    text((cx, 25), "FORTUNA BRIEF", fit("bold", 34, "FORTUNA BRIEF", width - 2 * PAD, floor=18), 255, "mm")
    text((cx, 54), _long_date(n), font(17), 255, "mm")
    y = 80
    text((cx, y), f"{n.strftime('%H:%M')}   ·   {PLACE}", font(15, False), 0, "ma")
    y += 24
    if words and words["intro"]:                                  # the day in two sentences
        f = font(16, False)
        lines = wrap(d, words["intro"], f, width - 2 * PAD - 14, 4)
        d.rectangle([PAD, y, PAD + 3, y + 21 * len(lines) - 3], fill=0)
        for ln in lines:
            text((PAD + 14, y), ln, f)
            y += 21
        y += 4

    # -- the weather today, in one compact block, with sunrise and sunset
    w = dat.get("weather")
    if w:
        c = w["now"]
        section("WEATHER NOW")
        text((PAD, y - 2), f"{round(c['temp'])}°", font(46), 0, "la")
        cond = WMO.get(c["code"], "")
        text((PAD + 92, y + 2), cond, fit("bold", 20, cond, width - PAD - 92 - 56, floor=13), 0)
        text((PAD + 92, y + 28), _x(f"feels {round(c['feels'])}° · wind {round(c['wind'])} km/h · {round(c['humidity'])}%",
                                    f"gefühlt {round(c['feels'])}° · Wind {round(c['wind'])} km/h · {round(c['humidity'])}%"), font(13, False), 0)
        paste_icon(c["code"], c["day"], 44, width - PAD - 44, y)
        y += 56
        d0 = w["days"][0]
        wet = max(w["hours"][:24], key=lambda h: h["pop"])
        line = _x(f"Sunrise {d0['sunrise']}  ·  Sunset {d0['sunset']}", f"Sonnenaufgang {d0['sunrise']}  ·  Sonnenuntergang {d0['sunset']}")
        text((cx, y), line, fit("regular", 14, line, width - 2 * PAD, floor=10), 0, "ma")
        y += 20
        if wet["pop"] >= 30:                                       # only when rain is likely
            rain = _x(f"Rain {wet['pop']}% around {wet['time'][:2]}h", f"Regen {wet['pop']}% gegen {wet['time'][:2]} Uhr")
            text((cx, y), rain, font(14, False), 0, "ma")
            y += 20
        y += 4
    else:
        text((PAD, y), "Weather unavailable (offline).", font(15, False), 0)
        y += 26

    # -- the headlines
    section("TOP STORIES")
    if dat.get("news"):
        for i, st in enumerate(dat["news"]):
            d.rectangle([PAD, y + 1, PAD + 24, y + 25], fill=0)
            text((PAD + 12, y + 13), str(i + 1), font(17), 255, "mm")
            tf = font(17)
            lines = wrap(d, st["title"], tf, width - PAD - (PAD + 36), 3)
            yy = y
            for ln in lines:
                text((PAD + 36, yy), ln, tf, 0)
                yy += 21
            y = max(yy, y + 28) + 7
    else:
        text((PAD, y), "News unavailable (offline).", font(15, False), 0)
        y += 26

    # -- research highlights: three single lines
    if dat.get("science"):
        section("RESEARCH")
        sf = font(14, False)
        for it in dat["science"][:3]:
            lines = wrap(d, f"{it['topic']}: {it['line']}", sf, width - PAD - (PAD + 16), 3)
            d.rectangle([PAD + 2, y + 6, PAD + 7, y + 11], fill=0)
            for ln in lines:
                text((PAD + 16, y), ln, sf, 0)
                y += 18
            y += 4

    # -- the foot
    d.rectangle([0, y, width, y + 2], fill=0)
    y += 10
    text((cx, y), "Have a lovely day.", font(16), 0, "ma")
    text((cx, y + 22), _x("Open-Meteo  ·  The Local  ·  BBC  ·  ScienceDaily", "Open-Meteo  ·  NZZ  ·  ZDF heute  ·  ScienceDaily") + ("  ·  AI intro" if words else ""), font(11, False), 0, "ma")
    return img.crop((0, 0, width, y + 40))


ENRICH_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["intro"], "properties": {"intro": {"type": "string"}}}
_enrich_cache = {"key": None, "val": None}


def _facts(dat):
    w = dat.get("weather")
    out = {"place": PLACE, "date": now().strftime("%A %d %B %Y"), "time": now().strftime("%H:%M")}
    if w:
        c = w["now"]
        out["now"] = f"{round(c['temp'])}C, {WMO.get(c['code'], '')}, wind {round(c['wind'])} km/h"
        out["days"] = [f"{'Today' if i == 0 else _fmt_day(x['date'])}: {WMO.get(x['code'], '')}, {round(x['min'])} to {round(x['max'])}C, rain {x['pop']}%"
                       for i, x in enumerate(w["days"][:4])]
        out["sun"] = f"sunrise {w['days'][0]['sunrise']}, sunset {w['days'][0]['sunset']}"
    out["headlines"] = [s_["title"] for s_ in (dat.get("news") or [])[:4]]
    return out


def enrich(dat):
    set_lang(dat.get("lang") or DEFAULT_LANG)
    """The AI's words for the paper slip: a short intro for the day and a plain summary
    of every story. Only the facts above are given to it; None when the AI is unavailable (the slip then prints without)."""
    key = (dat.get("when"), dat.get("lang"))
    if _enrich_cache["key"] == key and _enrich_cache["val"] is not None:
        return _enrich_cache["val"]
    try:
        import ai_client
        facts = _facts(dat)
        system = ("You write the printed daily brief for House Fortuna, a flatshare at Fortunagasse 24 in Zurich. It is read on a "
                  "narrow paper slip over breakfast. Plain, warm, concrete, no emojis, no hype, British spelling. Use ONLY the facts "
                  "you are given; never add numbers, places or events that are not there. Write 'intro' = two short sentences that "
                  "greet the person for the time of day given in 'time' (good morning before noon, good afternoon until 18:00, good evening after) "
                  "and say what to expect today in Zurich (weather, anything worth knowing), at most 140 characters in all."
                  + (" Write in German (Swiss spelling: ss, never the letter ß); greet with Guten Morgen before noon, Guten Tag until 18:00, "
                     "Guten Abend after." if dat.get("lang") == "de" else ""))
        j, _i, _o = ai_client.ask(system, json.dumps(facts, ensure_ascii=False), max_tokens=300, effort="low",
                                  schema=ENRICH_SCHEMA, timeout=40)
        val = {"intro": str(j.get("intro", "")).strip()[:170]}
        _enrich_cache.update(key=key, val=val)
        return val
    except Exception as e:
        print(f"[brief] the AI is unavailable for the slip: {e}", flush=True)
        return None


DEFAULT_PRINT_AT = "07:30"


def due(st, n=None):
    """Is it time to print today's brief? On by default, once a day, from the set time for four hours (a wall
    that boots at night does not print yesterday's morning paper)."""
    if not st.get("brief_print", True):
        return False
    n = n or now()
    if st.get("brief_printed") == n.date().isoformat():
        return False
    try:
        h, m = (int(v) for v in str(st.get("brief_print_at") or DEFAULT_PRINT_AT).split(":")[:2])
    except ValueError:
        h, m = 7, 30
    start = n.replace(hour=h, minute=m, second=0, microsecond=0)
    return start <= n < start + datetime.timedelta(hours=4)


def show_seconds(dat=None, lang=None):
    """How long the show runs for this data (the sum of its scenes)."""
    return sum(sec for _, sec, _ in plan(dat if dat is not None else data(wait=False, lang=lang)))


_last_print = [0.0]
REPRINT_GAP = 600.0                                                # replaying the show within 10 minutes does not print again




def print_slip(lang=None):
    """Print the brief on the receipt printer (raises when the printer is unreachable)."""
    import print_out
    print_out.send(slip_image(data(lang=lang or DEFAULT_LANG)))
    _last_print[0] = time.time()


def print_once(gap=REPRINT_GAP, lang=None):
    """The slip that goes out as the show starts: skipped when one was printed in the last few minutes. -> True if printed."""
    if time.time() - _last_print[0] < gap:
        print("[brief] a slip was printed a moment ago: not printing again", flush=True)
        return False
    print_slip(lang)
    print("[brief] slip printed (the show's start)", flush=True)
    return True
