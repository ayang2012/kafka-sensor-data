{{
    config(
        materialized='incremental',
        unique_key=['hour', 'country', 'customer_name'],
        on_schema_change='sync_all_columns',
    )
}}

SELECT
    DATE_TRUNC('hour', f.ingested_at)      AS hour,
    COALESCE(ds.country, f.country)        AS country,
    COALESCE(dc.region, 'Unknown')         AS region,
    COALESCE(dc.customer_name, 'Unknown')  AS customer_name,
    COUNT(*)                               AS reading_count,
    ROUND(AVG(f.pm25), 3)                  AS avg_pm25,
    ROUND(MAX(f.pm25), 3)                  AS max_pm25,
    ROUND(MIN(f.pm25), 3)                  AS min_pm25,
    ROUND(AVG(f.pm10), 3)                  AS avg_pm10,
    ROUND(MAX(f.pm10), 3)                  AS max_pm10
FROM {{ ref('sensor_readings') }} f
LEFT JOIN {{ source('silver', 'dim_sensors') }} ds
    ON f.sensor_id = ds.sensor_id
LEFT JOIN {{ source('silver', 'dim_customers') }} dc
    ON ds.customer_id = dc.customer_id
WHERE f.pm25 IS NOT NULL

{% if is_incremental() %}
AND f.ingested_at > (
    SELECT DATEADD('hour', -1, MAX(hour)) FROM {{ this }}
)
{% endif %}

GROUP BY 1, 2, 3, 4
