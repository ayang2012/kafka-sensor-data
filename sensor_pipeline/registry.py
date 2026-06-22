import json
import logging
import os

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://sensor:sensor@localhost:5432/sensordb")


def connect() -> psycopg2.extensions.connection:
    return psycopg2.connect(POSTGRES_DSN)


def get_customer(sensor_id: int, conn) -> dict | None:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ds.sensor_id, ds.region, ds.customer_id, c.customer_name
            FROM dim_sensors ds
            JOIN customers c USING (customer_id)
            WHERE ds.sensor_id = %s
            """,
            (sensor_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def log_unregistered(sensor_id: int, payload: dict, conn) -> None:
    """One row per sensor, ever — checked before insert since there's no
    DB-level uniqueness constraint (pressure alerts share this table and
    need to log every occurrence, not just the first)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM alert_log WHERE sensor_id = %s AND alert_type = %s",
            (sensor_id, "unregistered_device"),
        )
        if cur.fetchone():
            return
        cur.execute(
            """
            INSERT INTO alert_log (sensor_id, alert_type, payload)
            VALUES (%s, %s, %s)
            """,
            (sensor_id, "unregistered_device", json.dumps(payload)),
        )
    conn.commit()
    logger.warning("Unregistered device alert logged: sensor_id=%s", sensor_id)


def log_pressure_alert(sensor_id: int, reading_id: str, payload: dict, conn) -> None:
    """Every breach is its own row — pressure threshold events form an
    incident timeline, not a single deduped flag."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO alert_log (sensor_id, reading_id, alert_type, payload)
            VALUES (%s, %s, %s, %s)
            """,
            (sensor_id, reading_id, "pressure_threshold_exceeded", json.dumps(payload)),
        )
    conn.commit()
    logger.warning(
        "Pressure threshold alert logged: sensor_id=%s reading_id=%s",
        sensor_id, reading_id,
    )
