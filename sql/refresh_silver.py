"""
Rebuild the silver SENSOR_READINGS table from bronze.

Usage:
    python sql/refresh_silver.py

NOTE: At larger production scale this would be managed by Airflow or dbt
rather than a standalone script, giving richer DAG visibility, retry
policies, and cross-team observability.
"""
import os
import snowflake.connector

SF_ACCOUNT   = os.environ["SNOWFLAKE_ACCOUNT"]
SF_USER      = os.environ["SNOWFLAKE_USER"]
SF_PASSWORD  = os.environ["SNOWFLAKE_PASSWORD"]
SF_WAREHOUSE = os.environ["SNOWFLAKE_WAREHOUSE"]
SF_DATABASE  = os.getenv("SNOWFLAKE_DATABASE", "SENSOR_DATA")

SILVER_SQL = """
CREATE OR REPLACE TABLE SENSOR_DATA.SILVER.SENSOR_READINGS AS
SELECT
    reading_id,
    sensor_id,
    sensor_type,
    TRY_TO_TIMESTAMP_TZ(ingested_at)          AS ingested_at,
    latitude,
    longitude,
    country,
    TRY_PARSE_JSON("values"):P1::FLOAT        AS pm25,
    TRY_PARSE_JSON("values"):P2::FLOAT        AS pm10,
    TRY_PARSE_JSON("values"):temperature::FLOAT    AS temperature,
    TRY_PARSE_JSON("values"):humidity::FLOAT       AS humidity,
    TRY_PARSE_JSON("values"):pressure::FLOAT       AS pressure,
    TRY_PARSE_JSON("values"):pressure_at_sealevel::FLOAT AS pressure_at_sealevel
FROM SENSOR_DATA.BRONZE.SENSOR_READINGS
QUALIFY ROW_NUMBER() OVER (PARTITION BY reading_id ORDER BY ingested_at) = 1
"""


def main():
    conn = snowflake.connector.connect(
        account=SF_ACCOUNT,
        user=SF_USER,
        password=SF_PASSWORD,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
    )
    try:
        with conn.cursor() as cur:
            print("Refreshing SILVER.SENSOR_READINGS from bronze...")
            cur.execute(SILVER_SQL)
            cur.execute("SELECT COUNT(*) FROM SENSOR_DATA.SILVER.SENSOR_READINGS")
            count = cur.fetchone()[0]
            print(f"Silver table refreshed: {count:,} rows")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
