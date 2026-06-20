import pickle
import pytest
from pathlib import Path
from unittest.mock import patch

from sensor_pipeline.bootstrap import build_profiles, load_profiles, _validate_profile


MOCK_SENSORS = [
    {
        "id": i,
        "sensor": {"sensor_type": {"name": "SDS011"}},
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

    def test_missing_id(self):
        p = dict(MOCK_SENSORS[0])
        p["id"] = None
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
