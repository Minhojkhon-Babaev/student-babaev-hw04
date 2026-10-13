#!/usr/bin/env python3
"""Сохранить несколько коротких выполненных запросов для читаемых снимков."""
from __future__ import annotations

from db import ROOT, ch_rows, connect_pg, pg_rows, save_json
from run import normalize


def main() -> None:
    directory = ROOT / "evidence/main"
    connection = connect_pg()
    pg_query = """SELECT count(*) AS observations,
       count(DISTINCT (city_id, observed_at)) AS unique_business_keys
FROM weather_hourly;"""
    ch_query = """SELECT count() AS observations,
       uniqExact(tuple(city_id, observed_at)) AS unique_business_keys
FROM weather.weather_city;"""
    mv_query = """SELECT city_id, observed_date,
       sum(observations) AS observations,
       sum(temp_count) AS temp_count,
       sum(temp_sum_centi) AS temp_sum_centi,
       sum(precip_sum_centi) AS precip_sum_centi,
       min(min_temp_centi) AS min_temp_centi,
       max(max_temp_centi) AS max_temp_centi
FROM weather.weather_daily
WHERE city_id = 'moscow' AND observed_date = '2024-10-05'
GROUP BY city_id, observed_date;"""
    save_json(
        directory,
        "live_queries.json",
        {
            "pg": {
                "sql": pg_query,
                "data": normalize(pg_rows(connection, pg_query)),
            },
            "ch": {"sql": ch_query, "data": ch_rows(ch_query)},
            "mv": {"sql": mv_query, "data": ch_rows(mv_query)},
        },
    )
    connection.close()
    print("PASS live read-only queries captured")


if __name__ == "__main__":
    main()
