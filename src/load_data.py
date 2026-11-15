"""End-to-end pipeline: fetch from AeroDataBox, transform, load into MySQL."""
import logging
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.api_client import (build_time_windows, get_aircraft, get_airport,
                            get_airport_delays, get_airport_flights)
from src.config import (AIRPORT_CODES, DAYS_BACK, EXTRA_AIRPORT_LIMIT,
                        MAX_AIRCRAFT_LOOKUPS)
from src.db import create_schema, get_engine
from src.transform import (transform_aircraft, transform_airport,
                           transform_delays, transform_flight)

logger = logging.getLogger(__name__)


def upsert(engine: Engine, table: str, rows: list[dict], chunk: int = 500) -> int:
    """Insert rows; on duplicate keys update, never overwriting data with NULL."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    updates = ", ".join(f"{c}=COALESCE(VALUES({c}), {c})" for c in cols)
    sql = text(
        f"INSERT INTO {table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )
    try:
        with engine.begin() as conn:
            for i in range(0, len(rows), chunk):
                conn.execute(sql, rows[i:i + chunk])
    except SQLAlchemyError:
        logger.exception("Insert into %s failed", table)
        raise
    logger.info("%s: %d rows upserted", table, len(rows))
    return len(rows)


def fetch_main_airports() -> dict[str, dict]:
    """Fetch and transform the chosen airports. Returns {iata: row}."""
    airports = {}
    for code in AIRPORT_CODES:
        row = transform_airport(get_airport(code))
        if row:
            airports[code] = row
        else:
            logger.warning("No airport data for %s", code)
    return airports


def _merge(existing: dict, new: dict) -> None:
    """Fill missing (None) fields of `existing` from `new`."""
    for key, value in new.items():
        if existing.get(key) is None and value is not None:
            existing[key] = value


def fetch_flights(airports: dict[str, dict]):
    """Fetch flights for all airports. Returns (flights, counterparts, aircraft_models)."""
    flights: dict[str, dict] = {}
    counterpart_counts: Counter = Counter()
    counterpart_info: dict[str, dict] = {}
    aircraft_models: dict[str, dict] = {}
    warned = False

    for iata, info in airports.items():
        for start, end in build_time_windows(info["timezone"], DAYS_BACK):
            payload = get_airport_flights(iata, start, end)
            if not payload:
                continue
            for kind in ("departures", "arrivals"):
                for item in payload.get(kind) or []:
                    row = transform_flight(item, kind, iata)
                    if row is None:
                        if not warned:
                            logger.warning("Skipped an item; raw keys: %s", list(item.keys()))
                            warned = True
                        continue
                    counterpart = row.pop("_counterpart")
                    model = row.get("aircraft_model")
                    other = counterpart["iata"]
                    if other not in airports:
                        counterpart_counts[other] += 1
                        counterpart_info[other] = counterpart
                    reg = row["aircraft_registration"]
                    if reg:
                        aircraft_models.setdefault(
                            reg, {"model": model, "owner": row["airline_name"]})
                    if row["flight_id"] in flights:
                        _merge(flights[row["flight_id"]], row)
                    else:
                        flights[row["flight_id"]] = row
    logger.info("Collected %d unique flights", len(flights))
    return list(flights.values()), counterpart_counts, counterpart_info, aircraft_models


def build_counterpart_airports(counts: Counter, info: dict[str, dict]) -> list[dict]:
    """Full lookups for the busiest extra airports, minimal rows for the rest."""
    rows = []
    top = {code for code, _ in counts.most_common(EXTRA_AIRPORT_LIMIT)}
    for code, raw in info.items():
        row = transform_airport(get_airport(code)) if code in top else None
        rows.append(row or transform_airport(raw))
    return [r for r in rows if r]


def build_aircraft_rows(aircraft_models: dict[str, dict]) -> list[dict]:
    """Stub rows for every registration, enriched for up to N detailed lookups."""
    rows = {}
    for reg, meta in aircraft_models.items():
        model = meta["model"]
        rows[reg] = {
            "registration": reg, "model": model,
            "manufacturer": model.split()[0] if model else None,
            "icao_type_code": None, "owner": meta["owner"],
        }
    for reg in list(rows)[:MAX_AIRCRAFT_LOOKUPS]:
        detailed = transform_aircraft(get_aircraft(reg))
        if detailed:
            for key, value in detailed.items():
                if value is not None:
                    rows[reg][key] = value
    return list(rows.values())


def delays_from_flights(engine: Engine) -> list[dict]:
    """Fallback: derive per-airport daily delay stats from departures in `flights`."""
    df = pd.read_sql(
        "SELECT origin_iata, scheduled_departure, status, delay_minutes FROM flights "
        "WHERE scheduled_departure IS NOT NULL AND origin_iata IN "
        "(SELECT iata_code FROM airport)", engine)
    if df.empty:
        return []
    df["delay_date"] = pd.to_datetime(df["scheduled_departure"]).dt.date
    rows = []
    for (iata, day), grp in df.groupby(["origin_iata", "delay_date"]):
        delayed = int((grp["status"] == "Delayed").sum())
        median = grp["delay_minutes"].dropna().median()
        rows.append({
            "airport_iata": iata, "delay_date": day,
            "total_flights": int(len(grp)), "delayed_flights": delayed,
            "delay_index": round(100 * delayed / len(grp), 2),  # % delayed (approximation)
            "median_delay_min": int(median) if pd.notna(median) else None,
            "canceled_flights": int((grp["status"] == "Cancelled").sum()),
        })
    return rows


def load_delays(engine: Engine, airports: dict[str, dict]) -> None:
    """Daily delay stats derived from flights; delay_index taken from the API snapshot."""
    rows = delays_from_flights(engine)
    snapshot = {}
    for iata in airports:
        row = transform_delays(get_airport_delays(iata), iata, "")
        if row and row["delay_index"] is not None:
            snapshot[iata] = row["delay_index"]

    latest = {}
    for r in rows:
        code = r["airport_iata"]
        if code not in latest or r["delay_date"] > latest[code]:
            latest[code] = r["delay_date"]
    for r in rows:
        code = r["airport_iata"]
        if r["delay_date"] == latest[code] and code in snapshot:
            r["delay_index"] = snapshot[code]
    upsert(engine, "airport_delays", rows)


def run() -> None:
    """Run the full ETL pipeline."""
    engine = get_engine()
    create_schema(engine)

    airports = fetch_main_airports()
    upsert(engine, "airport", list(airports.values()))

    flights, counts, info, aircraft_models = fetch_flights(airports)
    upsert(engine, "airport", build_counterpart_airports(counts, info))
    upsert(engine, "aircraft", build_aircraft_rows(aircraft_models))
    upsert(engine, "flights", flights)
    load_delays(engine, airports)

    with engine.connect() as conn:
        for table in ("airport", "aircraft", "flights", "airport_delays"):
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f"{table}: {count} rows")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run()