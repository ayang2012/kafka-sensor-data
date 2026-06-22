"""
Build all gold tables from silver and log unregistered sensor alerts to Postgres.

Runs gold SQL files in order:
  1. pm25_by_country_hour
  2. temperature_by_region_day
  3. sensor_activity_by_customer

After building, scans silver for sensor_ids with no dim_sensors match and
writes them to Postgres alert_log as unregistered_device alerts.

Usage:
    python sql/build_gold.py

NOTE: At larger production scale this orchestration would live in Airflow,
giving richer DAG visibility, retry policies, SLA monitoring, and the ability
to fan out gold table builds in parallel.
"""
import json
import os
from pathlib import Path

import psycopg2
import snowflake.connector

SF_ACCOUNT   = os.environ["SNOWFLAKE_ACCOUNT"]
SF_USER      = os.environ["SNOWFLAKE_USER"]
SF_PASSWORD  = os.environ["SNOWFLAKE_PASSWORD"]
SF_WAREHOUSE = os.environ["SNOWFLAKE_WAREHOUSE"]
SF_DATABASE  = os.getenv("SNOWFLAKE_DATABASE", "SENSOR_DATA")

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://sensor:sensor@localhost:5432/sensordb")

GOLD_DIR = Path(__file__).parent / "gold"
GOLD_FILES = [
    "pm25_by_country_hour.sql",
    "temperature_by_region_day.sql",
    "sensor_activity_by_customer.sql",
]

UNREGISTERED_SQL = """
SELECT DISTINCT f.sensor_id, f.country, f.latitude, f.longitude, f.sensor_type
FROM SENSOR_DATA.SILVER.SENSOR_READINGS f
LEFT JOIN SENSOR_DATA.SILVER.DIM_SENSORS ds ON f.sensor_id = ds.sensor_id
WHERE ds.sensor_id IS NULL
"""


def build_gold_tables(sf_conn):
    sf_conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SF_DATABASE}.GOLD")
    for filename in GOLD_FILES:
        sql = (GOLD_DIR / filename).read_text()
        table_name = filename.replace(".sql", "").upper()
        print(f"Building GOLD.{table_name}...")
        sf_conn.execute(sql)
        sf_conn.execute(f"SELECT COUNT(*) FROM {SF_DATABASE}.GOLD.{table_name}")
        count = sf_conn.fetchone()[0]
        print(f"  -> {count:,} rows")


def alert_unregistered(sf_conn, pg_conn):
    sf_conn.execute(UNREGISTERED_SQL)
    rows = sf_conn.fetchall()
    if not rows:
        print("No unregistered sensors found in silver")
        return

    print(f"Found {len(rows)} unregistered sensor(s) in silver — checking alert_log")
    logged = 0
    with pg_conn.cursor() as cur:
        for sensor_id, country, lat, lon, sensor_type in rows:
            cur.execute(
                "SELECT 1 FROM alert_log WHERE sensor_id = %s AND alert_type = %s",
                (sensor_id, "unregistered_device"),
            )
            if cur.fetchone():
                continue  # one row per sensor, ever — already logged

            payload = {
                "sensor_id": sensor_id,
                "country": country,
                "latitude": lat,
                "longitude": lon,
                "sensor_type": sensor_type,
                "source": "gold_build",
            }
            cur.execute(
                """
                INSERT INTO alert_log (sensor_id, alert_type, payload)
                VALUES (%s, %s, %s)
                """,
                (sensor_id, "unregistered_device", json.dumps(payload)),
            )
            logged += 1
    pg_conn.commit()
    print(f"Logged {logged} new unregistered device alert(s)")


def main():
    sf_conn = snowflake.connector.connect(
        account=SF_ACCOUNT,
        user=SF_USER,
        password=SF_PASSWORD,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
    )
    pg_conn = psycopg2.connect(POSTGRES_DSN) if POSTGRES_DSN else None

    try:
        with sf_conn.cursor() as cur:
            build_gold_tables(cur)
            if pg_conn:
                alert_unregistered(cur, pg_conn)
            else:
                print("POSTGRES_DSN not set — skipping unregistered sensor alert step")
        sf_conn.commit()
        print("Gold build complete")
    finally:
        sf_conn.close()
        if pg_conn:
            pg_conn.close()


if __name__ == "__main__":
    main()
