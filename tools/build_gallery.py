#!/usr/bin/env python3
"""Build the public Fortuna gallery (GitHub Pages) from gallery/ (published editions).

    python3 tools/build_gallery.py               # -> _site/
    python3 tools/build_gallery.py --from assets/daily --out /tmp/site    # preview local editions

Pages: index.html (the wall's control app), art/ (the feed, newest first, under a calendar of the year
in colour), e/<date>/ (one page per edition, with a studio to play the piece by hand and make postcards),
window/ (any screen as a small Fortuna wall), feed.xml (RSS) and editions.json, plus the editions' files.
Every piece runs its GLSL live in the browser (site/gallery.js).
"""
import argparse
import datetime
import email.utils
import html
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_URL = os.environ.get("GALLERY_URL", "https://fionnf.github.io/magic-mirror/").rstrip("/") + "/"
TITLE = "Fortuna"
CREDIT = "Dewa and Fionn"
TAGLINE = ("One piece of light a day from a living room in Zürich, made by Dewa and Fionn for a wall of "
           "LED panels. Each one is shaped by what the room listens to until midnight.")
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" '
         'href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?'
         'family=Instrument+Sans:wght@400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">')
e = html.escape


def load(folder):
    eds = []
    for fn in sorted(os.listdir(folder), reverse=True):
        if fn.endswith(".json") and fn.count(".") == 1:
            with open(os.path.join(folder, fn)) as fh:
                m = json.load(fh)
            m["date"] = fn[:-5]
            if os.path.exists(os.path.join(folder, m["date"] + ".frag")):
                eds.append(m)
    return eds


def nice(d):
    return datetime.date.fromisoformat(d).strftime("%A %-d %B %Y")


def still(m):
    return m["date"] + (".final.png" if m.get("final") else ".png")


def tidy(t):
    """End on a whole sentence or clause (older editions were cut at a fixed length)."""
    t = (t or "").strip()
    if t and t[-1] not in ".!?":
        cut = max(t.rfind(". "), t.rfind(", "))
        t = (t[:cut] if cut > 40 else t).rstrip(",") + "."
    return t


def caption(m):
    return (m.get("post") or {}).get("caption") or m.get("description", "")


def piece(m, prefix):
    w, h = m.get("size") or [192, 192]
    pal = m.get("palette") or ["#000000", "#444444", "#ffffff"]
    alt = (m.get("post") or {}).get("alt") or m.get("name", "")
    return (f'<div class="piece" style="aspect-ratio:{w}/{h};--pitch:calc(100% / {w});--glow:{e(pal[1])}">'
            f'<img src="{prefix}gallery/{still(m)}" alt="{e(alt)}" loading="lazy">'
            f'<canvas width="{w}" height="{h}" data-frag="{prefix}gallery/{m["date"]}.frag" '
            f'data-palette=\'{json.dumps(pal)}\' data-day=\'{json.dumps(m.get("hours", []))}\' '
            f'data-cols="{w // 64}" data-rows="{h // 64}" aria-hidden="true"></canvas></div>')


def page(title, body, prefix, desc=TAGLINE, image=None, canonical="", scripts=()):
    og = f'<meta property="og:image" content="{SITE_URL}gallery/{image}">' if image else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">{og}
<link rel="canonical" href="{SITE_URL}{canonical}">
<link rel="alternate" type="application/rss+xml" title="{TITLE}" href="{SITE_URL}feed.xml">
<meta name="theme-color" content="#121014">{FONTS}<link rel="stylesheet" href="{prefix}style.css"></head>
<body><div class="wrap">{body}
<footer>Made by {CREDIT} at House Fortuna. Every piece here is the same program that runs on the
wall. <a href="{prefix}feed.xml">Follow by RSS</a>.</footer></div>
<script src="{prefix}gallery.js" defer></script>{"".join(f'<script src="{prefix}{x}" defer></script>' for x in scripts)}</body></html>"""


def header(prefix):
    return (f'<header class="site"><h1><a href="{prefix}art/">{TITLE}</a></h1><p>{e(TAGLINE)}</p>'
            f'<div class="follow"><a href="{prefix}feed.xml">Follow by RSS</a>'
            f'<a href="https://feedly.com/i/subscription/feed/{SITE_URL}feed.xml">Follow on Feedly</a>'
            f'<a href="{prefix}window/">Open as a window</a><a href="{prefix}">Control the wall</a></div></header>')


def post_html(m, prefix, full=False):
    link = f'{prefix}e/{m["date"]}/'
    out = [f'<article class="post">', piece(m, prefix),
           f'<p class="when">{nice(m["date"])}{"" if m.get("final") else " · on the wall now"}</p>',
           "<h2>" + (e(m["name"]) if full else f'<a href="{link}">{e(m["name"])}</a>') + "</h2>",
           f'<p class="caption">{e(caption(m))}</p>']
    if m.get("listening"):
        out.append(f'<p class="listens">{e(tidy(m["listening"]))}</p>')
    out.append('<div class="actions"><button class="btn" data-listen>Let it hear your room</button>'
               + ("" if full else f'<a class="btn" href="{link}">About this piece</a>')
               + f'<a class="btn" href="{prefix}window/?d={m["date"]}">Open as a window</a></div>')
    if full:
        pal = m.get("palette") or []
        facts = [("Date", nice(m["date"]))] + ([("Statement", e(m.get("description", "")))]
                                               if caption(m) != m.get("description") else []) + [
                 ("Palette", '<span class="swatches">' + "".join(f'<i style="background:{e(c)}" title="{e(c)}"></i>' for c in pal) + "</span>"),
                 ("Medium", f'GLSL shader on a {e(str((m.get("size") or [192,192])[0]))} × {e(str((m.get("size") or [192,192])[1]))} pixel LED wall'),
                 ("By", CREDIT),
                 ("Source", f'<a href="{prefix}gallery/{m["date"]}.frag">{m["date"]}.frag</a> · sha256 {e(m.get("source_sha256", "")[:12])}')]
        out.append('<dl class="facts">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts) + "</dl>")
        hours = m.get("hours")
        if hours:
            top = max(hours) or 1
            out.append('<p class="listens" style="margin-bottom:4px">What the room heard, hour by hour</p>'
                       '<div class="day">' + "".join(f'<i style="height:{max(2, v / top * 100):.0f}%"></i>' for v in hours)
                       + '</div><div class="day-axis"><span>midnight</span><span>noon</span><span>midnight</span></div>')
        cur = m.get("curator") or {}
        if cur.get("verdict"):
            out.append(f'<p class="listens" style="margin:26px 0 6px">The curator, before it was hung</p>'
                       f'<p class="curator">{e(cur["verdict"])}</p>')
        out.append(studio(m))
    out.append("</article>")
    return "\n".join(out)


KNOBS = [("iBass", "Bass", 1, .01), ("iEnergy", "Energy", 1, .01), ("iTreble", "Treble", 1, .01),
         ("iBreath", "Breath", 1, .01), ("iTension", "Tension", 1, .01), ("iKey", "Key of the music", 1, .01),
         ("iSong", "Song", 24, 1)]


def studio(m):
    """Play the piece by hand: everything the wall hears or knows, as controls (wired by site/studio.js)."""
    pal = m.get("palette") or ["#000000", "#444444", "#ffffff"]
    meta = json.dumps({"name": m["name"], "date": m["date"], "when": nice(m["date"])})
    knob = lambda u, label, hi, step: (f'<label class="knob"><span>{label}<output></output></span>'
                                       f'<input type="range" data-u="{u}" min="0" max="{hi}" step="{step}" value="0"></label>')
    return (f'<details class="studio" id="studio" data-meta=\'{e(meta)}\'><summary><span>Play with it</span>'
            '<small>Be the room: the music, the hour, the whole day</small></summary>'
            '<p class="listens">Every control is something the wall hears or knows. Touch one and it stops listening '
            'to the room and listens to you. Nothing here changes the wall.</p>'
            '<div class="speeds" role="group" aria-label="Time">'
            '<button class="btn" data-speed="still">Hold still</button><button class="btn" data-speed="live">As it is</button>'
            '<button class="btn" data-speed="fast">Hurry</button><button class="btn" data-speed="day">A day in a minute</button></div>'
            '<div class="knobs">' + "".join(knob(*k) for k in KNOBS)
            + '<label class="knob"><span>Hour of the day<output data-hour></output></span>'
              '<input type="range" data-u="clock" min="0" max="23.99" step="0.05" value="12"></label></div>'
            '<p class="listens" style="margin:20px 0 6px">The day it remembers. Draw it: one bar for every hour, louder at the top</p>'
            '<div class="day draw" aria-label="Draw the day\'s listening">' + "<i></i>" * 24 + '</div>'
            '<div class="day-axis"><span>midnight</span><span>noon</span><span>midnight</span></div>'
            '<p class="listens" style="margin:20px 0 8px">Its colours</p><div class="paints">'
            + "".join(f'<input type="color" data-c="{i}" value="{e(c)}" aria-label="Colour {i + 1}">' for i, c in enumerate(pal[:3]))
            + '</div><div class="actions" style="margin-top:22px">'
            '<button class="btn" data-still>Postcard</button><button class="btn" data-record>Record 8 seconds</button>'
            '<button class="btn" data-link>Copy a link to your version</button><button class="btn" data-reset>Back to the room</button></div>'
            '<p class="said" role="status" aria-live="polite"></p></details>')


def year(eds, prefix):
    """The year in colour: one cell per day, each day painted with its piece's palette."""
    if not eds:
        return ""
    by = {m["date"]: m for m in eds}
    y = int(eds[0]["date"][:4])
    rows = []
    for mo in range(1, 13):
        cells = []
        for d in range(1, 32):
            try:
                day = datetime.date(y, mo, d)
            except ValueError:
                cells.append('<i class="none"></i>')
                continue
            m = by.get(day.isoformat())
            if m:
                pal = m.get("palette") or ["#000", "#444", "#fff"]
                cells.append(f'<a href="{prefix}e/{m["date"]}/" title="{e(m["name"])}, {day.strftime("%-d %B")}" '
                             f'style="background:linear-gradient(135deg,{pal[0]},{pal[1]} 55%,{pal[2]})"></a>')
            else:
                cells.append(f'<i title="{day.strftime("%-d %B")}"></i>')
        rows.append(f'<span>{datetime.date(y, mo, 1).strftime("%b")}</span>' + "".join(cells))
    return (f'<section class="year" aria-label="{y}, one colour a day"><p class="listens">{y}, one piece a day. '
            f'The calendar fills in as the wall makes them.</p><div class="cal">' + "".join(rows) + "</div></section>")


def index(eds):
    """editions.json: what the window (and the control app's welcome) need to draw any edition."""
    return json.dumps([{"date": m["date"], "name": m["name"], "caption": caption(m), "palette": m.get("palette"),
                        "hours": m.get("hours", []), "size": m.get("size") or [192, 192],
                        "frag": f"gallery/{m['date']}.frag", "still": f"gallery/{still(m)}"} for m in eds])


def rss(eds):
    items = []
    for m in eds[:30]:
        url = f"{SITE_URL}e/{m['date']}/"
        img = f"{SITE_URL}gallery/{still(m)}"
        when = datetime.datetime.fromisoformat(m["date"] + "T07:00:00+01:00")
        body = f'<p><img src="{img}" alt="{e((m.get("post") or {}).get("alt", m["name"]))}"></p><p>{e(caption(m))}</p>'
        items.append(f"<item><title>{e(m['name'])}</title><link>{url}</link><guid isPermaLink=\"true\">{url}</guid>"
                     f"<pubDate>{email.utils.format_datetime(when)}</pubDate>"
                     f"<description>{e(body)}</description>"
                     f"<enclosure url=\"{img}\" type=\"image/png\" length=\"0\"/></item>")
    return ('<?xml version="1.0" encoding="utf-8"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">'
            f"<channel><title>{TITLE}</title><link>{SITE_URL}</link><description>{e(TAGLINE)}</description>"
            f'<atom:link href="{SITE_URL}feed.xml" rel="self" type="application/rss+xml"/><language>en</language>'
            + "".join(items) + "</channel></rss>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", default=os.path.join(ROOT, "gallery"))
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args()
    eds = load(a.src) if os.path.isdir(a.src) else []
    shutil.rmtree(a.out, ignore_errors=True)
    os.makedirs(os.path.join(a.out, "gallery"))
    for fn in ("style.css", "gallery.js", "studio.js"):
        shutil.copy(os.path.join(ROOT, "site", fn), a.out)
    for m in eds:
        for ext in ("frag", "png", "final.png"):
            p = os.path.join(a.src, f"{m['date']}.{ext}")
            if os.path.exists(p):
                shutil.copy(p, os.path.join(a.out, "gallery"))
        os.makedirs(os.path.join(a.out, "e", m["date"]))
        with open(os.path.join(a.out, "e", m["date"], "index.html"), "w") as fh:
            fh.write(page(f"{m['name']} · {TITLE}", header("../../") + post_html(m, "../../", full=True),
                          "../../", caption(m), still(m), f"e/{m['date']}/", scripts=("studio.js",)))
    feed = "".join(post_html(m, "../") for m in eds) or '<p class="caption">The first piece is on its way.</p>'
    os.makedirs(os.path.join(a.out, "art"))
    with open(os.path.join(a.out, "art", "index.html"), "w") as fh:
        fh.write(page(TITLE, header("../") + year(eds, "../") + feed, "../", image=still(eds[0]) if eds else None, canonical="art/"))
    # the home page is the wall's control app (it finds the wall through its announced address)
    shutil.copy(os.path.join(ROOT, "panel_setup", "web", "index.html"), os.path.join(a.out, "index.html"))
    with open(os.path.join(a.out, "feed.xml"), "w") as fh:
        fh.write(rss(eds))
    with open(os.path.join(a.out, "editions.json"), "w") as fh:
        fh.write(index(eds))
    os.makedirs(os.path.join(a.out, "window"))
    shutil.copy(os.path.join(ROOT, "site", "window.html"), os.path.join(a.out, "window", "index.html"))
    with open(os.path.join(a.out, ".nojekyll"), "w"):
        pass
    print(f"gallery: {len(eds)} editions -> {a.out}")


if __name__ == "__main__":
    sys.exit(main())
