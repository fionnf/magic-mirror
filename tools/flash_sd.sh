#!/usr/bin/env bash
# Write a Raspberry Pi OS image to an SD card (macOS). The one step that needs your password (sudo).
#   ./tools/flash_sd.sh path/to/image.img /dev/disk4
# Refuses anything that is not a 16-256 GB disk, or that holds a mounted APFS/system volume. It ERASES the card.
set -euo pipefail
IMG="${1:?usage: flash_sd.sh image.img /dev/diskN}"; DISK="${2:?usage: flash_sd.sh image.img /dev/diskN}"
[ -f "$IMG" ] || { echo "no such image: $IMG"; exit 1; }
case "$DISK" in /dev/disk[0-9]*) ;; *) echo "give the whole disk, like /dev/disk4"; exit 1;; esac
INFO="$(diskutil info "$DISK")"
SIZE=$(echo "$INFO" | awk -F'[()]' '/Disk Size|Total Size/{print $2; exit}' | awk '{print $1}')
GB=$(( ${SIZE:-0} / 1000000000 ))
echo "$INFO" | grep -E "Device / Media Name|Disk Size|Protocol|Removable|Solid State" || true
[ "$GB" -ge 16 ] && [ "$GB" -le 256 ] || { echo "refusing: $DISK is ${GB} GB"; exit 1; }
if diskutil list "$DISK" | grep -q -E "APFS|Apple_Boot|Recovery"; then echo "refusing: $DISK holds a Mac system volume"; exit 1; fi
echo "Writing $(basename "$IMG") to $DISK (${GB} GB). This erases it."
diskutil unmountDisk "$DISK"
sudo dd if="$IMG" of="${DISK/disk/rdisk}" bs=4m
sync
diskutil eject "$DISK"
echo "Done: put the card in the Pi."
