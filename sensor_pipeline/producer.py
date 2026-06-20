import json
import logging
import os
import time

from confluent_kafka import Producer

from .fetch import fetch_by_country

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
COUNTRY = os.getenv("SENSOR_COUNTRY", "DE")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))  # 5 min default


def _delivery_report(err, msg):
    if err:
        logger.error("Delivery failed for key %s: %s", msg.key(), err)


def run():
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    logger.info("Producer started. topic=%s country=%s", TOPIC, COUNTRY)

    while True:
        try:
            readings = fetch_by_country(COUNTRY)
            logger.info("Fetched %d readings", len(readings))

            for reading in readings:
                key = str(reading.get("id", "")).encode()
                value = json.dumps(reading).encode()
                producer.produce(TOPIC, key=key, value=value, callback=_delivery_report)

            producer.flush()
            logger.info("Flushed %d messages to Kafka", len(readings))
        except Exception as exc:
            logger.exception("Fetch/produce cycle failed: %s", exc)

        time.sleep(POLL_INTERVAL)
