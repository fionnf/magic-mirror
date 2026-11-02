#!/usr/bin/env bash
# Run before the wall starts (ExecStartPre): bring the code up to the latest master on GitHub.
# Never blocks the wall: no network, no key or a failed fetch just means it starts with what it has.
# Tracked files are reset to GitHub's; untracked files (.env, assets, wall_state.json, tokens) are untouched.
cd "$(dirname "$0")/.." || exit 0
LOG=panel_setup/logs/update.log
mkdir -p panel_setup/logs 2>/dev/null
say() {                                      # to the journal and to a log the app can show (panel_setup/logs/update.log, last 200 lines)
    echo "[update] $*"
    echo "[$(date '+%F %T')] $*" >> "$LOG" 2>/dev/null
    [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 400 ] && tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
}
STAMP=/tmp/wall-update.stamp
if [ -f "$STAMP" ] && [ $(( $(date +%s) - $(stat -c %Y "$STAMP") )) -lt 600 ]; then
    say "skipped: the code was updated less than 10 minutes ago"
    exit 0                                   # pulled within 10 minutes (a quick restart or a crash loop)
fi
git() { command git -c safe.directory="$PWD" "$@"; }   # runs as root in a folder the pi user may own
[ -d .git ] || git init -q                 # a rsync-deployed copy has no history yet: the first pull creates it
find .git -maxdepth 1 -name 'index.lock' -mmin +1 -delete 2>/dev/null      # a git killed half way leaves this behind, and every update then fails quietly
free=$(df -Pm . 2>/dev/null | awk 'NR==2{print $4}')
[ -n "$free" ] && [ "$free" -lt 150 ] && say "WARNING: only ${free} MB free on the disk: updates may fail"
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
    if git reset --hard FETCH_HEAD --quiet 2>>/tmp/wall-update.err; then
        touch "$STAMP"                       # only a SUCCESSFUL update counts: a failed one must be retried at the next start
        say "$before -> $(git rev-parse --short HEAD)"
    else
        say "reset failed ($(tail -1 /tmp/wall-update.err)); staying on $before"
    fi
else
    say "fetch failed ($(tail -1 /tmp/wall-update.err)); starting with the code already here ($before)"
fi
exit 0
