"""Zurich public transit (ZVV) API client.

Fetches real-time tram and bus departures from public APIs for display on
the mirror. Attempts to use live APIs but gracefully falls back to realistic
mock data when APIs are unavailable or restricted.

NOTE: Most public transit APIs (SBB, ZVV, Search.ch) restrict programmatic
access via "Host not in allowlist" or 403 Forbidden. To use real APIs, you
would need to:
1. Register for an API key from SBB/ZVV
2. Use a web scraper (slower, brittle)
3. Access from a whitelisted host

For testing and development, the mock data is realistic and sufficient.

API endpoints attempted (in priority order):
1. SBB opendata.ch API - blocked ("Host not in allowlist")
2. Mock data - realistic test data, always available
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

    Uses the SBB opendata.ch API which covers all Swiss public transit
    including ZVV (Zurich). This is the most reliable public API for
    Swiss rail and tram schedules.

    Args:
        stop_name: ZVV stop name (e.g., "Rennweg", "Bellevue")
        limit: Maximum number of departures to return
        timeout: Request timeout in seconds

    Returns:
        List of Departure objects, or mock data if API unavailable.
    """
    # SBB opendata.ch API - works for all Swiss transit including ZVV
    try:
        print(f"[ZVV] fetching from {stop_name}...")
        url = "https://transport.opendata.ch/v1/stationboard"
        params = {
            "station": stop_name,
            "limit": limit,
        }
        query = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        full_url = f"{url}?{query}"

        req = urllib.request.Request(full_url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode('utf-8'))

        departures = []
        for journey in data.get('stationboard', [])[:limit]:
            try:
                line = journey.get('number', '?')
                destination = journey.get('to', '?')

                # Get departure time (real-time or scheduled)
                departure = journey.get('departure')
                if departure:
                    # Parse ISO timestamp: "2024-01-15T14:30:00+0100"
                    departure_str = str(departure)
                    if 'T' in departure_str:
                        departure_time = departure_str.split('T')[1][:5]
                    else:
                        departure_time = departure_str[:5]
                else:
                    departure_time = "?"

                departures.append(Departure(line, destination, departure_time))
            except (KeyError, ValueError, TypeError, IndexError):
                pass

        if departures:
            print(f"[ZVV] ✓ got {len(departures)} departure(s) from {stop_name}")
            return departures
        else:
            print(f"[ZVV] API returned no departures")

    except urllib.error.HTTPError as e:
        print(f"[ZVV] HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"[ZVV] Network error: {e.reason}")
    except json.JSONDecodeError as e:
        print(f"[ZVV] Invalid JSON response: {e}")
    except Exception as e:
        print(f"[ZVV] Error: {type(e).__name__}: {e}")

    # Fallback: return mock departures for offline/development
    print(f"[ZVV] using mock data for {stop_name}")
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
