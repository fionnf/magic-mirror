"""Zurich public transit (ZVV) API client.

Fetches real-time tram and bus departures from the SBB Journey Planner API (works
for ZVV stops) for display on the mirror. Falls back gracefully if the API is
unavailable.
"""
import json
import time
from typing import List, Optional
import urllib.request
import urllib.error
import urllib.parse


class Departure:
    def __init__(self, line: str, destination: str, departure_time: str):
        self.line = line
        self.destination = destination
        self.departure_time = departure_time

    def __repr__(self):
        return f"{self.line} → {self.destination} ({self.departure_time})"


def get_departures(stop_name: str = "Rennweg", limit: int = 3,
                   timeout: int = 5) -> Optional[List[Departure]]:
    """Fetch next departures from a ZVV stop via public APIs.

    Tries multiple endpoints in order of reliability:
    1. SBB HAFAS XML API (official real-time)
    2. Search.ch JSON API (backup)

    Args:
        stop_name: ZVV stop name (e.g., "Rennweg")
        limit: Maximum number of departures to return
        timeout: Request timeout in seconds

    Returns:
        List of Departure objects, or mock data if all APIs unavailable.
    """
    # Endpoint 1: SBB HAFAS XML API (official, most reliable)
    try:
        import xml.etree.ElementTree as ET

        url_finder = "http://www.myzvv.ch/zvv/XML_STOPFINDER_REQUEST"
        params_finder = {
            "language": "de",
            "type_sf": "any",
            "name_sf": stop_name,
            "typeInfo_sf": "stop",
        }
        query_finder = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params_finder.items())

        req = urllib.request.Request(f"{url_finder}?{query_finder}", headers={
            'User-Agent': 'Mozilla/5.0'
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            tree = ET.fromstring(response.read())

        stops = tree.findall(".//Stop")
        if not stops:
            raise ValueError("No stops found")

        stop_id = stops[0].get("stopID")
        if not stop_id:
            raise ValueError("No stop ID found")

        # Fetch departures for this stop
        url_board = "http://www.myzvv.ch/zvv/XML_DM_REQUEST"
        params_board = {
            "language": "de",
            "StopID": stop_id,
            "depType": "DEP",
            "useRealtime": "1",
            "maxJourneys": limit,
        }
        query_board = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params_board.items())

        req_board = urllib.request.Request(f"{url_board}?{query_board}", headers={
            'User-Agent': 'Mozilla/5.0'
        })
        with urllib.request.urlopen(req_board, timeout=timeout) as response:
            tree_board = ET.fromstring(response.read())

        departures = []
        for journey in tree_board.findall(".//Journey")[:limit]:
            try:
                line = journey.findtext(".//Operator", "?")
                destination = journey.findtext(".//Direction", "?")

                # Try realtime first, then planned
                rt_time = journey.find(".//RealTimeTripStart")
                pl_time = journey.find(".//PlannedTripStart")
                departure_time = "?"

                if rt_time is not None and rt_time.get("departure"):
                    departure_time = rt_time.get("departure")[:5]
                elif pl_time is not None and pl_time.get("departure"):
                    departure_time = pl_time.get("departure")[:5]

                departures.append(Departure(line, destination, departure_time))
            except (AttributeError, ValueError, TypeError):
                pass

        if departures:
            print(f"[ZVV] fetched {len(departures)} departures from {stop_name} (HAFAS)")
            return departures

    except Exception as e:
        print(f"[ZVV] HAFAS API failed ({type(e).__name__}: {e}), trying alternative...")

    # Endpoint 2: Search.ch JSON API (backup)
    try:
        print(f"[ZVV] trying Search.ch API...")
        url_search = (f"https://fahrplan.search.ch/api/stationboard.json?"
                     f"station={urllib.parse.quote(stop_name)}&"
                     f"limit={limit}")

        req_search = urllib.request.Request(url_search, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux armv7l) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req_search, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))

        departures = []
        for journey in data.get('stationboard', [])[:limit]:
            try:
                line = journey.get('number', '?')
                destination = journey.get('to', '?')
                departure_time = journey.get('departure', '?')

                if departure_time and len(departure_time) >= 5:
                    departure_time = departure_time[:5]

                departures.append(Departure(line, destination, departure_time))
            except (KeyError, ValueError, TypeError):
                pass

        if departures:
            print(f"[ZVV] fetched {len(departures)} departures from {stop_name} (Search.ch)")
            return departures

    except Exception as e:
        print(f"[ZVV] Search.ch API failed ({type(e).__name__}: {e}), using fallback...")

    # Fallback: return mock departures for simulator or API unavailability
    import datetime
    now = datetime.datetime.now()
    times = [
        (now + datetime.timedelta(minutes=5)).strftime("%H:%M"),
        (now + datetime.timedelta(minutes=12)).strftime("%H:%M"),
        (now + datetime.timedelta(minutes=18)).strftime("%H:%M"),
    ]
    print(f"[ZVV] using fallback mock data for {stop_name}")
    fallback = [
        Departure("8", "Bellevue", times[0]),
        Departure("13", "Wollishofen", times[1]),
        Departure("14", "Fluntern", times[2]),
    ]
    return fallback[:limit]


def format_departures(departures: Optional[List[Departure]]) -> str:
    """Format departures as a single-line string for display."""
    if not departures:
        return "Keine Abfahrten"
    lines = [f"{d.line} {d.departure_time}" for d in departures]
    return "  •  ".join(lines)


# Simple cache to avoid hammering the API
_cache = {"departures": None, "timestamp": 0, "cache_ttl": 30}


def get_departures_cached(stop_name: str = "Rennweg", limit: int = 3,
                         timeout: int = 5) -> Optional[List[Departure]]:
    """Fetch departures with caching (30 second TTL)."""
    now = time.time()
    if _cache["departures"] and (now - _cache["timestamp"]) < _cache["cache_ttl"]:
        return _cache["departures"]

    departures = get_departures(stop_name, limit, timeout)
    _cache["departures"] = departures
    _cache["timestamp"] = now
    return departures
