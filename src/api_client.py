"""Thin, cached client for the AeroDataBox API (via RapidAPI)."""
import hashlib
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from src.config import API_HEADERS, API_HOST, MAX_RETRIES, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

BASE_URL = f"https://{API_HOST}"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(path: str, params: dict | None) -> Path:
    """Build a unique cache filename for a request."""
    key = path + json.dumps(params or {}, sort_keys=True)
    digest = hashlib.md5(key.encode()).hexdigest()[:10]
    safe = path.strip("/").replace("/", "_").replace(":", "-")[:80]
    return CACHE_DIR / f"{safe}_{digest}.json"


def _get(path: str, params: dict | None = None) -> dict | list | None:
    """GET a path with caching, retries and rate-limit handling.

    Returns parsed JSON, or None if the resource does not exist / has no data.
    """
    cache_file = _cache_path(path, params)
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))

    url = f"{BASE_URL}{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                url, headers=API_HEADERS, params=params, timeout=REQUEST_TIMEOUT
            )
            if response.status_code == 429:
                wait = 5 * attempt
                logger.warning("Rate limited (429). Waiting %ss...", wait)
                time.sleep(wait)
                continue
            if response.status_code in (204, 404):
                logger.info("No data for %s (%s)", path, response.status_code)
                return None

            if response.status_code in (400, 403, 422):
                logger.error("Request rejected (%s) for %s: %s",
                             response.status_code, path, response.text[:200])
                return None 
                      
            response.raise_for_status()
            data = response.json()
            cache_file.write_text(json.dumps(data), encoding="utf-8")
            time.sleep(1.1)  # stay under ~1 request/second
            return data
        except requests.RequestException as exc:
            logger.warning("Attempt %s/%s failed for %s: %s",
                           attempt, MAX_RETRIES, path, exc)
            time.sleep(2 * attempt)
    logger.error("Giving up on %s", path)
    return None


def get_airport(iata_code: str) -> dict | None:
    """Fetch airport details by IATA code."""
    return _get(f"/airports/iata/{iata_code}")


def get_airport_flights(iata_code: str, from_local: datetime,
                        to_local: datetime) -> dict | None:
    """Fetch arrivals and departures for one airport in a time window.

    The API allows a maximum window of 12 hours. Times are airport-local.
    """
    fmt = "%Y-%m-%dT%H:%M"
    path = (f"/flights/airports/iata/{iata_code}/"
            f"{from_local.strftime(fmt)}/{to_local.strftime(fmt)}")
    params = {
        "direction": "Both",
        "withLeg": "true",
        "withCancelled": "true",
        "withCodeshared": "false",
        "withCargo": "false",
        "withPrivate": "false",
        "withLocation": "false",
    }
    return _get(path, params)


def get_aircraft(registration: str) -> dict | None:
    """Fetch aircraft details by registration."""
    return _get(f"/aircrafts/reg/{registration}")


def get_airport_delays(iata_code: str, date_local: str | None = None) -> dict | None:
    """Fetch delay statistics for an airport (current, or for a given date)."""
    path = f"/airports/iata/{iata_code}/delays"
    if date_local:
        path += f"/{date_local}"
    return _get(path)


def build_time_windows(timezone: str, days_back: int) -> list[tuple[datetime, datetime]]:
    """Split the last `days_back` days into 12-hour windows (airport-local time)."""
    now_local = datetime.now(ZoneInfo(timezone)).replace(
        minute=0, second=0, microsecond=0, tzinfo=None
    )
    windows = []
    end = now_local
    for _ in range(days_back * 2):
        start = end - timedelta(hours=12)
        windows.append((start, end - timedelta(minutes=1)))
        end = start
    return windows