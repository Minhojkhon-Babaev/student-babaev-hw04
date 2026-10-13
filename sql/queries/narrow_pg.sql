-- narrow: точные целые единицы, среднее округлено до 0.0001 °C.
WITH grouped AS (
SELECT f.city_id, (f.observed_at AT TIME ZONE 'UTC')::date AS observed_date,
       count(*) AS observations,
       count(*) FILTER (WHERE f.is_valid) AS valid_observations,
       count(f.temp_centi) FILTER (WHERE f.is_valid) AS temp_count,
       coalesce(sum(f.temp_centi) FILTER (WHERE f.is_valid), 0)::bigint AS temp_sum_centi,
       count(f.precip_centi) FILTER (WHERE f.is_valid) AS precip_count,
       coalesce(sum(f.precip_centi) FILTER (WHERE f.is_valid), 0)::bigint AS precip_sum_centi,
       min(f.temp_centi) FILTER (WHERE f.is_valid) AS min_temp_centi,
       max(f.temp_centi) FILTER (WHERE f.is_valid) AS max_temp_centi
FROM weather_hourly AS f
WHERE f.city_id = 'moscow' AND f.observed_at >= '2024-06-01' AND f.observed_at < '2024-07-01'
GROUP BY city_id, observed_date
)
SELECT *,
       CASE WHEN temp_count = 0 THEN NULL
            ELSE sign(temp_sum_centi)::bigint *
                 ((abs(temp_sum_centi) * 100 + temp_count / 2) / temp_count)
       END AS avg_temp_1e4_c
FROM grouped
ORDER BY city_id, observed_date;
