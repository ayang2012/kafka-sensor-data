import json
import pytest
from unittest.mock import MagicMock, call

from sensor_pipeline.registry import get_customer, log_unregistered


def _make_conn(fetchone_result=None):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_result
    cur.__enter__ = lambda s: cur
    cur.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


class TestGetCustomer:
    def test_returns_dict_when_found(self):
        row = {"sensor_id": 42, "region": "Europe", "customer_id": 1, "customer_name": "AirWatch EU North"}
        conn, cur = _make_conn(fetchone_result=row)
        result = get_customer(42, conn)
        assert result == dict(row)

    def test_returns_none_when_not_found(self):
        conn, cur = _make_conn(fetchone_result=None)
        result = get_customer(99999, conn)
        assert result is None

    def test_queries_with_sensor_id(self):
        conn, cur = _make_conn(fetchone_result=None)
        get_customer(42, conn)
        args = cur.execute.call_args[0]
        assert 42 in args[1]


class TestLogUnregistered:
    def test_inserts_alert_log_row(self):
        conn, cur = _make_conn()
        payload = {"sensor_id": 99, "country": "XX"}
        log_unregistered(99, payload, conn)
        cur.execute.assert_called_once()
        args = cur.execute.call_args[0]
        assert args[1][0] == 99
        assert args[1][1] == "unregistered_device"
        assert json.loads(args[1][2]) == payload

    def test_commits_after_insert(self):
        conn, cur = _make_conn()
        log_unregistered(99, {}, conn)
        conn.commit.assert_called_once()
