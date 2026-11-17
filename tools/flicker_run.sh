#!/usr/bin/env bash
# usage: ft.sh NAME BRIGHTNESS BITS LSB_NS SLOWDOWN [SECS] [PATTERN] [extra display_test args...]
N=$1; B=$2; BITS=$3; LSB=$4; SL=$5; S=${6:-40}; P=${7:-gradient}
shift $(( $# < 7 ? $# : 7 ))
cd ~/magic-mirror
sudo pkill -f "[p]ython3 panel_setup/display_test" 2>/dev/null; sleep 2
sudo timeout "$S" python3 panel_setup/display_test.py --pattern "$P" --brightness "$B" --pwm-bits "$BITS" --lsb-ns "$LSB" --slowdown "$SL" --show-refresh --log /tmp/$N.csv "$@" > /tmp/$N.log 2>&1
echo "== $N: brightness $B, bits $BITS, lsb $LSB, slowdown $SL, $P, extra: $*"
grep -a -o "\[PI\][^[]*" /tmp/$N.log | tail -2 | cut -c1-150
grep -a -o "lowest: [0-9.]*Hz" /tmp/$N.log | tail -1
grep -a -o "[0-9.]*Hz" /tmp/$N.log | tr -d Hz | sort -n | awk '{a[NR]=$1} END{print "refresh readings: min",a[1],"median",a[int(NR/2)],"max",a[NR]}'
echo "$(vcgencmd get_throttled) $(vcgencmd measure_temp)"
