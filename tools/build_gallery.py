#!/usr/bin/env python3
"""Build the small public site (GitHub Pages): the wall's control app and the photo page.

    python3 tools/build_gallery.py               # -> _site/

index.html is the wall's control app (it finds the wall through its announced address, see docs/remote-access.md),
p/ is the photo page (<site>/p/#<the day's Drive folder>, see docs/mirror.md), plus the app's shader library
(gallery.js) and the icons. The daily art is NOT on the site any more (removed 2026-11-17 to keep the hosting small).
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    out = os.path.join(ROOT, "_site")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    for fn in ("gallery.js", "favicon.svg", "favicon.png", "apple-touch-icon.png"):
        shutil.copy(os.path.join(ROOT, "site", fn), out)
    shutil.copy(os.path.join(ROOT, "panel_setup", "web", "index.html"), os.path.join(out, "index.html"))
    os.makedirs(os.path.join(out, "p"))
    with open(os.path.join(ROOT, "site", "photos.html")) as fh:
        page_html = fh.read().replace("__DRIVE_API_KEY__", os.environ.get("GALLERY_API_KEY", "").strip())
    with open(os.path.join(out, "p", "index.html"), "w") as fh:
        fh.write(page_html)
    with open(os.path.join(out, ".nojekyll"), "w"):
        pass
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(out) for f in fs)
    print(f"site: {size // 1024} KB -> {out} (photo page {'with' if os.environ.get('GALLERY_API_KEY') else 'without'} a Drive key)")


if __name__ == "__main__":
    sys.exit(main())
