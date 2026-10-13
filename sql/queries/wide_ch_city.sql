-- wide: точные целые единицы, среднее округлено до 0.0001 °C.
WITH grouped AS (
SELECT d.federal_district, toStartOfMonth(f.observed_at) AS observed_month,
       count() AS observations,
       sum(toUInt64(f.is_valid)) AS valid_observations,
       countIf(f.is_valid = 1 AND isNotNull(f.temp_centi)) AS temp_count,
       sumIf(ifNull(toInt64(f.temp_centi), 0), f.is_valid = 1) AS temp_sum_centi,
       countIf(f.is_valid = 1 AND isNotNull(f.precip_centi)) AS precip_count,
       sumIf(ifNull(toUInt64(f.precip_centi), 0), f.is_valid = 1) AS precip_sum_centi,
       min(if(f.is_valid = 1, f.temp_centi, NULL)) AS min_temp_centi,
       max(if(f.is_valid = 1, f.temp_centi, NULL)) AS max_temp_centi
FROM weather.weather_city AS f
JOIN weather.dim_city AS d ON f.city_id = d.city_id
WHERE f.observed_at >= '2024-01-01' AND f.observed_at < '2024-10-01'
GROUP BY federal_district, observed_month
)
SELECT *,
       if(temp_count = 0, NULL,
          sign(temp_sum_centi) * intDiv(abs(temp_sum_centi) * 100 + intDiv(temp_count, 2),
                                       greatest(temp_count, 1))) AS avg_temp_1e4_c
FROM grouped
ORDER BY federal_district, observed_month;
