#!/usr/bin/env bash
# Run before the wall starts (ExecStartPre): bring the code up to the latest master on GitHub.
# Never blocks the wall: no network, no key or a failed fetch just means it starts with what it has.
# Tracked files are reset to GitHub's; untracked files (.env, assets, wall_state.json, tokens) are untouched.
cd "$(dirname "$0")/.." || exit 0
STAMP=/tmp/wall-update.stamp
if [ -f "$STAMP" ] && [ $(( $(date +%s) - $(stat -c %Y "$STAMP") )) -lt 600 ]; then
    exit 0                                   # pulled within 10 minutes (a quick restart or a crash loop)
fi
[ -d .git ] || { echo "[update] not a git checkout: skipping"; exit 0; }
KEY="${GALLERY_DEPLOY_KEY:-$HOME/.ssh/fortuna_deploy}"
[ -f "$KEY" ] || KEY=/home/pi/.ssh/fortuna_deploy
for i in 1 2 3 4 5 6; do                     # at boot the network can lag behind the service
    getent hosts github.com >/dev/null 2>&1 && break
    sleep 3
done
if [ -f "$KEY" ]; then
    export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
    URL="git@github.com:fionnf/magic-mirror.git"
else
    URL="https://github.com/fionnf/magic-mirror.git"
fi
before=$(git rev-parse --short HEAD 2>/dev/null)
if timeout 40 git fetch --quiet "$URL" master 2>/tmp/wall-update.err; then
    git reset --hard FETCH_HEAD --quiet 2>>/tmp/wall-update.err
    touch "$STAMP"
    echo "[update] $before -> $(git rev-parse --short HEAD)"
else
    echo "[update] fetch failed ($(tail -1 /tmp/wall-update.err)); starting with the code already here"
fi
exit 0
