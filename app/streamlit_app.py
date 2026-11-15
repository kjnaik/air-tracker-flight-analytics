"""Air Tracker: Flight Analytics - Streamlit dashboard."""
import re
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Make `src` importable when running `streamlit run app/streamlit_app.py`
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db import get_engine, run_query  # noqa: E402

st.set_page_config(page_title="Air Tracker", page_icon="✈️", layout="wide")


@st.cache_resource
def engine():
    """One shared database engine for the whole app."""
    return get_engine()


@st.cache_data(ttl=300)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Cached query helper. `params` is a tuple of (name, value) pairs."""
    return run_query(engine(), sql, dict(params))


MAIN_AIRPORTS = ("DEL", "BOM", "BLR", "MAA", "HYD", "CCU",
                 "DXB", "LHR", "JFK", "SIN", "SYD", "FRA")

# ---------------------------------------------------------------- sidebar
st.sidebar.title("✈️ Air Tracker")
page = st.sidebar.radio("Navigate", [
    "Dashboard", "Search & Filter Flights", "Airport Details",
    "Delay Analysis", "Route Leaderboards", "SQL Queries"])

try:
    q("SELECT 1")
except Exception as exc:  # noqa: BLE001
    st.error(f"Cannot connect to the database: {exc}")
    st.stop()

# ---------------------------------------------------------------- dashboard
if page == "Dashboard":
    st.title("Air Tracker: Flight Analytics")
    stats = q("""
        SELECT (SELECT COUNT(*) FROM airport) AS airports,
               (SELECT COUNT(*) FROM flights) AS flights,
               (SELECT COUNT(*) FROM aircraft) AS aircraft,
               (SELECT ROUND(AVG(median_delay_min), 1) FROM airport_delays
                 WHERE airport_iata IN :main) AS avg_delay
    """.replace(":main", str(MAIN_AIRPORTS))).iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total airports", f"{int(stats.airports):,}")
    c2.metric("Total flights fetched", f"{int(stats.flights):,}")
    c3.metric("Aircraft tracked", f"{int(stats.aircraft):,}")
    c4.metric("Avg median delay (min)",
              "n/a" if pd.isna(stats.avg_delay) else stats.avg_delay)

    left, right = st.columns(2)
    status = q("SELECT status, COUNT(*) AS flights FROM flights GROUP BY status")
    left.plotly_chart(px.pie(status, names="status", values="flights",
                             title="Flights by status", hole=0.4),
                      use_container_width=True)
    airlines = q("""SELECT airline_name, COUNT(*) AS flights FROM flights
                    WHERE airline_name IS NOT NULL GROUP BY airline_name
                    ORDER BY flights DESC LIMIT 10""")
    right.plotly_chart(px.bar(airlines, x="flights", y="airline_name",
                              orientation="h", title="Top 10 airlines"),
                       use_container_width=True)
    models = q("""SELECT aircraft_model AS model, COUNT(*) AS flights FROM flights
                  WHERE aircraft_model IS NOT NULL GROUP BY aircraft_model
                  ORDER BY flights DESC LIMIT 10""")
    st.plotly_chart(px.bar(models, x="model", y="flights",
                           title="Most used aircraft models"),
                    use_container_width=True)

# ---------------------------------------------------------------- search
elif page == "Search & Filter Flights":
    st.title("Search & Filter Flights")
    c1, c2, c3 = st.columns(3)
    text_search = c1.text_input("Flight number or airline", "")
    statuses = q("SELECT DISTINCT status FROM flights ORDER BY status")["status"].tolist()
    status_sel = c2.multiselect("Status", statuses)
    origins = q("""SELECT DISTINCT origin_iata FROM flights
                   WHERE origin_iata IS NOT NULL ORDER BY origin_iata""")["origin_iata"].tolist()
    origin_sel = c3.multiselect("Origin airport", origins)
    bounds = q("SELECT DATE(MIN(scheduled_departure)) AS lo, "
               "DATE(MAX(scheduled_departure)) AS hi FROM flights").iloc[0]
    date_range = st.date_input("Departure date range", (bounds.lo, bounds.hi))

    where, params = ["1=1"], {}
    if text_search:
        where.append("(f.flight_number LIKE :s OR f.airline_name LIKE :s "
                     "OR f.airline_code LIKE :s)")
        params["s"] = f"%{text_search.strip()}%"
    if status_sel:
        keys = [f"st{i}" for i in range(len(status_sel))]
        where.append("f.status IN (" + ",".join(f":{k}" for k in keys) + ")")
        params.update(dict(zip(keys, status_sel)))
    if origin_sel:
        keys = [f"og{i}" for i in range(len(origin_sel))]
        where.append("f.origin_iata IN (" + ",".join(f":{k}" for k in keys) + ")")
        params.update(dict(zip(keys, origin_sel)))
    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        where.append("DATE(f.scheduled_departure) BETWEEN :d1 AND :d2")
        params["d1"], params["d2"] = date_range

    sql = f"""
        SELECT f.flight_number, f.airline_name, f.origin_iata, f.destination_iata,
               f.scheduled_departure, f.actual_departure, f.scheduled_arrival,
               f.actual_arrival, f.status, f.aircraft_registration, f.aircraft_model
        FROM flights f WHERE {' AND '.join(where)}
        ORDER BY f.scheduled_departure DESC
    """
    result = q(sql, tuple(params.items()))
    st.caption(f"{len(result):,} flights match")
    page_size = 100
    pages = max(1, -(-len(result) // page_size))
    page_no = st.number_input("Page", 1, pages, 1)
    st.dataframe(result.iloc[(page_no - 1) * page_size: page_no * page_size],
                 use_container_width=True, hide_index=True)
    st.download_button("Download all results (CSV)", result.to_csv(index=False),
                       "flights.csv", "text/csv")

# ---------------------------------------------------------------- airport
elif page == "Airport Details":
    st.title("Airport Details")
    airports = q("""SELECT iata_code, name FROM airport
                    WHERE iata_code IN :main ORDER BY name
                 """.replace(":main", str(MAIN_AIRPORTS)))
    choice = st.selectbox("Select airport", airports["iata_code"],
                          format_func=lambda c: f"{c} - "
                          f"{airports.set_index('iata_code').loc[c, 'name']}")
    info = q("SELECT * FROM airport WHERE iata_code = :c",
             (("c", choice),)).iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("City", info.city)
    c2.metric("Country", info.country)
    c3.metric("Timezone", info.timezone)
    st.write(f"**ICAO:** {info.icao_code}  |  **Continent:** {info.continent}  "
             f"|  **Coordinates:** {info.latitude}, {info.longitude}")
    st.map(pd.DataFrame({"lat": [info.latitude], "lon": [info.longitude]}))

    dep = q("""SELECT f.flight_number, f.airline_name, f.destination_iata,
                      f.scheduled_departure, f.status
               FROM flights f WHERE f.origin_iata = :c
               ORDER BY f.scheduled_departure DESC LIMIT 200""", (("c", choice),))
    arr = q("""SELECT f.flight_number, f.airline_name, f.origin_iata,
                      f.scheduled_arrival, f.status
               FROM flights f WHERE f.destination_iata = :c
               ORDER BY f.scheduled_arrival DESC LIMIT 200""", (("c", choice),))
    t1, t2 = st.tabs([f"Departures ({len(dep)})", f"Arrivals ({len(arr)})"])
    t1.dataframe(dep, use_container_width=True, hide_index=True)
    t2.dataframe(arr, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- delays
elif page == "Delay Analysis":
    st.title("Delay Analysis")
    df = q("""
        SELECT d.airport_iata, a.name,
               SUM(d.total_flights) AS total_flights,
               SUM(d.delayed_flights) AS delayed_flights,
               ROUND(100 * SUM(d.delayed_flights) / NULLIF(SUM(d.total_flights), 0), 2)
                   AS delayed_pct,
               ROUND(AVG(d.median_delay_min), 1) AS avg_median_delay_min,
               SUM(d.canceled_flights) AS canceled_flights
        FROM airport_delays d JOIN airport a ON a.iata_code = d.airport_iata
        WHERE d.airport_iata IN :main
        GROUP BY d.airport_iata, a.name
    """.replace(":main", str(MAIN_AIRPORTS)))
    if df.empty:
        st.info("No delay data for the selected airports.")
    else:
        pick = st.multiselect("Airports", df["airport_iata"].tolist(),
                              default=df["airport_iata"].tolist())
        view = df[df["airport_iata"].isin(pick)]
        c1, c2 = st.columns(2)
        c1.plotly_chart(px.bar(view.sort_values("delayed_pct", ascending=False),
                               x="airport_iata", y="delayed_pct",
                               title="% of departures delayed"),
                        use_container_width=True)
        c2.plotly_chart(px.bar(view.sort_values("avg_median_delay_min", ascending=False),
                               x="airport_iata", y="avg_median_delay_min",
                               title="Average median delay (min)"),
                        use_container_width=True)
        st.dataframe(view, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- leaderboards
elif page == "Route Leaderboards":
    st.title("Route Leaderboards")
    top_n = st.slider("Rows to show", 5, 50, 15)
    routes = q("""
        SELECT f.origin_iata, f.destination_iata,
               CONCAT(f.origin_iata, ' → ', f.destination_iata) AS route,
               COUNT(*) AS flights
        FROM flights f
        WHERE f.origin_iata IS NOT NULL AND f.destination_iata IS NOT NULL
        GROUP BY f.origin_iata, f.destination_iata
        ORDER BY flights DESC LIMIT :n""", (("n", top_n),))
    st.subheader("Busiest routes")
    st.plotly_chart(px.bar(routes, x="route", y="flights"), use_container_width=True)
    st.dataframe(routes[["route", "flights"]], use_container_width=True, hide_index=True)

    st.subheader("Most delayed airports (by % of departures delayed)")
    delayed = q("""
        SELECT a.iata_code, a.name, COUNT(*) AS departures,
               ROUND(100 * SUM(f.status = 'Delayed') / COUNT(*), 2) AS delayed_pct
        FROM flights f JOIN airport a ON a.iata_code = f.origin_iata
        GROUP BY a.iata_code, a.name
        HAVING COUNT(*) >= 20
        ORDER BY delayed_pct DESC LIMIT :n""", (("n", top_n),))
    st.dataframe(delayed, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- SQL queries
else:
    st.title("SQL Queries")
    text = (ROOT / "sql" / "queries.sql").read_text(encoding="utf-8")
    blocks = [b.strip() for b in re.split(r"(?m)^(?=-- Q\d+:)", text) if b.strip()]
    titles = [b.splitlines()[0].lstrip("- ").strip() for b in blocks]
    idx = st.selectbox("Choose a query", range(len(blocks)),
                       format_func=lambda i: titles[i])
    st.code(blocks[idx], language="sql")
    if st.button("Run query"):
        try:
            st.dataframe(q(blocks[idx].rstrip(";")),
                         use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Query failed: {exc}")