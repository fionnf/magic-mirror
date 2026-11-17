# The online site

The wall's phone control app is also served from a small GitHub Pages site, so it can be opened away from home (see [remote-access.md](remote-access.md)).
`tools/build_gallery.py` builds it into `_site/`; the workflow `.github/workflows/gallery.yml` deploys it when `site/**` or `panel_setup/web/index.html` change.

What is on the site (about 140 KB, and it does not grow):

- `index.html`: the wall's control app (it finds the wall through the address the wall announces in `wall/wall.json`);
- `p/`: the photo page (`<site>/p/#<the day's Drive folder>`, see [mirror.md](mirror.md));
- `gallery.js` (the app's shader library) and the icons.

## The daily art is not on the site

Until 2026-11-17 every day's piece was published too: a feed, one page per piece, RSS, a `window/` page, `editions.json`, and a scheduled GitHub Actions workflow that made the piece in the cloud.
All of that was removed to keep the hosting small (the pieces, their stills and the git history were growing every day). The wall still composes its own piece around 05:00 (an offline one if there is no
internet) and keeps it in `assets/daily/` on the Pi; nothing is published. The old pieces are still in the git history (commits before the removal, folder `gallery/`).

## Preview and your own fork

```bash
python3 tools/build_gallery.py
python3 -m http.server -d _site 8000
```

In a fork, set Settings, Pages, source **GitHub Actions**, and optionally the repository variable `GALLERY_API_KEY` (a browser key for the Drive API, for the photo page).
The wall's address announcements need `GALLERY_TOKEN` or a deploy key (README, "Remote access"): `display/publish.py` (`announce_wall`).
