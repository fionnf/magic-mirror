# Train boards: Kilchberg and Zürich HB

Two live departure boards in the app's **Live boards**, drawn like a station display (amber LED dots on black), in `display/kilchberg.py`:

| Mode | Shows |
|---|---|
| `kilchberg` ("Kilchberg trains") | the next 6 trains from **Kilchberg ZH** (S8, S24, the night S-Bahn SN8 ...) |
| `zurichhb` ("Zürich HB trains") | the next 7 trains from **Zürich HB** (IC, IR, S and night lines), platforms like `43/44` |

Each row: the line, the destination (long ones shortened: "Pfäffik. SZ", "Flughafen"), the platform (`Gl`) and the minutes. A train more than 2 minutes late shows its minutes in red with "+n Min" under the destination;
one that is pulling in shows a small train-front symbol instead of the minutes; anything an hour or more away shows its clock time. The header has the station and the clock, the footer the date (in German). If the data cannot be fetched the footer scrolls
"Keine Daten - Verbindung zur Fahrplanauskunft unterbrochen", like the real boards, instead of showing stale times.

**Data**: `transport.opendata.ch` (the Swiss timetable, no key), `stationboard` for the station with `transportations[]=train` (so no trams or buses from the same stop), fetched every 30 s on a side thread; the minutes count down live between fetches.
(The original tram board, `trams`, uses the same service for Rennweg: `display/departures.py`.)

**Your own station**: `TrainBoard(station, rows, title=...)` in `display/kilchberg.py` takes any station name the API knows (Swiss and some border stations). Add a `frame_xyz` function like `frame_hb`, a line in `_anims()` in `panel_setup/play.py`,
an entry in `MODES`, `LIVE_THUMBS` and the heavy-mode tuple in `panel_setup/wall_control.py`, and the id in `LIVE_IDS` in `panel_setup/web/index.html`.
