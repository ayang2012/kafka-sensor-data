import json
import pytest
from unittest.mock import MagicMock, patch

from sensor_pipeline.producer import _on_message
import sensor_pipeline.producer as producer_mod


def _make_mqtt_msg(payload: dict) -> MagicMock:
    msg = MagicMock()
    msg.payload = json.dumps(payload).encode()
    return msg


def _make_userdata(producer=None, registered=True):
    """Return (producer, pg_conn) userdata tuple with registry mocked."""
    producer = producer or MagicMock()
    pg_conn = MagicMock()
    customer = {"sensor_id": 42, "customer_id": 1, "customer_name": "AirWatch EU North", "region": "Europe"}
    with patch("sensor_pipeline.producer.get_customer", return_value=customer if registered else None), \
         patch("sensor_pipeline.producer.log_unregistered"):
        pass
    return producer, pg_conn


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
    def setup_method(self):
        producer_mod._seen_sensor_ids.clear()

    def _call(self, payload=None, registered=True):
        producer = MagicMock()
        pg_conn = MagicMock()
        customer = {"sensor_id": 42, "customer_id": 1, "customer_name": "AirWatch EU North", "region": "Europe"}
        msg = _make_mqtt_msg(payload or SAMPLE_READING)
        with patch("sensor_pipeline.producer.get_customer", return_value=customer if registered else None) as mock_get, \
             patch("sensor_pipeline.producer.log_unregistered") as mock_log:
            _on_message(None, (producer, pg_conn), msg)
            return producer, pg_conn, mock_get, mock_log

    def test_produces_to_kafka(self):
        producer, *_ = self._call()
        producer.produce.assert_called_once()

    def test_uses_sensor_id_as_key(self):
        producer, *_ = self._call()
        _, kwargs = producer.produce.call_args
        assert kwargs["key"] == b"42"

    def test_payload_forwarded_verbatim(self):
        producer, *_ = self._call()
        _, kwargs = producer.produce.call_args
        assert json.loads(kwargs["value"]) == SAMPLE_READING

    def test_polls_after_produce(self):
        producer, *_ = self._call()
        producer.poll.assert_called_once_with(0)

    def test_invalid_json_does_not_raise(self):
        producer = MagicMock()
        pg_conn = MagicMock()
        msg = MagicMock()
        msg.payload = b"not valid json"
        _on_message(None, (producer, pg_conn), msg)
        producer.produce.assert_not_called()

    def test_missing_sensor_id_uses_empty_key(self):
        reading = dict(SAMPLE_READING)
        del reading["sensor_id"]
        producer, *_ = self._call(payload=reading)
        _, kwargs = producer.produce.call_args
        assert kwargs["key"] == b""

    def test_registry_lookup_only_once_per_sensor(self):
        producer = MagicMock()
        pg_conn = MagicMock()
        customer = {"sensor_id": 42, "customer_id": 1, "customer_name": "AirWatch EU North", "region": "Europe"}
        msg = _make_mqtt_msg(SAMPLE_READING)
        with patch("sensor_pipeline.producer.get_customer", return_value=customer) as mock_get, \
             patch("sensor_pipeline.producer.log_unregistered"):
            _on_message(None, (producer, pg_conn), msg)
            _on_message(None, (producer, pg_conn), msg)
        assert mock_get.call_count == 1

    def test_unregistered_sensor_logs_alert(self):
        _, _, _, mock_log = self._call(registered=False)
        mock_log.assert_called_once()
        args = mock_log.call_args[0]
        assert args[0] == 42
