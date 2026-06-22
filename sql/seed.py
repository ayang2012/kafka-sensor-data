"""
Seed dim_sensors from sensor_profiles.pkl.

Usage:
    python sql/seed.py
"""
import os
import pickle
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

PROFILES_PATH = Path(__file__).parent.parent / "sensor_profiles.pkl"
DSN = os.getenv("POSTGRES_DSN", "postgresql://sensor:sensor@localhost:5432/sensordb")

REGION_CUSTOMERS = {
    "Europe":        [1, 2],
    "North America": [3, 4],
    "Asia-Pacific":  [5],
    "Other":         [6],
}


def assign_region(lat: float, lon: float, country: str) -> str:
    eu_countries = {
        "DE", "FR", "IT", "ES", "PL", "NL", "BE", "SE", "AT", "CH",
        "CZ", "HU", "RO", "BG", "HR", "SK", "SI", "PT", "GR", "FI",
        "DK", "NO", "LT", "LV", "EE", "LU", "IE", "GB", "RS", "BA",
        "UA", "BY", "MD", "AL", "MK", "ME", "XK",
    }
    if country in eu_countries:
        return "Europe"
    if -170 <= lon <= -30 and 10 <= lat <= 85:
        return "North America"
    if 60 <= lon <= 180 and -15 <= lat <= 75:
        return "Asia-Pacific"
    return "Other"


def assign_customer(sensor_id: int, region: str) -> int:
    pool = REGION_CUSTOMERS.get(region, REGION_CUSTOMERS["Other"])
    return pool[sensor_id % len(pool)]


def main():
    if not PROFILES_PATH.exists():
        print(f"ERROR: {PROFILES_PATH} not found. Run bootstrap first.", file=sys.stderr)
        sys.exit(1)

    profiles = pickle.loads(PROFILES_PATH.read_bytes())
    print(f"Loaded {len(profiles)} sensor profiles")

    rows = []
    for p in profiles:
        region = assign_region(p["latitude"], p["longitude"], p["country"])
        customer_id = assign_customer(p["id"], region)
        rows.append((
            p["id"],
            p["sensor_type"],
            p["latitude"],
            p["longitude"],
            p["country"],
            region,
            customer_id,
        ))

    conn = psycopg2.connect(DSN)
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO dim_sensors
                    (sensor_id, sensor_type, latitude, longitude, country, region, customer_id)
                VALUES %s
                ON CONFLICT (sensor_id) DO NOTHING
                """,
                rows,
            )
        conn.commit()
        print(f"Inserted {len(rows)} sensors into dim_sensors")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
