# ✈️ Air Tracker: Flight Analytics

An end-to-end data project: it collects aviation data from the AeroDataBox API,
stores it in a MySQL database, and explores it in an interactive Streamlit dashboard.

## Objectives
- Extract airport, flight, aircraft and delay data from the AeroDataBox REST API
- Flatten nested JSON into a relational MySQL schema
- Answer 11 analytical questions with SQL
- Present results in an interactive Streamlit app

## Tech stack
Python · MySQL · SQLAlchemy · pandas · Streamlit · Plotly · AeroDataBox (RapidAPI)

## Project structure
```
air-tracker-flight-analytics/
├── app/streamlit_app.py     # Streamlit dashboard
├── src/
│   ├── config.py            # settings and env variables
│   ├── db.py                # connection, schema creation, query helper
│   ├── api_client.py        # cached API client with retries
│   ├── transform.py         # JSON -> relational rows
│   └── load_data.py         # ETL pipeline
├── sql/
│   ├── schema.sql           # table definitions and indexes
│   └── queries.sql          # the 11 required SQL queries
├── docs/screenshots/
├── .env.example
├── requirements.txt
└── README.md
```

## Database schema
| Table | Purpose |
|---|---|
| `airport` | Airport details: codes, name, city, country, continent, coordinates, timezone |
| `aircraft` | Registration, model, manufacturer, type code, owner |
| `flights` | One row per flight, with route, scheduled and actual times, status, airline |
| `airport_delays` | Daily delay statistics per airport |

`flights` references `airport` (origin and destination) and `aircraft` (registration)
through foreign keys. Indexes exist on origin, destination, aircraft, status, airline
and scheduled times.

## Setup
1. Clone the repo and create a virtual environment:
   ```bash
   git clone https://github.com/<your-username>/air-tracker-flight-analytics.git
   cd air-tracker-flight-analytics
   python -m venv venv
   venv\Scripts\activate          # Mac/Linux: source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Create the MySQL database:
   ```sql
   CREATE DATABASE air_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
3. Copy `.env.example` to `.env` and fill in your values:
   ```
   API_HOST=aerodatabox.p.rapidapi.com
   API_KEY=your_rapidapi_key
   DB_URL=mysql+pymysql://user:password@localhost:3306/air_tracker
   ```
4. Load the data (takes several minutes the first time; API responses are cached):
   ```bash
   python -m src.load_data
   ```
5. Start the app:
   ```bash
   streamlit run app/streamlit_app.py
   ```

## App features
- **Dashboard:** totals, status split, top airlines, most used aircraft models
- **Search & Filter Flights:** by flight number or airline, status, origin and date range, with pagination and CSV download
- **Airport Details:** location, timezone, map, departures and arrivals
- **Delay Analysis:** delay percentages and median delays by airport
- **Route Leaderboards:** busiest routes and most delayed airports
- **SQL Queries:** runs each of the 11 required queries live

## Design decisions and challenges
- **Rate limits:** every API response is cached in `data/raw/`, calls are paced, and
  429 responses are retried with backoff.
- **12-hour window:** the flights endpoint allows at most 12 hours per call, so the
  period is split into 12-hour windows.
- **Missing registrations:** some flights have no aircraft registration, so the aircraft
  model is stored on the flight too. Model-based queries still work.
- **Foreign keys:** counterpart airports seen in flights are loaded into `airport` so
  no route loses its origin or destination.
- **Delay statistics:** the API gives a rolling snapshot rather than daily totals, so
  daily figures are derived from the flights table, and the API's `delayIndex` is used
  for the latest day.
- **Idempotent loads:** inserts use upserts, so the pipeline can be re-run safely.

## Key insights
[Fill in 3 to 5 findings from your own data, for example: which airport handles the
most arrivals, which airline has the highest delay share, the busiest route, and the
share of domestic versus international flights.]

## Screenshots
![Dashboard](docs/screenshots/dashboard.png)
![Search](docs/screenshots/search.png)
![Delays](docs/screenshots/delays.png)
![Routes](docs/screenshots/routes.png)

## Author
[Your name]