{{
    config(
        materialized='incremental',
        unique_key=['day', 'region', 'sensor_type', 'customer_name'],
        on_schema_change='sync_all_columns',
    )
}}

SELECT
    DATE_TRUNC('day', f.ingested_at)       AS day,
    COALESCE(dc.region, 'Unknown')         AS region,
    COALESCE(dc.customer_name, 'Unknown')  AS customer_name,
    f.sensor_type,
    COUNT(*)                               AS reading_count,
    ROUND(AVG(f.temperature), 3)           AS avg_temperature,
    ROUND(MAX(f.temperature), 3)           AS max_temperature,
    ROUND(MIN(f.temperature), 3)           AS min_temperature,
    ROUND(AVG(f.humidity), 3)              AS avg_humidity,
    ROUND(AVG(f.pressure), 3)             AS avg_pressure
FROM {{ ref('sensor_readings') }} f
LEFT JOIN {{ source('silver', 'dim_sensors') }} ds
    ON f.sensor_id = ds.sensor_id
LEFT JOIN {{ source('silver', 'dim_customers') }} dc
    ON ds.customer_id = dc.customer_id
WHERE f.temperature IS NOT NULL

{% if is_incremental() %}
AND f.ingested_at > (
    SELECT DATEADD('day', -1, MAX(day)) FROM {{ this }}
)
{% endif %}

GROUP BY 1, 2, 3, 4
