#!/usr/bin/env python3
"""Test script for ZVV transit API.

Usage:
  python tests/test_zvv_api.py                 # fetch departures from Rennweg
  python tests/test_zvv_api.py --stop "Bellevue"  # fetch from different stop
  python tests/test_zvv_api.py --limit 5      # fetch more departures
  python tests/test_zvv_api.py --timeout 10   # longer timeout for slow connections
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import zvv_client


def main():
    p = argparse.ArgumentParser(description="Test ZVV transit API")
    p.add_argument("--stop", default="Rennweg",
                   help="ZVV stop name (default: Rennweg)")
    p.add_argument("--limit", type=int, default=5,
                   help="number of departures to fetch (default: 5)")
    p.add_argument("--timeout", type=int, default=5,
                   help="request timeout in seconds (default: 5)")
    p.add_argument("--cached", action="store_true",
                   help="use cached departures (30s TTL)")
    args = p.parse_args()

    print(f"[TEST] Fetching departures from '{args.stop}'...")
    print(f"       Limit: {args.limit}, Timeout: {args.timeout}s")
    if args.cached:
        print("       Using cache (30s TTL)")
    print()

    try:
        if args.cached:
            departures = zvv_client.get_departures_cached(args.stop, limit=args.limit,
                                                          timeout=args.timeout)
        else:
            departures = zvv_client.get_departures(args.stop, limit=args.limit,
                                                   timeout=args.timeout)

        if departures:
            print(f"✓ Success! Got {len(departures)} departure(s):\n")
            for i, dep in enumerate(departures, 1):
                print(f"  {i}. {dep.line:6} → {dep.destination:20} at {dep.departure_time}")
            print()
            print(f"Formatted: {zvv_client.format_departures(departures)}")
        else:
            print("✗ No departures returned")
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
