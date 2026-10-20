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


DEPLOY_KEY = os.path.expanduser(os.environ.get("GALLERY_DEPLOY_KEY", "~/.ssh/fortuna_deploy"))
CLONE = os.path.expanduser(os.environ.get("GALLERY_CLONE", "~/fortuna-gallery"))


def _git(*args, cwd=CLONE):
    env = dict(os.environ, GIT_SSH_COMMAND=f"ssh -i {DEPLOY_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new")
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]}: {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout


_BROKEN = ("is empty", "corrupt", "bad object", "loose object", "unable to mmap", "not a git repository",
           "did not send all necessary objects", "dubious ownership")


def _commit_with_deploy_key(files, message):
    """The wall's way: a small sparse clone pushed over SSH with a deploy key (write access to this
    one repository only), so no personal token has to live on the Pi. The clone holds nothing that
    is not on GitHub, so a damaged one (a power cut mid-write) is moved aside and cloned afresh."""
    try:
        return _commit_in_clone(files, message)
    except RuntimeError as e:
        if not any(b in str(e) for b in _BROKEN):
            raise
        import time
        aside = f"{CLONE}.broken-{int(time.time())}"
        os.rename(CLONE, aside)
        print(f"[publish] clone damaged ({str(e)[:80]}): moved to {aside}, cloning afresh", flush=True)
        return _commit_in_clone(files, message)


def _commit_in_clone(files, message):
    if not os.path.isdir(os.path.join(CLONE, ".git")):
        _git("clone", "--depth", "1", "--filter=blob:none", "--sparse", "--branch", BRANCH,
             f"git@github.com:{REPO}.git", CLONE, cwd=os.path.dirname(CLONE))
        _git("sparse-checkout", "set", "gallery", "wall")
        _git("config", "user.name", "fortuna-wall")
        _git("config", "user.email", "wall@users.noreply.github.com")
    for attempt in range(3):
        _git("fetch", "--depth", "1", "origin", BRANCH)
        _git("reset", "--hard", f"origin/{BRANCH}")
        for path, data in files.items():
            full = os.path.join(CLONE, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(data)
        _git("add", "--sparse", *files)
        if not _git("status", "--porcelain").strip():
            return None
        _git("commit", "-q", "-m", message)
        try:
            _git("push", "-q", "origin", f"HEAD:{BRANCH}")
            return _git("rev-parse", "HEAD").strip()
        except RuntimeError:                      # someone pushed in between: fetch and try again
            continue
    raise RuntimeError("could not push to the gallery after 3 tries")


def available():
    return bool(_token()) or os.path.exists(DEPLOY_KEY)


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


def commit_files(files, message):
    """One commit putting {repo path: bytes} on the branch (unchanged files skipped). -> sha or None."""
    import hashlib
    tok = _token()
    if not tok:
        if os.path.exists(DEPLOY_KEY):
            return _commit_with_deploy_key(files, message)
        raise RuntimeError("no GALLERY_TOKEN, gh login or deploy key - cannot publish")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28"})

    def call(method, path, **kw):
        r = s.request(method, f"{API}/repos/{REPO}/{path}", timeout=30, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"GitHub {method} {path}: {r.status_code} {r.text[:160]}")
        return r.json()

    head = call("GET", f"git/ref/heads/{BRANCH}")["object"]["sha"]
    base_tree = call("GET", f"git/commits/{head}")["tree"]["sha"]
    existing = {}
    try:
        for e in call("GET", f"git/trees/{base_tree}?recursive=1")["tree"]:
            existing[e["path"]] = e["sha"]
    except RuntimeError:
        pass
    tree = []
    for path, data in files.items():
        if existing.get(path) == hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest():
            continue
        blob = call("POST", "git/blobs", json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    if not tree:
        return None
    new_tree = call("POST", "git/trees", json={"base_tree": base_tree, "tree": tree})["sha"]
    commit = call("POST", "git/commits", json={"message": message, "tree": new_tree, "parents": [head]})["sha"]
    call("PATCH", f"git/refs/heads/{BRANCH}", json={"sha": commit})
    return commit


def publish(dates, message=None):
    """One commit with these editions' files. Returns the commit sha (None if nothing changed)."""
    files = {}
    names = []
    for d in dates:
        files.update(files_for(d))
        with open(daily._path(d, "json")) as fh:
            names.append(f"{d} {json.load(fh).get('name', '')}")
    sha = commit_files(files, message or "Gallery: " + "; ".join(names))
    if sha:
        print(f"[gallery] published {', '.join(dates)} -> {sha[:7]}", flush=True)
    return sha


def announce_wall(url):
    """Tell the Pages control app where the wall is reachable right now (wall/wall.json)."""
    import time
    return commit_files({"wall/wall.json": json.dumps({"url": url, "since": int(time.time())}).encode()},
                        "Wall: new remote address")


if __name__ == "__main__":
    args = sys.argv[1:]
    ds = [d for d, _ in daily.editions()] if args == ["--all"] else args
    print(publish(ds) or "already up to date")
