"""Publish art-of-the-day editions to the public Fortuna gallery (GitHub Pages).

Each edition's public files go into the repo's gallery/ folder as one commit through the GitHub API;
the Pages workflow then rebuilds the site and its RSS feed. Nothing private is published: the songs
the room heard and the token counts stay on the wall's computer.

Needs a token that may write to the repo: GALLERY_TOKEN in .env (a fine-grained personal access token,
"Contents: read and write" on that one repository). On a laptop with the GitHub CLI logged in,
`gh auth token` is used instead. GALLERY_REPO overrides the repository (default fionnf/magic-mirror).

    python3 -m display.publish 2026-10-09        # publish one edition by hand
    python3 -m display.publish --all
"""
import base64
import json
import os
import subprocess
import sys

import requests

from display import daily

REPO = os.environ.get("GALLERY_REPO", "fionnf/magic-mirror")
BRANCH = os.environ.get("GALLERY_BRANCH", "master")
API = "https://api.github.com"
PRIVATE = ("songs", "tokens")


def _token():
    tok = os.environ.get("GALLERY_TOKEN", "").strip()
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def available():
    return bool(_token())


def public_meta(meta):
    return {k: v for k, v in meta.items() if k not in PRIVATE}


def files_for(date):
    """{repo path: bytes} for one edition."""
    out = {}
    with open(daily._path(date, "json")) as fh:
        meta = json.load(fh)
    out[f"gallery/{date}.json"] = json.dumps(public_meta(meta), indent=1).encode()
    for ext in ("frag", "png", "final.png"):
        p = daily._path(date, ext)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                out[f"gallery/{date}.{ext}"] = fh.read()
    return out


def publish(dates, message=None):
    """One commit with these editions' files. Returns the commit sha (None if nothing changed)."""
    tok = _token()
    if not tok:
        raise RuntimeError("no GALLERY_TOKEN (and no gh login) - the gallery cannot be published")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28"})

    def call(method, path, **kw):
        r = s.request(method, f"{API}/repos/{REPO}/{path}", timeout=30, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {method} {path}: {r.status_code} {r.text[:160]}")
        return r.json()

    files = {}
    for d in dates:
        files.update(files_for(d))
    head = call("GET", f"git/ref/heads/{BRANCH}")["object"]["sha"]
    base_tree = call("GET", f"git/commits/{head}")["tree"]["sha"]
    # skip files that are already identical on the branch
    existing = {}
    try:
        for e in call("GET", f"git/trees/{base_tree}?recursive=1")["tree"]:
            if e["path"].startswith("gallery/"):
                existing[e["path"]] = e["sha"]
    except RuntimeError:
        pass
    import hashlib
    tree = []
    for path, data in files.items():
        if existing.get(path) == hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest():
            continue
        blob = call("POST", "git/blobs", json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    if not tree:
        return None
    new_tree = call("POST", "git/trees", json={"base_tree": base_tree, "tree": tree})["sha"]
    names = []
    for d in dates:
        with open(daily._path(d, "json")) as fh:
            names.append(f"{d} {json.load(fh).get('name', '')}")
    msg = message or "Gallery: " + "; ".join(names)
    commit = call("POST", "git/commits", json={"message": msg, "tree": new_tree, "parents": [head]})["sha"]
    call("PATCH", f"git/refs/heads/{BRANCH}", json={"sha": commit})
    print(f"[gallery] published {', '.join(dates)} ({len(tree)} files) -> {commit[:7]}", flush=True)
    return commit


if __name__ == "__main__":
    args = sys.argv[1:]
    ds = [d for d, _ in daily.editions()] if args == ["--all"] else args
    print(publish(ds) or "already up to date")
