import json
import pytest
from unittest.mock import MagicMock, patch

from sensor_pipeline.alert_consumer import _check_pressure, _on_message, send_alert


def _make_payload(pressure=None, sensor_id=42, reading_id="abc-123"):
    values = {}
    if pressure is not None:
        values["pressure"] = pressure
    return {
        "reading_id": reading_id,
        "sensor_id": sensor_id,
        "sensor_type": "BME280",
        "latitude": 48.1,
        "longitude": 11.5,
        "country": "DE",
        "values": values,
    }


class TestCheckPressure:
    def test_returns_pressure_when_over_threshold(self):
        payload = _make_payload(pressure=150000)
        assert _check_pressure(payload) == 150000

    def test_returns_none_when_under_threshold(self):
        payload = _make_payload(pressure=100000)
        assert _check_pressure(payload) is None

    def test_returns_none_when_missing(self):
        payload = _make_payload(pressure=None)
        assert _check_pressure(payload) is None

    def test_returns_none_for_non_numeric(self):
        payload = _make_payload(pressure="not-a-number")
        assert _check_pressure(payload) is None

    def test_boundary_exactly_at_threshold_not_alerted(self):
        payload = _make_payload(pressure=130000)
        assert _check_pressure(payload) is None


class TestSendAlert:
    def test_logs_when_no_webhook_configured(self, caplog):
        with patch("sensor_pipeline.alert_consumer.SLACK_WEBHOOK_URL", None):
            send_alert(42, 150000.0, {"customer_name": "AirWatch EU North", "region": "Europe"}, _make_payload(150000))
        assert "Pressure threshold exceeded" in caplog.text

    def test_posts_to_webhook_when_configured(self):
        with patch("sensor_pipeline.alert_consumer.SLACK_WEBHOOK_URL", "https://hooks.slack.test/x"), \
             patch("sensor_pipeline.alert_consumer.requests.post") as mock_post:
            send_alert(42, 150000.0, {"customer_name": "AirWatch EU North", "region": "Europe"}, _make_payload(150000))
            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert args[0] == "https://hooks.slack.test/x"

    def test_handles_unregistered_sensor_gracefully(self, caplog):
        with patch("sensor_pipeline.alert_consumer.SLACK_WEBHOOK_URL", None):
            send_alert(42, 150000.0, None, _make_payload(150000))
        assert "Unknown" in caplog.text


class TestOnMessage:
    def test_ignores_messages_under_threshold(self):
        pg_conn = MagicMock()
        payload = _make_payload(pressure=100000)
        with patch("sensor_pipeline.alert_consumer.get_customer") as mock_get, \
             patch("sensor_pipeline.alert_consumer.log_pressure_alert") as mock_log:
            _on_message(payload, pg_conn)
            mock_get.assert_not_called()
            mock_log.assert_not_called()

    def test_alerts_and_logs_when_over_threshold(self):
        pg_conn = MagicMock()
        payload = _make_payload(pressure=150000, sensor_id=42, reading_id="abc-123")
        customer = {"customer_id": 1, "customer_name": "AirWatch EU North", "region": "Europe"}
        with patch("sensor_pipeline.alert_consumer.get_customer", return_value=customer) as mock_get, \
             patch("sensor_pipeline.alert_consumer.log_pressure_alert") as mock_log, \
             patch("sensor_pipeline.alert_consumer.send_alert") as mock_send:
            _on_message(payload, pg_conn)
            mock_get.assert_called_once_with(42, pg_conn)
            mock_send.assert_called_once()
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            assert args[0] == 42
            assert args[1] == "abc-123"
            assert args[2]["customer_name"] == "AirWatch EU North"

    def test_logs_unknown_customer_when_unregistered(self):
        pg_conn = MagicMock()
        payload = _make_payload(pressure=150000, sensor_id=9999)
        with patch("sensor_pipeline.alert_consumer.get_customer", return_value=None), \
             patch("sensor_pipeline.alert_consumer.log_pressure_alert") as mock_log, \
             patch("sensor_pipeline.alert_consumer.send_alert"):
            _on_message(payload, pg_conn)
            args = mock_log.call_args[0]
            assert args[2]["customer_name"] == "Unknown"
