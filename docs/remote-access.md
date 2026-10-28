# Controlling the wall from outside your home network

Out of the box the control app is only for your home network. This page covers the optional
remote path: a password, a free Cloudflare tunnel, and the copy of the app hosted on GitHub Pages.
It is all optional; nothing else depends on it.

## Who needs a password

`panel_setup/wall_control.py` treats a request as "at home" when it comes from a private or
loopback IP address and carries no proxy headers (`_is_local`). Those requests need **no password**:
anybody on your Wi-Fi can drive the wall, and the guest page `/d` is open by design. Everything
else (requests through the tunnel) must log in.

Set a password in the wall's `.env`:

```
WALL_PASSWORD=choose-something-long
```

Without `WALL_PASSWORD` remote access is switched off ("Remote access is not set up yet"). Eight wrong
passwords in ten minutes lock the login for ten minutes. The login sets a 180-day cookie, or, from the
Pages app, returns a token. Changing the password logs every phone out.

## The tunnel

If the program `cloudflared` is installed on the Pi, `WALL_PASSWORD` is set and `WALL_TUNNEL` is not
`0`, the wall starts a Cloudflare "quick tunnel" (`cloudflared tunnel --url http://localhost:80`,
no Cloudflare account). It gets a random `https://<words>.trycloudflare.com` address that **changes
on every start**. `bootstrap_pi.sh` does not install `cloudflared`; install it yourself from
Cloudflare's downloads (arm64 build for a 64-bit Pi OS).

## The Pages copy of the app

Because the tunnel address changes, the wall announces it: it commits `wall/wall.json`
(`{"url": ..., "since": ...}`) to the gallery repo through `display/publish.py`, so it needs
`GALLERY_TOKEN` or a deploy key with write access (see [gallery.md](gallery.md)). The control app
that `tools/build_gallery.py` publishes as the site's `index.html` is the same file as
`panel_setup/web/index.html`. When it is opened on a host that is not a private IP, `.local`,
`localhost` or `trycloudflare.com`, it reads `wall/wall.json` from the GitHub API, asks for the
password, and talks to the wall through the tunnel. The wall allows that origin through CORS
(`WALL_APP_ORIGINS`, default `https://fionnf.github.io`).

To use this with your own fork, change:

| What | Where |
|---|---|
| repository the app reads `wall/wall.json` from | `panel_setup/web/index.html`, function `findWall()` (`api.github.com/repos/fionnf/magic-mirror/...`) |
| the gallery link shown on the login screens | `panel_setup/web/index.html`, `GALLERY` and two `<a href>` lines in the login gates |
| allowed web origin | `WALL_APP_ORIGINS=https://<you>.github.io` in `.env` |
| where the wall writes `wall/wall.json` | `GALLERY_REPO=<you>/magic-mirror` in `.env` |

`wall/wall.json` in this repo holds the author's last tunnel address; it is a public file and will
be overwritten by your wall.

## Without any of this

Use `http://<pi-ip>/` or `http://<hostname>.local/` on your home Wi-Fi. That is the default and needs
no accounts. Note that a request only counts as "at home" when its source address is private (or
loopback) and it carries no proxy headers; anything else is asked for the password.
