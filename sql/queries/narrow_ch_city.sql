-- narrow: точные целые единицы, среднее округлено до 0.0001 °C.
WITH grouped AS (
SELECT f.city_id, toDate(f.observed_at, 'UTC') AS observed_date,
       count() AS observations,
       sum(toUInt64(f.is_valid)) AS valid_observations,
       countIf(f.is_valid = 1 AND isNotNull(f.temp_centi)) AS temp_count,
       sumIf(ifNull(toInt64(f.temp_centi), 0), f.is_valid = 1) AS temp_sum_centi,
       countIf(f.is_valid = 1 AND isNotNull(f.precip_centi)) AS precip_count,
       sumIf(ifNull(toUInt64(f.precip_centi), 0), f.is_valid = 1) AS precip_sum_centi,
       min(if(f.is_valid = 1, f.temp_centi, NULL)) AS min_temp_centi,
       max(if(f.is_valid = 1, f.temp_centi, NULL)) AS max_temp_centi
FROM weather.weather_city AS f
WHERE f.city_id = 'moscow' AND f.observed_at >= '2024-06-01' AND f.observed_at < '2024-07-01'
GROUP BY city_id, observed_date
)
SELECT *,
       if(temp_count = 0, NULL,
          sign(temp_sum_centi) * intDiv(abs(temp_sum_centi) * 100 + intDiv(temp_count, 2),
                                       greatest(temp_count, 1))) AS avg_temp_1e4_c
FROM grouped
ORDER BY city_id, observed_date;
