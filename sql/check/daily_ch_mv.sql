-- daily: точные целые единицы, среднее округлено до 0.0001 °C.
WITH grouped AS (
SELECT f.city_id, f.observed_date AS observed_date,
       sum(f.observations) AS observations,
       sum(f.valid_observations) AS valid_observations,
       sum(f.temp_count) AS temp_count,
       sum(f.temp_sum_centi) AS temp_sum_centi,
       sum(f.precip_count) AS precip_count,
       sum(f.precip_sum_centi) AS precip_sum_centi,
       min(f.min_temp_centi) AS min_temp_centi,
       max(f.max_temp_centi) AS max_temp_centi
FROM weather.weather_daily AS f
WHERE TRUE
GROUP BY city_id, observed_date
)
SELECT *,
       if(temp_count = 0, NULL,
          sign(temp_sum_centi) * intDiv(abs(temp_sum_centi) * 100 + intDiv(temp_count, 2),
                                       greatest(temp_count, 1))) AS avg_temp_1e4_c
FROM grouped
ORDER BY city_id, observed_date;
