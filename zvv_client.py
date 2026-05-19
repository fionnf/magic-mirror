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
    """Fetch next departures from a ZVV stop.

    In the simulator or when the API is unavailable, returns mock data.

    Args:
        stop_name: ZVV stop name (e.g., "Rennweg")
        limit: Maximum number of departures to return
        timeout: Request timeout in seconds

    Returns:
        List of Departure objects, or None if API unavailable.
    """
    try:
        # Try SBB Journey Planner REST API - works for ZVV stops
        url = (f"https://fahrplan.search.ch/api/stationboard.json?"
               f"station={urllib.parse.quote(stop_name)}&"
               f"limit={limit}")

        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))

        departures = []
        for journey in data.get('stationboard', [])[:limit]:
            try:
                line = journey.get('number', '?')
                destination = journey.get('to', '?')
                departure_str = journey.get('departure', '')
                if departure_str:
                    departure_time = departure_str
                else:
                    departure_time = "?"

                departures.append(Departure(line, destination, departure_time))
            except (KeyError, ValueError):
                pass

        if departures:
            return departures
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError) as e:
        print(f"[ZVV] API fetch failed ({type(e).__name__}), using fallback data")
    except Exception as e:
        print(f"[ZVV] unexpected error: {e}")

    # Fallback: return mock departures for simulator or API unavailability
    import datetime
    now = datetime.datetime.now()
    times = [
        (now + datetime.timedelta(minutes=5)).strftime("%H:%M"),
        (now + datetime.timedelta(minutes=12)).strftime("%H:%M"),
        (now + datetime.timedelta(minutes=18)).strftime("%H:%M"),
    ]
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
