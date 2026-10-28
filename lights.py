"""Smart Life / Tuya lights, controlled locally over the home network (tinytuya).

Devices come from either
  panel_setup/lights.json   {"devices": [{"name", "id", "ip", "key", "version", "kind"}], ...}
  devices.json              the file written by `python -m tinytuya wizard` (id, name, key, ip, ver, ...)
Both contain each light's LOCAL KEY (a secret): they are git-ignored - never commit them.

    status()                      -> [{"name", "on": True/False/None, "error": ""}]
    set_all(False)                -> turn every light off (in parallel, 5 s timeout each)
    set_one("Living room", True)
    schedule()/set_schedule()     -> a daily "lights off at HH:MM" the wall controller fires
"""
import datetime
import json
import os
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(_HERE, "panel_setup", "lights.json")
WIZARD_FILE = os.path.join(_HERE, "devices.json")
STATE_FILE = os.path.join(_HERE, "panel_setup", "lights_state.json")
TIMEOUT = 5.0
# Tuya category codes that are lights (dj = light, dd = strip, xdd = ceiling, fwd = ambient, ...)
LIGHT_CATEGORIES = {"dj", "dd", "xdd", "fwd", "dc", "tgq", "tyndj"}
# everything we may switch (lights + sockets/switches); sensors, gateways and sub-devices are skipped
CONTROLLABLE = LIGHT_CATEGORIES | {"cz", "kg", "pc"}
CACHE_FILE = os.path.join(_HERE, "panel_setup", "lights_cache.json")      # {id: {"ip", "version"}} from a scan


def _read(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return None


def devices():
    """List of device dicts (name, id, ip, key, version, kind)."""
    cfg = _read(FILE) or {}
    raw = cfg.get("devices")
    if raw is None:                                       # fall back to the wizard's file
        raw = [{"name": d.get("name"), "id": d.get("id"), "ip": d.get("ip", ""), "key": d.get("key"),
                "version": d.get("ver", 3.3),
                "kind": "bulb" if d.get("category") in LIGHT_CATEGORIES else "outlet"}
               for d in (_read(WIZARD_FILE) or []) if isinstance(d, dict) and d.get("key")
               and not d.get("sub") and d.get("category", "dj") in CONTROLLABLE]
    found = _read(CACHE_FILE) or {}                       # addresses found by a network scan
    out = []
    for d in raw:
        if d.get("id") and d.get("key"):
            c = found.get(d["id"], {})
            out.append({"name": d.get("name") or d["id"][:8], "id": d["id"],
                        "ip": d.get("ip") or c.get("ip") or "Auto",
                        "key": d["key"], "version": float(c.get("version") or d.get("version") or 3.3),
                        "kind": d.get("kind", "bulb")})
    only = cfg.get("only")                                # optional: restrict to some names
    return [d for d in out if not only or d["name"] in only]


def installed():
    try:
        import tinytuya  # noqa: F401
        return True
    except Exception:
        return False


def _connect(d):
    import tinytuya
    cls = tinytuya.BulbDevice if d["kind"] == "bulb" else tinytuya.OutletDevice
    dev = cls(d["id"], d["ip"], d["key"])
    dev.set_version(d["version"])
    dev.set_socketPersistent(False)
    dev.set_socketTimeout(TIMEOUT)
    dev.set_socketRetryLimit(1)
    return dev


def _is_on(status):
    dps = (status or {}).get("dps") or {}
    for k in ("20", "1", "switch_led", "switch_1"):      # bulbs use 20, plugs/switches use 1
        if k in dps:
            return bool(dps[k])
    return None


def _brightness(status):
    """Bulb brightness as 0-100, or None (newer bulbs report 10-1000 on dps 22, older 25-255 on dps 3)."""
    dps = (status or {}).get("dps") or {}
    if "22" in dps and str(dps.get("21", "white")) != "colour":
        return max(1, min(100, round(int(dps["22"]) / 10)))
    if "3" in dps:
        return max(1, min(100, round(int(dps["3"]) / 2.55)))
    return None


def _run_each(devs, fn):
    """Run fn(device_dict) for every device in parallel; never blocks longer than ~TIMEOUT+1 s."""
    results = {}

    def work(d):
        try:
            results[d["name"]] = fn(d)
        except Exception as e:
            results[d["name"]] = {"error": str(e)[:80]}
    threads = [threading.Thread(target=work, args=(d,), daemon=True) for d in devs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT + 1.0)
    return results


def status():
    def one(d):
        st = _connect(d).status()
        if st and st.get("Error"):
            return {"on": None, "error": str(st["Error"])[:80]}
        return {"on": _is_on(st), "error": "", "brightness": _brightness(st)}
    res = _run_each(devices(), one)
    return [{"name": d["name"], "kind": d["kind"], **res.get(d["name"], {"on": None, "error": "no answer"})}
            for d in devices()]


def _switch(d, on):
    dev = _connect(d)
    r = dev.turn_on() if on else dev.turn_off()
    if isinstance(r, dict) and r.get("Error"):
        return {"ok": False, "error": str(r["Error"])[:80]}
    return {"ok": True, "error": ""}


def _look(d, brightness, warmth, colour):
    """Set a bulb's light: brightness 1-100, warmth 0 (warm) - 100 (cool), or colour "#rrggbb"."""
    if d["kind"] != "bulb":
        return {"ok": False, "error": "not a bulb"}
    dev = _connect(d)
    if colour:
        c = colour.lstrip("#")
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
        dev.turn_on()
        dev.set_colour(r, g, b)
        if brightness is not None:                        # a colour's brightness is its value channel
            import colorsys
            h, sat, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            dev.set_colour(*(round(x * 255) for x in colorsys.hsv_to_rgb(h, sat, max(0.04, brightness / 100))))
        return {"ok": True, "error": ""}
    dev.turn_on()
    if warmth is not None:
        dev.set_white_percentage(max(1, min(100, int(brightness if brightness is not None else 100))), int(warmth))
    elif brightness is not None:
        dev.set_brightness_percentage(max(1, min(100, int(brightness))))
    return {"ok": True, "error": ""}


def set_look(names, brightness=None, warmth=None, colour=None):
    group = [d for d in devices() if d["name"] in set(names)]
    return _run_each(group, lambda d: _look(d, brightness, warmth, colour))


def set_all(on):
    return _run_each(devices(), lambda d: _switch(d, on))


def set_one(name, on):
    devs = [d for d in devices() if d["name"] == name]
    if not devs:
        raise KeyError(f"no light called {name!r}")
    return _run_each(devs, lambda d: _switch(d, on))


# -------------------------------------------------------------------- room ---

def room():
    """Names of the lights that count as 'the room' (default: all of them)."""
    names = (_read(STATE_FILE) or {}).get("room")
    allnames = [d["name"] for d in devices()]
    return [n for n in names if n in allnames] if names is not None else allnames


def set_room_members(names):
    _save_state({"room": [str(n) for n in names]})
    return room()


def set_group(names, on):
    group = [d for d in devices() if d["name"] in set(names)]
    return _run_each(group, lambda d: _switch(d, on))


def rescan(seconds=20):
    """Find the lights' addresses and protocol versions on this network (run at home).
    Matches by device id and caches the result, so later commands connect directly."""
    import tinytuya
    try:
        found = tinytuya.deviceScan(False, seconds, byID=True)
    except TypeError:
        found = tinytuya.deviceScan(False, seconds)
    cache = {}
    for key, v in (found or {}).items():
        did = v.get("gwId") or v.get("id") or key
        if v.get("ip"):
            cache[did] = {"ip": v["ip"], "version": v.get("version") or 3.3}
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE_FILE)
    mine = {d["id"] for d in devices()}
    return {"found": len(cache), "mine": len(mine & set(cache)), "missing": sorted(
        d["name"] for d in devices() if d["id"] not in cache)}


# ---------------------------------------------------------------- schedule ---

def schedule():
    s = (_read(STATE_FILE) or {}).get("schedule", {})
    return {"off": s.get("off")}


def _save_state(update):
    st = _read(STATE_FILE) or {}
    st.update(update)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(st, fh)
    os.replace(tmp, STATE_FILE)


def set_schedule(off):
    """off: "HH:MM" or None."""
    if off is not None:
        datetime.datetime.strptime(off, "%H:%M")          # raises ValueError if malformed
    _save_state({"schedule": {"off": off}, "fired": None})
    return schedule()


def due(now=None):
    """True once per day when the scheduled off-time has passed (call every few seconds)."""
    now = now or datetime.datetime.now()
    off = schedule()["off"]
    if not off:
        return False
    st = _read(STATE_FILE) or {}
    today = now.date().isoformat()
    if st.get("fired") == today:
        return False
    hh, mm = (int(x) for x in off.split(":"))
    # fire within 10 minutes after the time (not for a time that passed hours ago, e.g. after a reboot)
    delta = (now - now.replace(hour=hh, minute=mm, second=0, microsecond=0)).total_seconds()
    if 0 <= delta <= 600:
        _save_state({"fired": today})
        return True
    return False


# ------------------------------------------------------- Smart Life import ---
# Rooms and tap-to-run scenes live in the Smart Life / Tuya cloud, not on the bulbs. The same cloud keys
# `python -m tinytuya wizard` saves (tinytuya.json) let us read them once and keep a local copy.

def _cloud():
    import tinytuya
    return tinytuya.Cloud()


def _result(r):
    if isinstance(r, dict) and r.get("success") is False:
        raise RuntimeError(str(r.get("msg") or r.get("Error") or "cloud refused")[:100])
    return (r or {}).get("result") if isinstance(r, dict) else None


def import_room(room_name="living"):
    """Read the home's rooms and scenes from Smart Life: the devices in the room whose name contains
    room_name become 'the room', and that home's tap-to-run scenes are kept for the app."""
    c = _cloud()
    mine = {d["id"]: d["name"] for d in devices()}
    cloud_devs = c.getdevices() or []
    uid = next((d.get("uid") for d in cloud_devs if isinstance(d, dict) and d.get("uid")), None)
    if not uid:
        raise RuntimeError("no Smart Life account found in the cloud keys (run: python -m tinytuya wizard)")
    homes = _result(c.cloudrequest(f"/v1.0/users/{uid}/homes")) or []
    members, scenes, room_found = [], [], ""
    for h in homes:
        hid = h.get("home_id")
        rooms = _result(c.cloudrequest(f"/v1.0/homes/{hid}/rooms")) or []
        rooms = rooms.get("rooms", []) if isinstance(rooms, dict) else rooms
        for r in rooms:
            if room_name.lower() in str(r.get("name", "")).lower():
                room_found = r.get("name", "")
                got = _result(c.cloudrequest(f"/v1.0/homes/{hid}/rooms/{r.get('room_id')}/devices")) or []
                for d in got:
                    if d.get("id") in mine:
                        members.append(mine[d["id"]])
        for sc in _result(c.cloudrequest(f"/v1.1/homes/{hid}/scenes")) or []:
            scenes.append({"id": sc.get("scene_id"), "name": sc.get("name") or "Scene", "home": hid})
    if not room_found:
        raise RuntimeError(f"no room called '{room_name}' in Smart Life")
    _save_state({"room": members, "scenes": scenes, "imported_room": room_found})
    return {"room": members, "scenes": [s["name"] for s in scenes], "room_name": room_found}


def scenes():
    return (_read(STATE_FILE) or {}).get("scenes", [])


def run_scene(scene_id):
    sc = next((s for s in scenes() if s["id"] == scene_id), None)
    if not sc:
        raise KeyError("no such scene")
    _result(_cloud().cloudrequest(f"/v1.0/homes/{sc['home']}/scenes/{scene_id}/trigger", action="POST"))
    return {"ok": True}
