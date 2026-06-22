{{ config(materialized='table') }}

-- Audit log of bronze rows excluded from silver.sensor_readings, with the
-- specific reason for exclusion. Nothing silently disappears between
-- bronze and silver — every dropped row is recorded here. Rebuilt in full
-- on each run since rejected rows are rare and lack reliable identifiers
-- to incrementally dedupe on.

SELECT
    reading_id,
    sensor_id,
    sensor_type,
    ingested_at AS raw_ingested_at,
    country,
    "values"    AS raw_values,
    CASE
        WHEN reading_id IS NULL THEN 'null_reading_id'
        WHEN TRY_TO_TIMESTAMP_TZ(ingested_at) IS NULL THEN 'unparseable_ingested_at'
        WHEN sensor_type IN ('', 'test') THEN 'invalid_sensor_type'
    END AS rejection_reason,
    CURRENT_TIMESTAMP() AS detected_at
FROM {{ source('bronze', 'sensor_readings') }}
WHERE reading_id IS NULL
   OR TRY_TO_TIMESTAMP_TZ(ingested_at) IS NULL
   OR sensor_type IN ('', 'test')
