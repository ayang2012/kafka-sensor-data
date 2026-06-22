import json
import pytest
from unittest.mock import MagicMock, call

from sensor_pipeline.registry import get_customer, log_unregistered, log_pressure_alert


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
    def test_inserts_alert_log_row_when_not_already_logged(self):
        conn, cur = _make_conn(fetchone_result=None)  # no existing row
        payload = {"sensor_id": 99, "country": "XX"}
        log_unregistered(99, payload, conn)
        # first execute = dedup check, second = insert
        assert cur.execute.call_count == 2
        insert_args = cur.execute.call_args_list[1][0]
        assert insert_args[1][0] == 99
        assert insert_args[1][1] == "unregistered_device"
        assert json.loads(insert_args[1][2]) == payload

    def test_skips_insert_when_already_logged(self):
        conn, cur = _make_conn(fetchone_result=(1,))  # existing row found
        log_unregistered(99, {}, conn)
        assert cur.execute.call_count == 1  # only the dedup check, no insert
        conn.commit.assert_not_called()

    def test_commits_after_insert(self):
        conn, cur = _make_conn(fetchone_result=None)
        log_unregistered(99, {}, conn)
        conn.commit.assert_called_once()


class TestLogPressureAlert:
    def test_inserts_with_reading_id(self):
        conn, cur = _make_conn()
        payload = {"pressure": 150000.0, "customer_name": "AirWatch EU North"}
        log_pressure_alert(42, "reading-abc", payload, conn)
        args = cur.execute.call_args[0]
        assert args[1][0] == 42
        assert args[1][1] == "reading-abc"
        assert args[1][2] == "pressure_threshold_exceeded"
        assert json.loads(args[1][3]) == payload

    def test_always_inserts_no_dedup_check(self):
        conn, cur = _make_conn()
        log_pressure_alert(42, "reading-1", {}, conn)
        log_pressure_alert(42, "reading-2", {}, conn)
        assert cur.execute.call_count == 2  # one insert each, no dedup lookups

    def test_commits_after_insert(self):
        conn, cur = _make_conn()
        log_pressure_alert(42, "reading-abc", {}, conn)
        conn.commit.assert_called_once()
