import json
import logging
import os
import threading

import paho.mqtt.client as mqtt
from confluent_kafka import Producer

from .registry import connect, get_customer, log_unregistered

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")

_stop_event = threading.Event()
_seen_sensor_ids: set[int] = set()


def _delivery_report(err, msg):
    if err:
        logger.error("Kafka delivery failed key=%s err=%s", msg.key(), err)


def _on_message(client, userdata, msg):
    producer, pg_conn = userdata
    try:
        payload = json.loads(msg.payload.decode())
        sensor_id = payload.get("sensor_id")

        if sensor_id not in _seen_sensor_ids:
            customer = get_customer(sensor_id, pg_conn)
            if customer is None:
                log_unregistered(sensor_id, payload, pg_conn)
            else:
                logger.debug(
                    "Sensor %s registered to %s (%s)",
                    sensor_id,
                    customer["customer_name"],
                    customer["region"],
                )
            _seen_sensor_ids.add(sensor_id)

        key = str(sensor_id or "").encode()
        producer.produce(
            KAFKA_TOPIC,
            key=key,
            value=msg.payload,
            callback=_delivery_report,
        )
        producer.poll(0)
    except Exception:
        logger.exception("Failed to forward MQTT message to Kafka")


def run():
    pg_conn = connect()
    logger.info("Connected to Postgres registry")

    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "enable.idempotence": True,
    })

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="mqtt-kafka-bridge",
        userdata=(producer, pg_conn),
    )
    client.on_message = _on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/data", qos=1)

    logger.info("Bridge running: MQTT %s:%s → Kafka %s", MQTT_HOST, MQTT_PORT, KAFKA_TOPIC)

    try:
        client.loop_forever()
    finally:
        producer.flush()
        client.disconnect()
        pg_conn.close()
