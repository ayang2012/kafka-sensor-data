import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

from sensor_pipeline.consumer import (
    _flush,
    _write_success_marker,
    _partition_prefix,
    backfill_missing_success_markers,
)


def _make_reading(sensor_id: int = 1) -> dict:
    return {
        "reading_id": str(uuid.uuid4()),
        "sensor_id": sensor_id,
        "sensor_type": "SDS011",
        "ingested_at": "2026-06-21T14:00:00+00:00",
        "latitude": 48.137,
        "longitude": 11.575,
        "country": "DE",
        "values": {"P1": 12.5, "P2": 8.3},
    }


class TestPartitionPrefix:
    def test_correct_format(self):
        dt = datetime(2026, 6, 21, 14, 0, 0, tzinfo=timezone.utc)
        prefix = _partition_prefix(dt)
        assert prefix == "sensor-readings/year=2026/month=06/day=21/hour=14"

    def test_zero_pads_single_digit_month_day_hour(self):
        dt = datetime(2026, 1, 5, 9, 0, 0, tzinfo=timezone.utc)
        prefix = _partition_prefix(dt)
        assert "month=01" in prefix
        assert "day=05" in prefix
        assert "hour=09" in prefix


class TestWriteSuccessMarker:
    def test_writes_to_correct_key(self):
        s3 = MagicMock()
        dt = datetime(2026, 6, 21, 14, 0, 0, tzinfo=timezone.utc)
        _write_success_marker(dt, s3)
        s3.put_object.assert_called_once()
        key = s3.put_object.call_args[1]["Key"]
        assert key == "sensor-readings/year=2026/month=06/day=21/hour=14/_SUCCESS"

    def test_writes_non_empty_body(self):
        s3 = MagicMock()
        dt = datetime(2026, 6, 21, 14, 0, 0, tzinfo=timezone.utc)
        _write_success_marker(dt, s3)
        body = s3.put_object.call_args[1]["Body"]
        assert body != b""
        assert b"2026-06-21" in body


class TestFlushWithHour:
    def test_flush_uses_provided_hour(self):
        s3 = MagicMock()
        dt = datetime(2026, 6, 21, 13, 0, 0, tzinfo=timezone.utc)
        _flush([_make_reading()], s3, flush_hour=dt)
        key = s3.put_object.call_args[1]["Key"]
        assert "hour=13" in key

    def test_flush_uses_current_hour_when_not_provided(self):
        s3 = MagicMock()
        now = datetime.now(timezone.utc)
        _flush([_make_reading()], s3)
        key = s3.put_object.call_args[1]["Key"]
        assert f"hour={now.hour:02d}" in key

    def test_empty_buffer_does_not_call_s3(self):
        s3 = MagicMock()
        _flush([], s3)
        s3.put_object.assert_not_called()


class TestBackfillMissingSuccessMarkers:
    def test_writes_marker_when_data_exists_but_no_success(self):
        s3 = MagicMock()
        # first call (checking for _SUCCESS) -> not found; second call (checking for any data) -> found
        s3.list_objects_v2.side_effect = lambda **kwargs: (
            {"KeyCount": 0} if kwargs["Prefix"].endswith("_SUCCESS") else {"KeyCount": 1}
        )
        backfill_missing_success_markers(s3, lookback_hours=2)
        assert s3.put_object.call_count == 2  # one per lookback hour, both missing markers

    def test_skips_hour_when_marker_already_exists(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {"KeyCount": 1}  # _SUCCESS check always finds something
        backfill_missing_success_markers(s3, lookback_hours=2)
        s3.put_object.assert_not_called()

    def test_skips_hour_with_no_data_at_all(self):
        s3 = MagicMock()
        s3.list_objects_v2.return_value = {"KeyCount": 0}  # nothing found for any prefix
        backfill_missing_success_markers(s3, lookback_hours=2)
        s3.put_object.assert_not_called()

    def test_never_touches_current_hour(self):
        s3 = MagicMock()
        s3.list_objects_v2.side_effect = lambda **kwargs: (
            {"KeyCount": 0} if kwargs["Prefix"].endswith("_SUCCESS") else {"KeyCount": 1}
        )
        backfill_missing_success_markers(s3, lookback_hours=3)
        current_hour_str = f"hour={datetime.now(timezone.utc).hour:02d}"
        written_keys = [c[1]["Key"] for c in s3.put_object.call_args_list]
        assert all(current_hour_str not in key for key in written_keys)
