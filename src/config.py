"""Central configuration loaded from environment variables."""
import os

from dotenv import load_dotenv

load_dotenv()

API_HOST = os.getenv("API_HOST", "aerodatabox.p.rapidapi.com")
API_KEY = os.getenv("API_KEY")
DB_URL = os.getenv("DB_URL")

if not API_KEY:
    raise RuntimeError("API_KEY is missing. Set it in your .env file.")
if not DB_URL:
    raise RuntimeError("DB_URL is missing. Set it in your .env file.")

API_HEADERS = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": API_HOST,
}

# Airports to analyse (mix of Indian domestic + international hubs)
AIRPORT_CODES = [
    "DEL", "BOM", "BLR", "MAA", "HYD", "CCU",   # India
    "DXB", "LHR", "JFK", "SIN", "SYD", "FRA",   # International
]

# How many days of flight history to fetch (each day = 2 API calls per airport)
DAYS_BACK = 1

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3