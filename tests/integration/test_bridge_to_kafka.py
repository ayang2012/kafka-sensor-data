"""
Integration test: MQTT publish → bridge → assert message lands in Kafka.
Requires MQTT broker and Kafka broker running.
"""
import json
import os
import socket
import time
import threading
import uuid
import pytest
import paho.mqtt.client as mqtt
from confluent_kafka import Producer, Consumer, KafkaException

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "sensor-readings")
TIMEOUT = 15


def _available(host, port) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def services():
    if not _available(MQTT_HOST, MQTT_PORT):
        pytest.skip("MQTT broker not available")
    if not _available("localhost", 9092):
        pytest.skip("Kafka not available")


class TestBridgeToKafka:
    def test_message_flows_mqtt_to_kafka(self, services):
        reading_id = str(uuid.uuid4())
        payload = {
            "reading_id": reading_id,
            "sensor_id": 9999,
            "sensor_type": "SDS011",
            "ingested_at": "2026-06-20T10:00:00+00:00",
            "latitude": 48.1,
            "longitude": 11.5,
            "country": "DE",
            "values": {"P1": 10.0, "P2": 5.0},
        }

        # publish to MQTT (bridge should forward to Kafka)
        pub = mqtt.Client(client_id=f"test-pub-{reading_id[:8]}")
        pub.connect(MQTT_HOST, MQTT_PORT)
        pub.publish(f"sensors/9999/data", json.dumps(payload), qos=1)
        pub.disconnect()

        # consume from Kafka and look for our reading_id
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-consumer-{reading_id[:8]}",
            "auto.offset.reset": "earliest",
        })
        consumer.subscribe([KAFKA_TOPIC])

        found = False
        deadline = time.time() + TIMEOUT
        try:
            while time.time() < deadline:
                msg = consumer.poll(timeout=1.0)
                if msg is None or msg.error():
                    continue
                record = json.loads(msg.value().decode())
                if record.get("reading_id") == reading_id:
                    found = True
                    break
        finally:
            consumer.close()

        assert found, f"reading_id {reading_id} not found in Kafka within {TIMEOUT}s"

    def test_sensor_id_is_kafka_message_key(self, services):
        reading_id = str(uuid.uuid4())
        payload = {
            "reading_id": reading_id,
            "sensor_id": 8888,
            "values": {},
            "ingested_at": "2026-06-20T10:00:00+00:00",
            "latitude": 0.0, "longitude": 0.0, "country": "XX",
            "sensor_type": "test",
        }

        pub = mqtt.Client(client_id=f"test-key-{reading_id[:8]}")
        pub.connect(MQTT_HOST, MQTT_PORT)
        pub.publish("sensors/8888/data", json.dumps(payload), qos=1)
        pub.disconnect()

        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": f"test-key-consumer-{reading_id[:8]}",
            "auto.offset.reset": "earliest",
        })
        consumer.subscribe([KAFKA_TOPIC])

        deadline = time.time() + TIMEOUT
        try:
            while time.time() < deadline:
                msg = consumer.poll(timeout=1.0)
                if msg is None or msg.error():
                    continue
                record = json.loads(msg.value().decode())
                if record.get("reading_id") == reading_id:
                    assert msg.key() == b"8888"
                    break
        finally:
            consumer.close()
