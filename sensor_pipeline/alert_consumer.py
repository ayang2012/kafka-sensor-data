import json
import logging
import os

import requests
from confluent_kafka import Consumer, KafkaException

from .registry import connect, get_customer, log_pressure_alert

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
KAFKA_GROUP_ID = os.getenv("ALERT_CONSUMER_GROUP", "alert-engine")
PRESSURE_THRESHOLD_PA = float(os.getenv("PRESSURE_THRESHOLD_PA", "130000"))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")


def _check_pressure(payload: dict) -> float | None:
    values = payload.get("values", {})
    pressure = values.get("pressure")
    if pressure is None:
        return None
    try:
        pressure = float(pressure)
    except (TypeError, ValueError):
        return None
    return pressure if pressure > PRESSURE_THRESHOLD_PA else None


def send_alert(sensor_id: int, pressure: float, customer: dict | None, payload: dict) -> None:
    customer_name = customer["customer_name"] if customer else "Unknown"
    region = customer["region"] if customer else "Unknown"
    message = (
        f"[ALERT] Pressure threshold exceeded: sensor_id={sensor_id} "
        f"pressure={pressure:.1f}Pa (limit={PRESSURE_THRESHOLD_PA:.0f}Pa) "
        f"customer={customer_name} region={region} "
        f"location=({payload.get('latitude')}, {payload.get('longitude')})"
    )

    if SLACK_WEBHOOK_URL:
        try:
            requests.post(SLACK_WEBHOOK_URL, json={"text": message}, timeout=5)
        except requests.RequestException:
            logger.exception("Failed to deliver Slack alert for sensor_id=%s", sensor_id)
    else:
        logger.warning(message)


def _on_message(payload: dict, pg_conn) -> None:
    pressure = _check_pressure(payload)
    if pressure is None:
        return

    sensor_id = payload.get("sensor_id")
    reading_id = payload.get("reading_id")
    customer = get_customer(sensor_id, pg_conn)

    send_alert(sensor_id, pressure, customer, payload)

    alert_payload = {
        "pressure": pressure,
        "threshold": PRESSURE_THRESHOLD_PA,
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "customer_id": customer["customer_id"] if customer else None,
        "customer_name": customer["customer_name"] if customer else "Unknown",
        "region": customer["region"] if customer else "Unknown",
    }
    log_pressure_alert(sensor_id, reading_id, alert_payload, pg_conn)


def run():
    pg_conn = connect()
    logger.info("Connected to Postgres registry")

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": KAFKA_GROUP_ID,
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
    })
    consumer.subscribe([KAFKA_TOPIC])
    logger.info(
        "Alert engine running: watching %s for pressure > %.0fPa",
        KAFKA_TOPIC, PRESSURE_THRESHOLD_PA,
    )

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            try:
                payload = json.loads(msg.value().decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.exception("Failed to decode message")
                continue
            try:
                _on_message(payload, pg_conn)
            except Exception:
                logger.exception("Failed to process message for alerting")
    finally:
        consumer.close()
        pg_conn.close()
