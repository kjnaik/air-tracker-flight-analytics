import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_HOST = os.getenv("API_HOST")
API_KEY = os.getenv("API_KEY")

headers = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": API_HOST,
}

url = f"https://{API_HOST}/airports/iata/DEL"
response = requests.get(url, headers=headers, timeout=30)

print(response.status_code)
print(response.json())