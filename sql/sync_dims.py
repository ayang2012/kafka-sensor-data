"""
Sync dim_customers and dim_sensors from Postgres → Snowflake.

Usage:
    python sql/sync_dims.py

Requires env vars:
    POSTGRES_DSN
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
    SNOWFLAKE_DATABASE (default: SENSOR_DATA)
    SNOWFLAKE_SCHEMA   (default: SILVER)
    SNOWFLAKE_WAREHOUSE
"""
import os

import psycopg2
import psycopg2.extras
import snowflake.connector

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://sensor:sensor@localhost:5432/sensordb")

SF_ACCOUNT   = os.environ["SNOWFLAKE_ACCOUNT"]
SF_USER      = os.environ["SNOWFLAKE_USER"]
SF_PASSWORD  = os.environ["SNOWFLAKE_PASSWORD"]
SF_DATABASE  = os.getenv("SNOWFLAKE_DATABASE", "SENSOR_DATA")
SF_SCHEMA    = os.getenv("SNOWFLAKE_SCHEMA", "SILVER")
SF_WAREHOUSE = os.environ["SNOWFLAKE_WAREHOUSE"]


def fetch_postgres(conn, query: str) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        return [dict(row) for row in cur.fetchall()]


def upsert_customers(sf_cur, rows: list[dict]):
    sf_cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {SF_DATABASE}.{SF_SCHEMA}.DIM_CUSTOMERS (
            CUSTOMER_ID   NUMBER        PRIMARY KEY,
            CUSTOMER_NAME VARCHAR(100),
            REGION        VARCHAR(50)
        )
    """)
    sf_cur.execute(f"CREATE OR REPLACE TEMP TABLE tmp_customers LIKE {SF_DATABASE}.{SF_SCHEMA}.DIM_CUSTOMERS")
    sf_cur.executemany(
        "INSERT INTO tmp_customers (CUSTOMER_ID, CUSTOMER_NAME, REGION) VALUES (%s, %s, %s)",
        [(r["customer_id"], r["customer_name"], r["region"]) for r in rows],
    )
    sf_cur.execute(f"""
        MERGE INTO {SF_DATABASE}.{SF_SCHEMA}.DIM_CUSTOMERS AS target
        USING tmp_customers AS source
        ON target.CUSTOMER_ID = source.CUSTOMER_ID
        WHEN MATCHED THEN UPDATE SET
            CUSTOMER_NAME = source.CUSTOMER_NAME,
            REGION        = source.REGION
        WHEN NOT MATCHED THEN INSERT (CUSTOMER_ID, CUSTOMER_NAME, REGION)
            VALUES (source.CUSTOMER_ID, source.CUSTOMER_NAME, source.REGION)
    """)
    print(f"Upserted {len(rows)} rows into DIM_CUSTOMERS")


def upsert_sensors(sf_cur, rows: list[dict]):
    sf_cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {SF_DATABASE}.{SF_SCHEMA}.DIM_SENSORS (
            SENSOR_ID    NUMBER    PRIMARY KEY,
            SENSOR_TYPE  VARCHAR(50),
            LATITUDE     FLOAT,
            LONGITUDE    FLOAT,
            COUNTRY      VARCHAR(10),
            REGION       VARCHAR(50),
            CUSTOMER_ID  NUMBER
        )
    """)
    sf_cur.execute(f"CREATE OR REPLACE TEMP TABLE tmp_sensors LIKE {SF_DATABASE}.{SF_SCHEMA}.DIM_SENSORS")
    sf_cur.executemany(
        """INSERT INTO tmp_sensors
           (SENSOR_ID, SENSOR_TYPE, LATITUDE, LONGITUDE, COUNTRY, REGION, CUSTOMER_ID)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        [(r["sensor_id"], r["sensor_type"], r["latitude"], r["longitude"],
          r["country"], r["region"], r["customer_id"]) for r in rows],
    )
    sf_cur.execute(f"""
        MERGE INTO {SF_DATABASE}.{SF_SCHEMA}.DIM_SENSORS AS target
        USING tmp_sensors AS source
        ON target.SENSOR_ID = source.SENSOR_ID
        WHEN MATCHED THEN UPDATE SET
            SENSOR_TYPE = source.SENSOR_TYPE,
            LATITUDE    = source.LATITUDE,
            LONGITUDE   = source.LONGITUDE,
            COUNTRY     = source.COUNTRY,
            REGION      = source.REGION,
            CUSTOMER_ID = source.CUSTOMER_ID
        WHEN NOT MATCHED THEN INSERT
            (SENSOR_ID, SENSOR_TYPE, LATITUDE, LONGITUDE, COUNTRY, REGION, CUSTOMER_ID)
        VALUES
            (source.SENSOR_ID, source.SENSOR_TYPE, source.LATITUDE, source.LONGITUDE,
             source.COUNTRY, source.REGION, source.CUSTOMER_ID)
    """)
    print(f"Upserted {len(rows)} rows into DIM_SENSORS")


def main():
    pg_conn = psycopg2.connect(POSTGRES_DSN)
    sf_conn = snowflake.connector.connect(
        account=SF_ACCOUNT,
        user=SF_USER,
        password=SF_PASSWORD,
        warehouse=SF_WAREHOUSE,
        database=SF_DATABASE,
        schema=SF_SCHEMA,
    )

    try:
        customers = fetch_postgres(pg_conn, "SELECT customer_id, customer_name, region FROM customers")
        sensors   = fetch_postgres(pg_conn, "SELECT sensor_id, sensor_type, latitude, longitude, country, region, customer_id FROM dim_sensors")
        print(f"Fetched {len(customers)} customers, {len(sensors)} sensors from Postgres")

        with sf_conn.cursor() as sf_cur:
            upsert_customers(sf_cur, customers)
            upsert_sensors(sf_cur, sensors)

        sf_conn.commit()
        print("Sync complete")
    finally:
        pg_conn.close()
        sf_conn.close()


if __name__ == "__main__":
    main()
