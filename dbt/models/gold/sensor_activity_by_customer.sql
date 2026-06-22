{{
    config(
        materialized='incremental',
        unique_key=['day', 'customer_name', 'sensor_type'],
        on_schema_change='sync_all_columns',
    )
}}

SELECT
    DATE_TRUNC('day', f.ingested_at)       AS day,
    COALESCE(dc.customer_name, 'Unknown')  AS customer_name,
    COALESCE(dc.region, 'Unknown')         AS region,
    f.sensor_type,
    COUNT(DISTINCT f.sensor_id)            AS active_sensors,
    COUNT(*)                               AS total_readings,
    ROUND(COUNT(*) / COUNT(DISTINCT f.sensor_id), 1) AS avg_readings_per_sensor
FROM {{ ref('sensor_readings') }} f
LEFT JOIN {{ source('silver', 'dim_sensors') }} ds
    ON f.sensor_id = ds.sensor_id
LEFT JOIN {{ source('silver', 'dim_customers') }} dc
    ON ds.customer_id = dc.customer_id

{% if is_incremental() %}
WHERE f.ingested_at > (
    SELECT DATEADD('day', -1, MAX(day)) FROM {{ this }}
)
{% endif %}

GROUP BY 1, 2, 3, 4
