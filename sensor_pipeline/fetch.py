import requests

BASE_URL = "https://data.sensor.community"
HEADERS = {"User-Agent": "kafka-sensor-data/1.0 (contact: ayang2012@gmail.com)"}


def fetch_all() -> list[dict]:
    """Fetch latest readings from all sensors."""
    r = requests.get(f"{BASE_URL}/static/v2/data.json", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_by_country(country: str = "DE") -> list[dict]:
    """Fetch latest readings filtered by country code."""
    r = requests.get(
        f"{BASE_URL}/airrohr/v1/filter/country={country}",
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
