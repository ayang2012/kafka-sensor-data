import logging
import pickle
import random
from pathlib import Path

from .fetch import fetch_all

logger = logging.getLogger(__name__)

PROFILES_PATH = Path("sensor_profiles.pkl")
SAMPLE_SIZE = 1000


def _validate_profile(p: dict) -> bool:
    try:
        loc = p.get("location", {})
        lat = float(loc.get("latitude", 0))
        lon = float(loc.get("longitude", 0))
        has_values = bool(p.get("sensordatavalues"))
        in_bounds = -90 <= lat <= 90 and -180 <= lon <= 180
        # NOTE: the API's top-level "id" is a per-submission/reading ID that
        # changes on every fetch — it is NOT a stable device identifier.
        # The stable identity is the nested sensor.id. Confirmed empirically:
        # two fetches ~5 min apart matched 98.9% of devices on sensor.id while
        # the top-level id never matched at all across fetches.
        return p.get("sensor", {}).get("id") is not None and has_values and in_bounds
    except (TypeError, ValueError):
        return False


def _dedupe_by_sensor_id(raw: list[dict]) -> list[dict]:
    """A single snapshot occasionally contains two near-simultaneous
    submissions from the same physical sensor (observed: 70/18174 sensors
    in one live fetch). Keep only the most recent per sensor.id so it's
    safe to use as a primary key downstream."""
    latest: dict[int, dict] = {}
    for p in raw:
        sid = p.get("sensor", {}).get("id")
        if sid is None:
            continue
        existing = latest.get(sid)
        if existing is None or p.get("timestamp", "") > existing.get("timestamp", ""):
            latest[sid] = p
    return list(latest.values())


def build_profiles(output_path: Path = PROFILES_PATH, sample_size: int = SAMPLE_SIZE) -> list[dict]:
    logger.info("Fetching snapshot from Sensor.Community...")
    raw = fetch_all()
    logger.info("Fetched %d total sensors", len(raw))

    deduped = _dedupe_by_sensor_id(raw)
    valid = [p for p in deduped if _validate_profile(p)]
    logger.info("%d sensors passed validation", len(valid))

    sample = random.sample(valid, min(sample_size, len(valid)))

    profiles = []
    for p in sample:
        profiles.append({
            "id": p["sensor"]["id"],
            "sensor_type": p.get("sensor", {}).get("sensor_type", {}).get("name", "unknown"),
            "latitude": float(p["location"]["latitude"]),
            "longitude": float(p["location"]["longitude"]),
            "country": p["location"].get("country", ""),
            "value_ranges": _extract_value_ranges(p["sensordatavalues"]),
        })

    output_path.write_bytes(pickle.dumps(profiles))
    logger.info("Wrote %d sensor profiles to %s", len(profiles), output_path)
    return profiles


def _extract_value_ranges(sensordatavalues: list[dict]) -> dict[str, dict]:
    ranges = {}
    for entry in sensordatavalues:
        name = entry.get("value_type")
        try:
            val = float(entry.get("value", 0))
        except (TypeError, ValueError):
            continue
        if name:
            ranges[name] = {"mean": val, "std": max(val * 0.05, 0.5)}
    return ranges


def load_profiles(path: Path = PROFILES_PATH) -> list[dict]:
    if not path.exists():
        raise FileNotFoundError(f"No profiles found at {path}. Run bootstrap first.")
    return pickle.loads(path.read_bytes())
