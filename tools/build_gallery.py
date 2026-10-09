#!/usr/bin/env python3
"""Build the public Fortuna gallery (GitHub Pages) from gallery/ (published editions).

    python3 tools/build_gallery.py               # -> _site/
    python3 tools/build_gallery.py --from assets/daily --out /tmp/site    # preview local editions

Pages: index.html (the feed, newest first), e/<date>/ (one page per edition), feed.xml (RSS, so
people can follow), plus the editions' files. Every post runs its GLSL live in the browser (site/gallery.js).
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


def page(title, body, prefix, desc=TAGLINE, image=None, canonical=""):
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
<script src="{prefix}gallery.js" defer></script></body></html>"""


def header(prefix):
    return (f'<header class="site"><h1><a href="{prefix}art/">{TITLE}</a></h1><p>{e(TAGLINE)}</p>'
            f'<div class="follow"><a href="{prefix}feed.xml">Follow by RSS</a>'
            f'<a href="https://feedly.com/i/subscription/feed/{SITE_URL}feed.xml">Follow on Feedly</a>'
            f'<a href="{prefix}">Control the wall</a></div></header>')


def post_html(m, prefix, full=False):
    link = f'{prefix}e/{m["date"]}/'
    out = [f'<article class="post">', piece(m, prefix),
           f'<p class="when">{nice(m["date"])}{"" if m.get("final") else " · on the wall now"}</p>',
           "<h2>" + (e(m["name"]) if full else f'<a href="{link}">{e(m["name"])}</a>') + "</h2>",
           f'<p class="caption">{e(caption(m))}</p>']
    if m.get("listening"):
        out.append(f'<p class="listens">{e(tidy(m["listening"]))}</p>')
    out.append('<div class="actions"><button class="btn" data-listen>Let it hear your room</button>'
               + ("" if full else f'<a class="btn" href="{link}">About this piece</a>') + '</div>')
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
    out.append("</article>")
    return "\n".join(out)


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
    for fn in ("style.css", "gallery.js"):
        shutil.copy(os.path.join(ROOT, "site", fn), a.out)
    for m in eds:
        for ext in ("frag", "png", "final.png"):
            p = os.path.join(a.src, f"{m['date']}.{ext}")
            if os.path.exists(p):
                shutil.copy(p, os.path.join(a.out, "gallery"))
        os.makedirs(os.path.join(a.out, "e", m["date"]))
        with open(os.path.join(a.out, "e", m["date"], "index.html"), "w") as fh:
            fh.write(page(f"{m['name']} · {TITLE}", header("../../") + post_html(m, "../../", full=True),
                          "../../", caption(m), still(m), f"e/{m['date']}/"))
    feed = "".join(post_html(m, "../") for m in eds) or '<p class="caption">The first piece is on its way.</p>'
    os.makedirs(os.path.join(a.out, "art"))
    with open(os.path.join(a.out, "art", "index.html"), "w") as fh:
        fh.write(page(TITLE, header("../") + feed, "../", image=still(eds[0]) if eds else None, canonical="art/"))
    # the home page is the wall's control app (it finds the wall through its announced address)
    shutil.copy(os.path.join(ROOT, "panel_setup", "web", "index.html"), os.path.join(a.out, "index.html"))
    with open(os.path.join(a.out, "feed.xml"), "w") as fh:
        fh.write(rss(eds))
    with open(os.path.join(a.out, ".nojekyll"), "w"):
        pass
    print(f"gallery: {len(eds)} editions -> {a.out}")


if __name__ == "__main__":
    sys.exit(main())
