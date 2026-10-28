# Live cam

The wall shows a live webcam reduced to the 192x256 LED grid (`display/livecam.py`, mode `livecam`).

## Only use streams you may use

You must only configure streams you are permitted to use. Many YouTube and aggregator streams are **not**
licensed for rebroadcast on other displays, and the module does not scrape sites, discover URLs or use tools
such as yt-dlp: you supply the URL and you are responsible for being entitled to it. No specific stream is
claimed to be permitted by this project.

Kinds of sources that are usually fine (check the actual terms of each one):

- your own IP cameras (RTSP or MJPEG on your network)
- municipal or transport webcams published under an open licence
- commercial webcam networks such as EarthCam, only as their own terms allow
- local video files and still-image URLs you have the rights to

## Configure

Copy `panel_setup/livecams.example.json` to `panel_setup/livecams.json` (git-ignored) and edit it. Each cam has
`name`, `url`, and optionally `x`, `y` (focus 0..1), `zoom`, `pan`, `label`, `rotation`, `flip`, `led`, `poll`.
`WALL_LIVECAMS_JSON` may hold the same JSON (text or a file path); its entries win by name.
The cam named `test` is a synthetic crossing needing no network.

| Setting | Meaning |
| --- | --- |
| `LIVECAM_MINUTES` | minutes per cam when cycling (default 10) |
| `LIVECAM_NAME` | stay on this cam |
| `LIVECAM_LED=1` | dithered LED mode for all cams |

The stream is read on a side thread with reconnect and backoff; `frame(t)` never waits. When no cam is
configured or the stream is down the wall shows a calm NO SIGNAL card with a slow scanline.
