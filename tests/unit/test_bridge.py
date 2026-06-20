import json
import pytest
from unittest.mock import MagicMock, patch, call

from sensor_pipeline.bridge import _on_message


def _make_mqtt_msg(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.payload = json.dumps(payload).encode()
    return msg


SAMPLE_READING = {
    "reading_id": "abc-123",
    "sensor_id": 42,
    "sensor_type": "SDS011",
    "ingested_at": "2026-06-20T10:00:00+00:00",
    "latitude": 48.137,
    "longitude": 11.575,
    "country": "DE",
    "values": {"P1": 12.5, "P2": 8.3},
}


class TestOnMessage:
    def test_produces_to_kafka(self):
        producer = MagicMock()
        msg = _make_mqtt_msg(SAMPLE_READING)
        _on_message(None, producer, msg)
        producer.produce.assert_called_once()

    def test_uses_sensor_id_as_key(self):
        producer = MagicMock()
        msg = _make_mqtt_msg(SAMPLE_READING)
        _on_message(None, producer, msg)
        _, kwargs = producer.produce.call_args
        assert kwargs["key"] == b"42"

    def test_payload_forwarded_verbatim(self):
        producer = MagicMock()
        msg = _make_mqtt_msg(SAMPLE_READING)
        _on_message(None, producer, msg)
        _, kwargs = producer.produce.call_args
        assert json.loads(kwargs["value"]) == SAMPLE_READING

    def test_polls_after_produce(self):
        producer = MagicMock()
        msg = _make_mqtt_msg(SAMPLE_READING)
        _on_message(None, producer, msg)
        producer.poll.assert_called_once_with(0)

    def test_invalid_json_does_not_raise(self):
        producer = MagicMock()
        msg = MagicMock()
        msg.payload = b"not valid json"
        _on_message(None, producer, msg)  # should not raise
        producer.produce.assert_not_called()

    def test_missing_sensor_id_uses_empty_key(self):
        producer = MagicMock()
        reading = dict(SAMPLE_READING)
        del reading["sensor_id"]
        msg = _make_mqtt_msg(reading)
        _on_message(None, producer, msg)
        _, kwargs = producer.produce.call_args
        assert kwargs["key"] == b""
