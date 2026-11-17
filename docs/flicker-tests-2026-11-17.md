# Flicker experiments after the rewiring to three HUB75 ports (2026-11-17)

Wall: 12 panels (64x64, FM6126A), Raspberry Pi 4 "mirror4" (1800 MHz, `isolcpus=3`, onboard audio off), Adafruit Bonnet, `hardware_mapping = "regular"`.
Judged by eye by the owner, on the wall. Pi readings come from `panel_setup/display_test.py` (`--show-refresh` and the built-in Pi monitor).
"Lowest" is the worst refresh dip seen during the run, which matters more for flicker than the median.

## 1. Rewiring and panel numbers

Rewired from two chains of six (ports 1 and 3) to **three chains of four (ports 1, 2, 3)** to cut flicker.
`config.py`: `PORT_SLOTS = [0, 1, 2]`, `CHAIN_PER_PORT = 4`, `PARALLEL = 3`. Panel numbers (chain index, port 1 = 0-3, port 2 = 4-7, port 3 = 8-11)
read off the wall with `./panel_setup/run.sh numbers`, top row first, as seen from the front:

```
 9 10 11
 8  7  6   (mounted upside down)
 3  2  1   (mounted upside down)
 4  5  0
```

`PANEL_CHAIN_ORDER = [(2,3),(2,2),(1,2),(0,2), (0,3),(1,3),(2,1),(1,1), (0,1),(0,0),(1,0),(2,0)]`, `PANEL_ROTATE = {1,2,3,6,7,8: 180}`. Confirmed: all 12 show, arrows up.

## 2. Things that went wrong (so they are not repeated)

- **The Pi reverts the code on every `wall-control` start.** `panel_setup/update.sh` (ExecStartPre) does `git reset --hard` to GitHub `master`. Starting the service wiped the rsync-deployed
  `config.py` and everything else uncommitted, so the wall ran the old 2-chain layout and ports were missing (seen as only 9, 10, 11, 8, 5, 4, 3, 2). Fix: commit and push to `master`
  before starting the service, or only run the tests through `display_test.py`, which does not trigger the update.
- `pwm_lsb_nanoseconds` must be **50..3000**. lsb 40 makes the library exit with "Invalid range", so four tests (R2, R3, R5, R6) never ran and the wall stayed dark for them.
  The owner's verdict for "R2" in that round is therefore unreliable; the round was re-run as Q1-Q6.
- `BRIGHTNESS_CAP` is 75, so `--brightness 100` silently ran at 75 until `WALL_BRIGHTNESS_CAP=100` was passed (the runner does this).
- `--refresh-limit 0` crashes `led_matrix.py` (division by zero in `_hw_brightness`). Use a large number (400) for "no cap".
- An uncapped refresh makes the panels **brighter** (duty grows with refresh), which makes flicker easier to see. Compare tests at a locked refresh.
- `pkill -f display_test` inside an SSH command kills that SSH command's own shell. Use `pkill -f "[p]ython3 panel_setup/display_test"` in a separate call.

## 3. Round 0: is it power or software?

Moving gradient, 6 PWM bits, lsb 60, refresh cap 100 Hz unless noted.

| Run | Brightness | Slowdown | Lowest refresh | Pi | Verdict |
|---|---|---|---|---|---|
| 1 | 75 | 7 | 68-70 Hz | 47% CPU, 60 C, ~18 A | no verdict recorded |
| 2 | 75 | 5 | 85.5 Hz | 44% CPU, 58 C, ~18 A | "flickered a lot in bright areas" |
| 3 | 75 | 7 | 87.0 Hz | 44% CPU, 57 C, ~18 A | "very flickery" |
| 4 | 35 | 7 | 87.4 Hz | 44% CPU, 58 C, ~8.4 A | "also flickers" |

Conclusions: slowdown 7 was the flicker-free setting on the old wiring but flickered now. Flicker at 35% brightness (8 A) rules out supply sag. Pi timing is fine
(`isolcpus=3`, audio off, no throttling, `throttled=0x0` throughout), which rules out software jitter.

## 4. Refresh headroom with the 100 Hz cap removed (brightness 100, lsb 60, cap 400)

| Slowdown | 5 bits | 6 bits | 7 bits |
|---|---|---|---|
| 7 | low 105 / med 177 | low 91 / med 145 | low 78 / med 124 |
| 5 | low 129 / med 239 | low 103 / med 207 | low 100 / med 181 |
| 4 | low 126 / med 261 | low 115 / med 229 | low 112 / med 203 |

The owner wants at least 110 Hz. At lsb 100-200 (slowdown 6 or 7) the worst dips fell to 62-98 Hz, so longer pulses are out; lsb must stay at 60 or lower (50 is the library minimum).

## 5. Round T: bright tiles with panel numbers, brightness 100, uncapped refresh, lsb 60

New pattern `display_test.py --pattern flicker --label "..."`: saturated bright tiles, each panel's chain number, a moving white bar, the test label across the top.

| Test | Slowdown | Bits | Lowest | Verdict |
|---|---|---|---|---|
| T0 | 7 | 6 | 99.8 (capped at 100) | slight flicker |
| T1 | 4 | 6 | 179.8 | more flicker, a lot brighter |
| T2 | 4 | 7 | 155.6 | flicker |
| T3 | 5 | 5 | 184.1 | very bad banding in places |
| T4 | 4 | 5 | 204.0 | a little better, a little streaky |
| T5 | 7 | 5 | 143.5 | flicker, no streaks or wrong colours |
| T6 | 5 | 6 | 163.7 | streaky and flicker |

Conclusions: slowdown 4 and 5 give streaks and banding (data too fast for the cables); only 6 and 7 are clean. More refresh alone did not cure flicker.

## 6. Round Q: refresh locked at 130 Hz, brightness 100 (valid lsb)

| Test | Slowdown | Bits | lsb (ns) | Lowest Hz | Verdict |
|---|---|---|---|---|---|
| Q1 | 7 | 5 | 60 | 129.8 | very good, almost no flicker (only at the eye corner) |
| Q2 | 7 | 5 | 50 | 129.7 | no flicker, rare colour jumps |
| Q3 | 7 | 6 | 50 | 128.5 | very slight flicker, no colour jumps |
| Q4 | 6 | 5 | 60 | 129.8 | no flicker, slight colour jumps sometimes |
| Q5 | 6 | 5 | 50 | 129.8 | a little more flicker, rare colour jumps |
| Q6 | 6 | 6 | 50 | 129.7 | next to no flicker, no colour jumps |

All six held at least 128.5 Hz; Pi 57-59 C, ~27 A at 100% on this pattern (28 A software budget), no throttling.
(An earlier R1 = Q1 and R4 = Q4 also ran fine at 129.7 Hz; R1: "pretty good, very slightly noticeable at the eye corner".)

## 7. Result

Best: **Q6 = slowdown 6, 6 PWM bits, lsb 50, refresh locked at 130 Hz**. Runner-up: Q1 (slowdown 7, 5 bits, lsb 60).
**Applied 2026-11-17** (`config.py`): `GPIO_SLOWDOWN` 6, `MATRIX_PWM_BITS` 6, `MATRIX_PWM_LSB_NS` 50, `MATRIX_REFRESH_LIMIT_HZ` 130, `PWM_BITS_HZ` 130 for 5 and 6 bits
(so the brightness scaling matches the locked refresh), `DEPTH_STEPS = []` (7-8 bits would pull the refresh under 110 Hz; untested at these settings).
`wall_control.py` no longer overrides slowdown 7 / 100 Hz for the dark live boards (`DARK_MODES`): they use the same settings as every piece.
`BRIGHTNESS_CAP` is still 75 (the tests ran at 100).

**Applying settings to the Pi:** the service resets the code to GitHub on every start (see section 2), so after an rsync deploy run
`sudo touch /tmp/wall-update.stamp` (the stamp is root-owned) before `sudo systemctl restart wall-control`; `update.sh` then skips for ten minutes.
Pushing to `master` is the real fix.

Reproduce: copy `tools/flicker_run.sh` to the Pi, then
`/tmp/flicker_run.sh NAME BRIGHTNESS BITS LSB_NS SLOWDOWN SECS flicker --refresh-limit 130 --label "..."` (stop `wall-control` first).
