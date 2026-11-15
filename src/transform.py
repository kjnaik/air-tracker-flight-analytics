"""Flatten nested AeroDataBox JSON into rows matching the relational schema."""
import logging
import re
from datetime import datetime

from src.config import DELAY_THRESHOLD_MIN

logger = logging.getLogger(__name__)


def _utc(block: dict | None) -> datetime | None:
    """Parse the 'utc' value of a time block into a naive UTC datetime."""
    if not isinstance(block, dict) or not block.get("utc"):
        return None
    try:
        return datetime.strptime(block["utc"][:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _times(block: dict | None) -> tuple[datetime | None, datetime | None]:
    """Return (scheduled, actual) times from a movement block."""
    block = block or {}
    scheduled = _utc(block.get("scheduledTime"))
    actual = _utc(block.get("runwayTime")) or _utc(block.get("revisedTime"))
    return scheduled, actual


def normalize_status(raw_status: str | None, delay_min: int | None) -> str:
    """Map API statuses to: On Time, Delayed, Cancelled, Diverted, Unknown."""
    status = raw_status or "Unknown"
    if status.lower().startswith("cancel"):
        return "Cancelled"
    if status in ("Unknown", "Diverted"):
        return status
    if status == "Delayed" or (delay_min is not None and delay_min > DELAY_THRESHOLD_MIN):
        return "Delayed"
    return "On Time"


def transform_airport(raw: dict | None) -> dict | None:
    """Convert an airport JSON object to an `airport` table row."""
    if not raw or not raw.get("iata"):
        return None
    location = raw.get("location") or {}
    return {
        "icao_code": raw.get("icao"),
        "iata_code": raw.get("iata"),
        "name": raw.get("fullName") or raw.get("name") or raw.get("shortName"),
        "city": raw.get("municipalityName"),
        "country": (raw.get("country") or {}).get("name"),
        "continent": (raw.get("continent") or {}).get("name"),
        "latitude": location.get("lat"),
        "longitude": location.get("lon"),
        "timezone": raw.get("timeZone"),
    }


def transform_flight(item: dict, kind: str, queried_iata: str) -> dict | None:
    """Convert one departure/arrival item to a `flights` row.

    `kind` is 'departures' or 'arrivals' (relative to the queried airport).
    Returns None if the origin, destination or number cannot be determined.
    """
    own_key, leg_key = (("departure", "arrival") if kind == "departures"
                        else ("arrival", "departure"))
    own = item.get(own_key) or {}
    leg = item.get(leg_key) or item.get("movement") or {}

    other = leg.get("airport") or own.get("airport") or {}
    if other.get("iata") == queried_iata:
        other = {}
    if not other.get("iata"):
        return None

    own_sched, own_actual = _times(own)
    leg_sched, leg_actual = _times(leg)
    if kind == "departures":
        origin, dest = queried_iata, other["iata"]
        sched_dep, act_dep, sched_arr, act_arr = own_sched, own_actual, leg_sched, leg_actual
    else:
        origin, dest = other["iata"], queried_iata
        sched_dep, act_dep, sched_arr, act_arr = leg_sched, leg_actual, own_sched, own_actual

    number = (item.get("number") or "").replace(" ", "")
    anchor = sched_dep or sched_arr
    if not number or anchor is None:
        return None

    delay_min = None
    if own_sched and own_actual:
        delay_min = int((own_actual - own_sched).total_seconds() // 60)

    aircraft = item.get("aircraft") or {}
    airline = item.get("airline") or {}
    return {
        "flight_id": f"{number}_{origin}_{dest}_{anchor:%Y%m%d}",
        "flight_number": number,
        "aircraft_registration": aircraft.get("reg"),
        "origin_iata": origin,
        "destination_iata": dest,
        "scheduled_departure": sched_dep,
        "actual_departure": act_dep,
        "scheduled_arrival": sched_arr,
        "actual_arrival": act_arr,
        "status": normalize_status(item.get("status"), delay_min),
        "airline_code": airline.get("iata") or airline.get("icao"),
        "airline_name": airline.get("name"),
        "delay_minutes": delay_min,
        # helper fields, removed by the loader before inserting
        "_counterpart": other,
        "aircraft_model": aircraft.get("model"),
    }


def transform_aircraft(raw: dict | None) -> dict | None:
    """Convert an aircraft JSON object to an `aircraft` table row."""
    if not raw or not raw.get("reg"):
        return None
    model = raw.get("model") or raw.get("typeName")
    return {
        "registration": raw["reg"],
        "model": model,
        "manufacturer": model.split()[0] if model else None,
        "icao_type_code": raw.get("modelCode"),
        "owner": raw.get("airlineName"),
    }


def _to_minutes(value) -> int | None:
    """Convert 'HH:MM:SS' strings or numbers to whole minutes."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.match(r"^(-?)(\d+):(\d+)", str(value))
    if not match:
        return None
    minutes = int(match.group(2)) * 60 + int(match.group(3))
    return -minutes if match.group(1) else minutes


def transform_delays(raw: dict | None, iata: str, date_str: str) -> dict | None:
    """Convert the airport delay statistics JSON to an `airport_delays` row."""
    if not raw:
        return None
    blocks = [raw.get("departuresDelayInformation"), raw.get("arrivalsDelayInformation")]
    blocks = [b for b in blocks if isinstance(b, dict)]
    if not blocks:
        return None

    total = sum(b.get("numTotal") or 0 for b in blocks)
    cancelled = sum(b.get("numCancelled") or 0 for b in blocks)
    delayed = sum(
        v for b in blocks for k, v in b.items()
        if k.startswith("num") and "Delayed" in k and isinstance(v, (int, float))
    )
    medians = [m for m in (_to_minutes(b.get("medianDelay")) for b in blocks) if m is not None]
    indexes = [b["delayIndex"] for b in blocks if b.get("delayIndex") is not None]
    if not total:
        return None
    return {
        "airport_iata": iata,
        "delay_date": date_str,
        "total_flights": total,
        "delayed_flights": delayed,
        "delay_index": round(sum(indexes) / len(indexes), 2) if indexes else None,
        "median_delay_min": int(sum(medians) / len(medians)) if medians else None,
        "canceled_flights": cancelled,
    }