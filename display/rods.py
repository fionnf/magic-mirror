"""The living room's two Bluetooth LED rods (MELK-OA10): warm orange, following the wall only for the daily art.

    r = Rods(); r.feed(img)          # call every frame with the picture being shown; cheap

The top half of the wall sets rod 1's colour and the bottom half rod 2's, so a gradient on the wall
becomes a gradient across the room. Colours are eased (the rods never flash), sent ~4 times a second
and only when they changed. The Bluetooth side runs on its own thread and reconnects by itself, so
a missing rod never touches the wall. Needs bleak and an unblocked Bluetooth adapter; without them
it quietly does nothing.
"""
import asyncio
import colorsys
import json
import os
import threading
import time

import numpy as np

STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_setup", "rods_status.json")
FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "panel_setup", "rods.json")
ADDRESSES = ["BE:69:33:1C:4F:01", "BE:69:6A:12:CD:03"]      # living room rod 1, rod 2
ON = bytes([0x7e, 0x04, 0x04, 0x01, 0xff, 0xff, 0x00, 0xef])
GAIN = 0.8                  # the rods are close to the eye: not full power
ORANGE = np.array([255, 110, 0], np.float32)
EASE = 0.6                  # seconds for a colour to follow the wall


def _pack(r, g, b):
    return bytes([0x7e, 0x07, 0x05, 0x03, int(r), int(g), int(b), 0x10, 0xef])


def colours(img):
    """(top, bottom) RGB 0..255 of a picture: the lively average of each half, saturation lifted."""
    a = np.asarray(img, np.float32)
    h = a.shape[0] // 2
    out = []
    for part in (a[:h], a[h:]):
        small = part[::8, ::8].reshape(-1, 3)
        w = small.max(1) - small.min(1) + 0.15 * small.max(1) + 1.0      # favour colourful, bright pixels
        c = (small * w[:, None]).sum(0) / w.sum()
        hh, ss, vv = colorsys.rgb_to_hsv(*(np.clip(c, 0, 255) / 255))
        out.append(np.array(colorsys.hsv_to_rgb(hh, min(1.0, ss * 1.4 + 0.05), min(1.0, vv * 1.6)), np.float32) * 255)
    return out


class Rods:
    def __init__(self, addresses=ADDRESSES):
        self.addr = addresses
        self.target = [np.zeros(3, np.float32) for _ in addresses]
        self.cur = [np.zeros(3, np.float32) for _ in addresses]
        self.last = None
        self.level = 1.0
        self.follow = False                                  # True only while the daily art is on the wall
        self.status = ["off"] * len(addresses)
        self._fed = 0.0
        try:
            import bleak  # noqa: F401
        except Exception:
            return
        threading.Thread(target=self._run, daemon=True).start()

    def feed(self, img):
        now = time.monotonic()
        if now - self._fed < 0.1:
            return
        dt, self._fed = min(0.5, now - self._fed), now
        top, bot = self._choice(img)
        for i, c in enumerate((top, bot)[:len(self.addr)]):
            self.target[i] = c * GAIN * self.level
            self.cur[i] += (self.target[i] - self.cur[i]) * (1 - np.exp(-dt / EASE))

    def _choice(self, img):
        """Warm orange, except while the daily art is on the wall (self.follow): then they take its colours.
        panel_setup/rods.json (re-read every 2 s) can still switch them off: {"mode": "off"}"""
        now = time.monotonic()
        if now - getattr(self, "_cfg_t", -9) > 2.0:
            self._cfg_t = now
            try:
                with open(FILE) as fh:
                    self._cfg = json.load(fh)
            except Exception:
                self._cfg = {}
        cfg = getattr(self, "_cfg", {})
        mode = cfg.get("mode", "auto")
        self.level = max(0.05, min(1.0, float(cfg.get("level", 100)) / 100.0))
        if mode == "off":
            z = np.zeros(3, np.float32)
            return z, z
        if mode in ("solid", "breathe"):
            h = str(cfg.get("colour", "#ff6a00")).lstrip("#")
            try:
                c = np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
            except ValueError:
                c = ORANGE
            if mode == "breathe":
                c = c * (0.55 + 0.45 * np.sin(time.monotonic() * 2 * np.pi / 8.0))
            return c, c
        if mode == "follow" or (mode == "auto" and self.follow):
            return colours(img)
        return ORANGE, ORANGE

    def _publish(self):
        try:
            tmp = STATUS_FILE + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"status": self.status, "addr": self.addr}, fh)
            os.replace(tmp, STATUS_FILE)
        except Exception:
            pass

    def _run(self):
        asyncio.run(self._main())

    async def _main(self):
        await asyncio.gather(*[self._rod(i) for i in range(len(self.addr))])

    async def _rod(self, i):
        from bleak import BleakClient
        await asyncio.sleep(3.0 * i)                         # one connection at a time: the adapter is busy otherwise
        while True:
            try:
                async with BleakClient(self.addr[i], timeout=20) as c:
                    ch = next(x for s in c.services for x in s.characteristics
                              if x.uuid.startswith(("0000fff3", "0000ffe1")) and
                              ("write" in x.properties or "write-without-response" in x.properties))
                    await c.write_gatt_char(ch, ON, response=False)
                    self.status[i] = "on"; self._publish()
                    sent = None
                    while c.is_connected:
                        rgb = tuple(int(v) for v in self.cur[i])
                        if sent is None or max(abs(a - b) for a, b in zip(rgb, sent)) >= 3:
                            await c.write_gatt_char(ch, _pack(*rgb), response=False)
                            sent = rgb
                        await asyncio.sleep(0.25)
            except Exception as e:
                self.status[i] = f"{type(e).__name__}"; self._publish()
            await asyncio.sleep(10.0)                         # lost or not there: try again later
