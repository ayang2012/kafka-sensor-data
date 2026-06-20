import json
import logging
import os
import threading

import paho.mqtt.client as mqtt
from confluent_kafka import Producer

logger = logging.getLogger(__name__)

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "sensors")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")

_stop_event = threading.Event()


def _delivery_report(err, msg):
    if err:
        logger.error("Kafka delivery failed key=%s err=%s", msg.key(), err)


def _on_message(client, producer, msg):
    try:
        payload = json.loads(msg.payload.decode())
        key = str(payload.get("sensor_id", "")).encode()
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
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "enable.idempotence": True,
    })

    client = mqtt.Client(client_id="mqtt-kafka-bridge", userdata=producer)
    client.on_message = _on_message
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.subscribe(f"{MQTT_TOPIC_PREFIX}/+/data", qos=1)

    logger.info("Bridge running: MQTT %s:%s → Kafka %s", MQTT_HOST, MQTT_PORT, KAFKA_TOPIC)

    try:
        client.loop_forever()
    finally:
        producer.flush()
        client.disconnect()
