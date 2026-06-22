{{
    config(
        materialized='incremental',
        unique_key='reading_id',
        on_schema_change='sync_all_columns',
    )
}}

SELECT
    reading_id,
    sensor_id,
    sensor_type,
    TRY_TO_TIMESTAMP_TZ(ingested_at)                          AS ingested_at,
    latitude,
    longitude,
    country,
    TRY_PARSE_JSON("values"):P1::FLOAT                        AS pm25,
    TRY_PARSE_JSON("values"):P2::FLOAT                        AS pm10,
    TRY_PARSE_JSON("values"):temperature::FLOAT               AS temperature,
    TRY_PARSE_JSON("values"):humidity::FLOAT                  AS humidity,
    TRY_PARSE_JSON("values"):pressure::FLOAT                  AS pressure,
    TRY_PARSE_JSON("values"):pressure_at_sealevel::FLOAT      AS pressure_at_sealevel
FROM {{ source('bronze', 'sensor_readings') }}
WHERE reading_id IS NOT NULL
  AND TRY_TO_TIMESTAMP_TZ(ingested_at) IS NOT NULL
  AND sensor_type NOT IN ('', 'test')

{% if is_incremental() %}
-- Only process rows newer than the latest ingested_at already in silver.
-- Uses the previous hour's closed partition — bronze must have a _SUCCESS marker
-- written by consumer.py before this model runs.
AND TRY_TO_TIMESTAMP_TZ(ingested_at) > (
    SELECT MAX(ingested_at) FROM {{ this }}
)
{% endif %}

QUALIFY ROW_NUMBER() OVER (PARTITION BY reading_id ORDER BY ingested_at) = 1
