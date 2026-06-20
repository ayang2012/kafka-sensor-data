import json
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from sensor_pipeline.simulator import _generate_reading


PROFILE = {
    "id": 42,
    "sensor_type": "SDS011",
    "latitude": 48.137,
    "longitude": 11.575,
    "country": "DE",
    "value_ranges": {
        "P1": {"mean": 12.5, "std": 1.0},
        "P2": {"mean": 8.3, "std": 0.5},
        "temperature": {"mean": 22.0, "std": 2.0},
    },
}


class TestGenerateReading:
    def test_has_reading_id(self):
        r = _generate_reading(PROFILE)
        assert "reading_id" in r
        uuid.UUID(r["reading_id"])  # raises if not valid UUID

    def test_reading_id_is_unique(self):
        ids = {_generate_reading(PROFILE)["reading_id"] for _ in range(100)}
        assert len(ids) == 100

    def test_has_ingested_at(self):
        r = _generate_reading(PROFILE)
        assert "ingested_at" in r
        # must be parseable ISO datetime
        datetime.fromisoformat(r["ingested_at"])

    def test_ingested_at_not_in_future(self):
        r = _generate_reading(PROFILE)
        ts = datetime.fromisoformat(r["ingested_at"])
        assert ts <= datetime.now(timezone.utc)

    def test_sensor_id_matches_profile(self):
        r = _generate_reading(PROFILE)
        assert r["sensor_id"] == PROFILE["id"]

    def test_values_are_non_negative(self):
        for _ in range(50):
            r = _generate_reading(PROFILE)
            for v in r["values"].values():
                assert v >= 0.0

    def test_values_contain_expected_types(self):
        r = _generate_reading(PROFILE)
        assert "P1" in r["values"]
        assert "P2" in r["values"]
        assert "temperature" in r["values"]

    def test_lat_lon_preserved(self):
        r = _generate_reading(PROFILE)
        assert r["latitude"] == PROFILE["latitude"]
        assert r["longitude"] == PROFILE["longitude"]

    def test_country_preserved(self):
        r = _generate_reading(PROFILE)
        assert r["country"] == "DE"
