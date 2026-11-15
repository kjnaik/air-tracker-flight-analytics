"""Quick manual test of the API client (uses a few requests)."""
import json
import logging

from src.api_client import (build_time_windows, get_aircraft, get_airport,
                            get_airport_delays, get_airport_flights)

logging.basicConfig(level=logging.INFO)

airport = get_airport("DEL")
print("=== AIRPORT ===")
print(json.dumps(airport, indent=2)[:1500])

tz = airport["timeZone"]
start, end = build_time_windows(tz, 1)[0]
flights = get_airport_flights("DEL", start, end)
print("\n=== FLIGHTS (keys) ===", list(flights.keys()) if flights else None)
if flights:
    print("departures:", len(flights.get("departures", [])),
          "arrivals:", len(flights.get("arrivals", [])))
    sample = (flights.get("departures") or flights.get("arrivals"))[0]
    print(json.dumps(sample, indent=2)[:2500])

reg = (sample.get("aircraft") or {}).get("reg")
if reg:
    print("\n=== AIRCRAFT", reg, "===")
    print(json.dumps(get_aircraft(reg), indent=2)[:1500])

print("\n=== DELAYS ===")
print(json.dumps(get_airport_delays("DEL"), indent=2)[:1500])