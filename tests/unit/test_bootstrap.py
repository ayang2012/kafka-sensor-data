import pickle
import pytest
from pathlib import Path
from unittest.mock import patch

from sensor_pipeline.bootstrap import build_profiles, load_profiles, _validate_profile, _dedupe_by_sensor_id


MOCK_SENSORS = [
    {
        "id": 90000000000 + i,  # per-submission id — changes every fetch, not a stable identifier
        "timestamp": f"2026-06-22 18:{(i % 60):02d}:00",
        "sensor": {"id": i, "sensor_type": {"name": "SDS011"}},
        "location": {"latitude": str(48.0 + i * 0.1), "longitude": str(11.0 + i * 0.1), "country": "DE"},
        "sensordatavalues": [
            {"value_type": "P1", "value": "12.5"},
            {"value_type": "P2", "value": "8.3"},
        ],
    }
    for i in range(1200)
]


class TestValidateProfile:
    def test_valid_profile(self):
        assert _validate_profile(MOCK_SENSORS[0]) is True

    def test_missing_sensor_id(self):
        p = dict(MOCK_SENSORS[0])
        p["sensor"] = {"id": None, "sensor_type": {"name": "SDS011"}}
        assert _validate_profile(p) is False

    def test_out_of_bounds_lat(self):
        p = dict(MOCK_SENSORS[0])
        p["location"] = {"latitude": "999", "longitude": "11.0", "country": "DE"}
        assert _validate_profile(p) is False

    def test_out_of_bounds_lon(self):
        p = dict(MOCK_SENSORS[0])
        p["location"] = {"latitude": "48.0", "longitude": "999", "country": "DE"}
        assert _validate_profile(p) is False

    def test_no_sensordatavalues(self):
        p = dict(MOCK_SENSORS[0])
        p["sensordatavalues"] = []
        assert _validate_profile(p) is False

    def test_invalid_lat_string(self):
        p = dict(MOCK_SENSORS[0])
        p["location"] = {"latitude": "not_a_number", "longitude": "11.0", "country": "DE"}
        assert _validate_profile(p) is False


class TestDedupeBySensorId:
    def test_keeps_one_entry_per_sensor_id(self):
        duplicated = MOCK_SENSORS[:5] + [
            {**MOCK_SENSORS[0], "id": 99999999999, "timestamp": "2026-06-22 18:59:59"},
        ]
        result = _dedupe_by_sensor_id(duplicated)
        sensor_ids = [p["sensor"]["id"] for p in result]
        assert len(sensor_ids) == len(set(sensor_ids))

    def test_keeps_most_recent_timestamp(self):
        older = {**MOCK_SENSORS[0], "id": 1, "timestamp": "2026-06-22 18:00:00"}
        newer = {**MOCK_SENSORS[0], "id": 2, "timestamp": "2026-06-22 18:30:00"}
        result = _dedupe_by_sensor_id([older, newer])
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_skips_entries_with_no_sensor_id(self):
        bad = {**MOCK_SENSORS[0], "sensor": {"id": None}}
        result = _dedupe_by_sensor_id([bad])
        assert result == []


class TestBuildProfiles:
    def test_samples_correct_count(self, tmp_path):
        out = tmp_path / "profiles.pkl"
        with patch("sensor_pipeline.bootstrap.fetch_all", return_value=MOCK_SENSORS):
            profiles = build_profiles(output_path=out, sample_size=100)
        assert len(profiles) == 100

    def test_profiles_have_required_fields(self, tmp_path):
        out = tmp_path / "profiles.pkl"
        with patch("sensor_pipeline.bootstrap.fetch_all", return_value=MOCK_SENSORS):
            profiles = build_profiles(output_path=out, sample_size=10)
        for p in profiles:
            assert "id" in p
            assert "sensor_type" in p
            assert "latitude" in p
            assert "longitude" in p
            assert "country" in p
            assert "value_ranges" in p

    def test_id_comes_from_nested_sensor_id(self, tmp_path):
        # The stable identifier is sensor.id, not the top-level per-submission id.
        out = tmp_path / "profiles.pkl"
        with patch("sensor_pipeline.bootstrap.fetch_all", return_value=MOCK_SENSORS):
            profiles = build_profiles(output_path=out, sample_size=10)
        profile_ids = {p["id"] for p in profiles}
        nested_sensor_ids = {s["sensor"]["id"] for s in MOCK_SENSORS}
        assert profile_ids.issubset(nested_sensor_ids)

    def test_lat_lon_in_bounds(self, tmp_path):
        out = tmp_path / "profiles.pkl"
        with patch("sensor_pipeline.bootstrap.fetch_all", return_value=MOCK_SENSORS):
            profiles = build_profiles(output_path=out, sample_size=50)
        for p in profiles:
            assert -90 <= p["latitude"] <= 90
            assert -180 <= p["longitude"] <= 180

    def test_writes_pickle(self, tmp_path):
        out = tmp_path / "profiles.pkl"
        with patch("sensor_pipeline.bootstrap.fetch_all", return_value=MOCK_SENSORS):
            build_profiles(output_path=out, sample_size=10)
        assert out.exists()

    def test_caps_at_available(self, tmp_path):
        out = tmp_path / "profiles.pkl"
        small_set = MOCK_SENSORS[:5]
        with patch("sensor_pipeline.bootstrap.fetch_all", return_value=small_set):
            profiles = build_profiles(output_path=out, sample_size=1000)
        assert len(profiles) == 5


class TestLoadProfiles:
    def test_loads_pickled_profiles(self, tmp_path):
        out = tmp_path / "profiles.pkl"
        expected = [{"id": 1, "sensor_type": "SDS011"}]
        out.write_bytes(pickle.dumps(expected))
        assert load_profiles(out) == expected

    def test_raises_if_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_profiles(tmp_path / "nonexistent.pkl")
