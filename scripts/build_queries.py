#!/usr/bin/env python3
"""Создание явных SQL-файлов; сами готовые запросы входят в сдачу."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PG_METRICS = """count(*) AS observations,
       count(*) FILTER (WHERE f.is_valid) AS valid_observations,
       count(f.temp_centi) FILTER (WHERE f.is_valid) AS temp_count,
       coalesce(sum(f.temp_centi) FILTER (WHERE f.is_valid), 0)::bigint AS temp_sum_centi,
       count(f.precip_centi) FILTER (WHERE f.is_valid) AS precip_count,
       coalesce(sum(f.precip_centi) FILTER (WHERE f.is_valid), 0)::bigint AS precip_sum_centi,
       min(f.temp_centi) FILTER (WHERE f.is_valid) AS min_temp_centi,
       max(f.temp_centi) FILTER (WHERE f.is_valid) AS max_temp_centi"""
CH_METRICS = """count() AS observations,
       sum(toUInt64(f.is_valid)) AS valid_observations,
       countIf(f.is_valid = 1 AND isNotNull(f.temp_centi)) AS temp_count,
       sumIf(ifNull(toInt64(f.temp_centi), 0), f.is_valid = 1) AS temp_sum_centi,
       countIf(f.is_valid = 1 AND isNotNull(f.precip_centi)) AS precip_count,
       sumIf(ifNull(toUInt64(f.precip_centi), 0), f.is_valid = 1) AS precip_sum_centi,
       min(if(f.is_valid = 1, f.temp_centi, NULL)) AS min_temp_centi,
       max(if(f.is_valid = 1, f.temp_centi, NULL)) AS max_temp_centi"""
MV_METRICS = """sum(f.observations) AS observations,
       sum(f.valid_observations) AS valid_observations,
       sum(f.temp_count) AS temp_count,
       sum(f.temp_sum_centi) AS temp_sum_centi,
       sum(f.precip_count) AS precip_count,
       sum(f.precip_sum_centi) AS precip_sum_centi,
       min(f.min_temp_centi) AS min_temp_centi,
       max(f.max_temp_centi) AS max_temp_centi"""
PG_AVG = """CASE WHEN temp_count = 0 THEN NULL
            ELSE sign(temp_sum_centi)::bigint *
                 ((abs(temp_sum_centi) * 100 + temp_count / 2) / temp_count)
       END AS avg_temp_1e4_c"""
CH_AVG = """if(temp_count = 0, NULL,
          sign(temp_sum_centi) * intDiv(abs(temp_sum_centi) * 100 + intDiv(temp_count, 2),
                                       greatest(temp_count, 1))) AS avg_temp_1e4_c"""


def make_query(engine: str, profile: str, table: str) -> str:
    pg = engine == "pg"
    mv = table == "weather_daily"
    instant = "f.observed_date" if mv else "f.observed_at"
    day = (
        "f.observed_date"
        if mv
        else (
            "(f.observed_at AT TIME ZONE 'UTC')::date"
            if pg
            else "toDate(f.observed_at, 'UTC')"
        )
    )
    month = (
        "date_trunc('month', f.observed_at AT TIME ZONE 'UTC')::date"
        if pg
        else f"toStartOfMonth({instant})"
    )
    if profile == "wide":
        keys = f"d.federal_district, {month} AS observed_month"
        key_names = "federal_district, observed_month"
        join = (
            "\nJOIN "
            + ("dim_city" if pg else "weather.dim_city")
            + " AS d ON f.city_id = d.city_id"
        )
        where = f"{instant} >= '2024-01-01' AND {instant} < '2024-10-01'"
    else:
        keys = f"f.city_id, {day} AS observed_date"
        key_names = "city_id, observed_date"
        join = ""
        where = (
            f"f.city_id = 'moscow' AND {instant} >= '2024-06-01' AND {instant} < '2024-07-01'"
            if profile == "narrow"
            else (
                f"{instant} >= '2024-06-01' AND {instant} < '2024-06-04'"
                if profile == "time_slice"
                else "TRUE"
            )
        )
    metrics = PG_METRICS if pg else MV_METRICS if mv else CH_METRICS
    source = table if pg else f"weather.{table}"
    avg = PG_AVG if pg else CH_AVG
    return (
        f"-- {profile}: точные целые единицы, среднее округлено до 0.0001 °C.\n"
        f"WITH grouped AS (\nSELECT {keys},\n       {metrics}\n"
        f"FROM {source} AS f{join}\nWHERE {where}\nGROUP BY {key_names}\n)\n"
        f"SELECT *,\n       {avg}\nFROM grouped\nORDER BY {key_names};\n"
    )


def main() -> None:
    for profile in ("narrow", "wide", "time_slice", "daily"):
        folder = ROOT / "sql" / ("check" if profile == "daily" else "queries")
        folder.mkdir(parents=True, exist_ok=True)
        for label, engine, table in [
            ("pg", "pg", "weather_hourly"),
            ("ch_city", "ch", "weather_city"),
            ("ch_time", "ch", "weather_time"),
            ("ch_mv", "ch", "weather_daily"),
        ]:
            (folder / f"{profile}_{label}.sql").write_text(
                make_query(engine, profile, table), encoding="utf-8"
            )


if __name__ == "__main__":
    main()
