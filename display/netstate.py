"""A tiny "offline" mark in the wall's bottom-left corner while the Pi has no internet.

    n = NetState()          # checks the connection on a side thread every 15 s
    img = n.mark(img)       # PIL image in, same image out (a copy with the mark only while offline)

Seven pixels wide: a wifi fan with a slash. Dim, so it is a hint, not a light.
"""
import socket
import threading
import time

_ICON = [               # 7 x 7: . off, w wifi, r slash
    ".wwwww.",
    "w.....w",
    "..www.r",
    ".w..rw.",
    "...r...",
    "..r....",
    ".r.....",
]
_COL = {"w": (110, 110, 120), "r": (200, 50, 40)}


class NetState:
    def __init__(self):
        self.offline = False
        self._fails = 0
        threading.Thread(target=self._run, daemon=True).start()

    @staticmethod
    def _reach():
        for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
            try:
                socket.create_connection(host, timeout=3).close()
                return True
            except OSError:
                continue
        return False

    def _run(self):
        time.sleep(20)                                   # let the network come up after boot before judging
        while True:
            if self._reach():
                self._fails, self.offline = 0, False
            else:
                self._fails += 1
                self.offline = self._fails >= 2          # two misses in a row: not a blip
            time.sleep(15)

    def mark(self, img):
        if not self.offline:
            return img
        img = img.copy()
        px = img.load()
        x0, y0 = 3, img.size[1] - 3 - len(_ICON)
        for dy, row in enumerate(_ICON):
            for dx, c in enumerate(row):
                if c != ".":
                    px[x0 + dx, y0 + dy] = _COL[c]
        return img
