import json
import logging
import os

from confluent_kafka import Consumer, KafkaException

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
GROUP_ID = os.getenv("KAFKA_CONSUMER_GROUP", "sensor-consumer-group")


def run():
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("Consumer subscribed to %s", TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            reading = json.loads(msg.value().decode())
            # TODO: write to Snowflake / Postgres / etc.
            logger.info(
                "sensor_id=%s location=%s,%s readings=%s",
                reading.get("id"),
                reading.get("location", {}).get("latitude"),
                reading.get("location", {}).get("longitude"),
                reading.get("sensordatavalues"),
            )
    finally:
        consumer.close()
