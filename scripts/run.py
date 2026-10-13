#!/usr/bin/env python3
"""Загрузка, независимый контроль, замеры и отдельный опыт повторной доставки."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import platform
import random
import statistics
import time
from pathlib import Path

import psycopg2

from db import (
    ROOT,
    CH_SETTINGS,
    ch_execute,
    ch_request,
    ch_rows,
    connect_pg,
    execute_file,
    pg_rows,
    save_json,
)
from generate import FIELDS, cities, generate, read_rows

LABELS = ("pg", "ch_city", "ch_time", "ch_mv")
METRIC_NAMES = [
    "observations",
    "valid_observations",
    "temp_count",
    "temp_sum_centi",
    "precip_count",
    "precip_sum_centi",
    "min_temp_centi",
    "max_temp_centi",
    "avg_temp_1e4_c",
]


def normalize(rows: list[list]) -> list[list]:
    return [
        [
            (
                value.isoformat()
                if isinstance(value, (dt.date, dt.datetime))
                else value
            )
            for value in row
        ]
        for row in rows
    ]


def fingerprint(rows: list[list]) -> str:
    digest = hashlib.sha256()
    for row in normalize(rows):
        digest.update(
            (
                json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            ).encode()
        )
    return digest.hexdigest()


def independent(rows: list[list], profile: str, city_count: int) -> list[list]:
    """Отдельный Python-расчёт из CSV: ни SQL, ни чтения витрины."""
    districts = {row[0]: row[2] for row in cities(city_count)}
    groups = {}
    for city, timestamp, temperature, rain, valid, _ in rows:
        day = timestamp[:10]
        if profile == "narrow" and not (
            city == "moscow" and "2024-06-01" <= day < "2024-07-01"
        ):
            continue
        if profile == "wide" and not ("2024-01-01" <= day < "2024-10-01"):
            continue
        if profile == "time_slice" and not (
            "2024-06-01" <= day < "2024-06-04"
        ):
            continue
        key = (
            (districts[city], day[:7] + "-01")
            if profile == "wide"
            else (city, day)
        )
        state = groups.setdefault(key, [0, 0, 0, 0, 0, 0, None, None])
        state[0] += 1
        state[1] += valid
        if valid and temperature is not None:
            state[2] += 1
            state[3] += temperature
            state[6] = (
                temperature if state[6] is None else min(state[6], temperature)
            )
            state[7] = (
                temperature if state[7] is None else max(state[7], temperature)
            )
        if valid and rain is not None:
            state[4] += 1
            state[5] += rain
    result = []
    for key, state in sorted(groups.items()):
        count, total = state[2:4]
        average = (
            None
            if count == 0
            else (1 if total >= 0 else -1)
            * ((abs(total) * 100 + count // 2) // count)
        )
        result.append([*key, *state, average])
    return result


def load_csv(connection, name: str) -> dict:
    path = ROOT / "data/generated" / f"{name}.csv"
    started = time.perf_counter()
    with path.open(encoding="utf-8") as handle, connection.cursor() as cursor:
        cursor.copy_expert(
            "COPY weather_hourly FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '')",
            handle,
        )
    pg_ms = (time.perf_counter() - started) * 1000
    rows = read_rows([name])
    buffer = io.StringIO()
    writer = csv.writer(
        buffer, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE
    )
    writer.writerow(FIELDS)
    writer.writerows(
        [[r"\N" if value is None else value for value in row] for row in rows]
    )
    data = buffer.getvalue().encode()
    times = {}
    for table in ("weather_city", "weather_time"):
        _, elapsed = ch_request(
            f"INSERT INTO weather.{table} FORMAT TSVWithNames",
            data=data,
            formatted=False,
        )
        times[table] = elapsed
    return {
        "batch": name,
        "rows": len(rows),
        "pg_copy_wall_ms": pg_ms,
        "ch_insert_wall_ms": times,
        "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def sql(profile: str, label: str) -> str:
    folder = "check" if profile == "daily" else "queries"
    return (ROOT / "sql" / folder / f"{profile}_{label}.sql").read_text(
        encoding="utf-8"
    )


def result_rows(connection, profile: str, label: str) -> list[list]:
    query = sql(profile, label)
    return normalize(
        pg_rows(connection, query) if label == "pg" else ch_rows(query)
    )


def assert_equal(
    expected: list[list], actual: list[list], context: str
) -> None:
    if actual != expected:
        first = next(
            (
                (left, right)
                for left, right in zip(expected, actual)
                if left != right
            ),
            None,
        )
        raise AssertionError(
            f"{context}: expected {len(expected)} rows, got {len(actual)}; mismatch={first}"
        )


def raw_transfer(connection, expected: list[list]) -> dict:
    expected = sorted(expected, key=lambda row: (row[0], row[1]))
    if len({(row[0], row[1]) for row in expected}) != len(expected):
        raise AssertionError("Повтор бизнес-ключа в источнике")
    pg = normalize(
        pg_rows(
            connection,
            """
        SELECT city_id, to_char(observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
               temp_centi, precip_centi, is_valid::int, batch_id
        FROM weather_hourly ORDER BY city_id, observed_at
    """,
        )
    )
    baseline = fingerprint(expected)
    result = {
        "source_rows": len(expected),
        "source_sha256": baseline,
        "unique_business_key": True,
    }
    assert_equal(expected, pg, "Полный перенос в PG")
    result["pg"] = {
        "rows": len(pg),
        "sha256": fingerprint(pg),
        "equal_all_fields": True,
    }
    for label, table in (
        ("ch_city", "weather_city"),
        ("ch_time", "weather_time"),
    ):
        actual = ch_rows(
            f"""
            SELECT city_id, toString(observed_at, 'UTC'), temp_centi, precip_centi, is_valid, batch_id
            FROM weather.{table} ORDER BY city_id, observed_at
        """
        )
        assert_equal(expected, actual, f"Полный перенос {label}")
        result[label] = {
            "rows": len(actual),
            "sha256": fingerprint(actual),
            "equal_all_fields": True,
        }
    return result


def validate(
    connection, directory: Path, stage: str, names: list[str], city_count: int
) -> dict:
    source = read_rows(names)
    transfer = raw_transfer(connection, source)
    comparisons = {}
    for profile in ("daily", "narrow", "wide", "time_slice"):
        expected = independent(source, profile, city_count)
        data = {
            "source": {"rows": len(expected), "sha256": fingerprint(expected)}
        }
        for label in LABELS:
            actual = result_rows(connection, profile, label)
            assert_equal(expected, actual, f"{stage}/{profile}/{label}")
            data[label] = {
                "rows": len(actual),
                "sha256": fingerprint(actual),
                "equal_all_keys_metrics": True,
            }
            if stage == "after_batch_2":
                save_json(
                    directory,
                    f"results/{profile}_{label}.json",
                    {
                        "sql": sql(profile, label),
                        "columns": (
                            ["federal_district", "observed_month"]
                            if profile == "wide"
                            else ["city_id", "observed_date"]
                        )
                        + METRIC_NAMES,
                        "data": actual,
                    },
                )
        comparisons[profile] = data
    daily = result_rows(connection, "daily", "ch_mv")
    increment_day = json.loads(
        (ROOT / "data/generated/manifest.json").read_text()
    )["increment_day"]
    focus = [
        row for row in daily if row[0] == "moscow" and row[1] >= increment_day
    ]
    partial_rows = ch_rows("SELECT count() FROM weather.weather_daily")[0][0]
    payload = {
        "stage": stage,
        "transfer": transfer,
        "comparisons": comparisons,
        "physical_daily_rows": partial_rows,
        "logical_daily_rows": len(daily),
        "increment_moscow": focus,
        "null_or_invalid_only_days": [
            row for row in daily if row[2] and row[4] == 0
        ],
        "all_checks_passed": True,
    }
    save_json(directory, f"checks/{stage}.json", payload)
    print(
        f"PASS {stage}: {len(source)} facts; {len(daily)} daily groups; full source and four SQL variants equal",
        flush=True,
    )
    return payload


def pg_explain(connection, query: str) -> dict:
    return pg_rows(
        connection,
        "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF, FORMAT JSON)\n"
        + query,
    )[0][0][0]


def scans(plan: dict) -> int:
    own = 0
    if (
        "Scan" in plan.get("Node Type", "")
        and plan.get("Relation Name") == "weather_hourly"
    ):
        own = (
            plan.get("Actual Rows", 0) + plan.get("Rows Removed by Filter", 0)
        ) * plan.get("Actual Loops", 1)
    return own + sum(scans(child) for child in plan.get("Plans", []))


def background(connection) -> dict:
    return {
        "ch_merges": ch_rows(
            "SELECT count() FROM system.merges WHERE database = 'weather'"
        )[0][0],
        "pg_active_autovacuum": pg_rows(
            connection,
            "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'autovacuum worker'",
        )[0][0],
    }


def benchmark(
    connection, directory: Path, repeats: int, city_count: int
) -> list[dict]:
    source = read_rows(["history", "batch_1", "batch_2"])
    records = []
    warmups = []
    randomizer = random.Random(20261013)
    before = background(connection)
    for profile in ("narrow", "wide", "time_slice"):
        expected = independent(source, profile, city_count)
        for label in LABELS:
            started = time.perf_counter_ns()
            actual = result_rows(connection, profile, label)
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            assert_equal(expected, actual, f"warmup {profile}/{label}")
            warmups.append(
                {
                    "profile": profile,
                    "variant": label,
                    "wall_ms_discarded": elapsed,
                }
            )
        for repeat in range(1, repeats + 1):
            order = list(LABELS)
            randomizer.shuffle(order)
            for label in order:
                query = sql(profile, label)
                query_id = f"hw04_{profile}_{label}_{repeat}"
                if label == "pg":
                    started = time.perf_counter_ns()
                    actual = normalize(pg_rows(connection, query))
                    wall = (time.perf_counter_ns() - started) / 1_000_000
                    plan = pg_explain(connection, query)
                    root = plan["Plan"]
                    record = {
                        "profile": profile,
                        "variant": label,
                        "repeat": repeat,
                        "wall_ms": wall,
                        "server_ms": plan["Execution Time"],
                        "planning_ms": plan["Planning Time"],
                        "read_rows": scans(root),
                        "read_bytes": None,
                        "pg_shared_hit_blocks": root.get(
                            "Shared Hit Blocks", 0
                        ),
                        "pg_shared_read_blocks": root.get(
                            "Shared Read Blocks", 0
                        ),
                        "pg_temp_read_blocks": root.get("Temp Read Blocks", 0),
                        "pg_temp_written_blocks": root.get(
                            "Temp Written Blocks", 0
                        ),
                        "query_id": query_id,
                    }
                    save_json(
                        directory, f"plans/{profile}_pg_{repeat}.json", plan
                    )
                    if repeat == repeats:
                        text_plan = pg_rows(
                            connection,
                            "EXPLAIN (ANALYZE, BUFFERS, SETTINGS, TIMING OFF)\n"
                            + query,
                        )
                        (directory / f"plans/{profile}_pg.txt").write_text(
                            query
                            + "\n"
                            + "\n".join(row[0] for row in text_plan)
                            + "\n"
                        )
                else:
                    response, wall = ch_request(query, query_id=query_id)
                    actual = response["data"]
                    stats = response["statistics"]
                    record = {
                        "profile": profile,
                        "variant": label,
                        "repeat": repeat,
                        "wall_ms": wall,
                        "server_ms": None,
                        "statistics_elapsed_ms": stats["elapsed"] * 1000,
                        "read_rows": stats["rows_read"],
                        "read_bytes": stats["bytes_read"],
                        "query_id": query_id,
                    }
                    if repeat == repeats:
                        plan = ch_rows("EXPLAIN indexes = 1\n" + query)
                        pipeline = ch_rows("EXPLAIN PIPELINE\n" + query)
                        (
                            directory / f"plans/{profile}_{label}.txt"
                        ).write_text(
                            query
                            + "\nEXPLAIN indexes = 1\n"
                            + "\n".join(row[0] for row in plan)
                            + "\n\nEXPLAIN PIPELINE\n"
                            + "\n".join(row[0] for row in pipeline)
                            + "\n"
                        )
                assert_equal(
                    expected, actual, f"timed {profile}/{label}/{repeat}"
                )
                record["result_sha256"] = fingerprint(actual)
                records.append(record)
        print(
            f"Measured {profile}: warmup + {repeats} repeats for each of four variants",
            flush=True,
        )
    ch_execute("SYSTEM FLUSH LOGS")
    query_logs = ch_rows(
        """
        SELECT query_id, query_duration_ms, read_rows, read_bytes, memory_usage, ProfileEvents
        FROM system.query_log WHERE type = 'QueryFinish' AND startsWith(query_id, 'hw04_')
        ORDER BY query_id
    """
    )
    by_id = {row[0]: row for row in query_logs}
    for record in records:
        if record["variant"] != "pg":
            row = by_id[record["query_id"]]
            record["server_ms"] = row[1]
            record["query_log_read_rows"] = row[2]
            record["query_log_read_bytes"] = row[3]
            record["memory_usage_bytes"] = row[4]
            record["profile_events"] = row[5]
    summary = []
    for profile in ("narrow", "wide", "time_slice"):
        for label in LABELS:
            selected = [
                row
                for row in records
                if row["profile"] == profile and row["variant"] == label
            ]
            item = {
                "profile": profile,
                "variant": label,
                "repeats": len(selected),
            }
            for metric in (
                "wall_ms",
                "server_ms",
                "read_rows",
                "read_bytes",
                "statistics_elapsed_ms",
            ):
                values = [
                    row[metric]
                    for row in selected
                    if row.get(metric) is not None
                ]
                if values:
                    item[metric] = {
                        "min": min(values),
                        "median": statistics.median(values),
                        "max": max(values),
                    }
            summary.append(item)
    save_json(directory, "bench/raw.json", records)
    save_json(directory, "bench/query_log.json", query_logs)
    save_json(directory, "bench/warmups.json", warmups)
    save_json(directory, "bench/summary.json", summary)
    save_json(
        directory,
        "bench/background.json",
        {
            "before": before,
            "after": background(connection),
            "merge_policy": "STOP MERGES of three experimental tables until all checks and timings complete",
        },
    )
    columns = [
        "profile",
        "variant",
        "repeat",
        "query_id",
        "wall_ms",
        "server_ms",
        "statistics_elapsed_ms",
        "planning_ms",
        "read_rows",
        "read_bytes",
        "pg_shared_hit_blocks",
        "pg_shared_read_blocks",
        "pg_temp_read_blocks",
        "pg_temp_written_blocks",
        "result_sha256",
    ]
    with (directory / "bench/raw.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(records)
    return summary


def repeat_experiment(connection, directory: Path, increment_day: str) -> dict:
    before = pg_rows(connection, "SELECT count(*) FROM weather_hourly")[0][0]
    try:
        pg_rows(
            connection,
            """INSERT INTO weather_hourly
            SELECT * FROM weather_hourly WHERE city_id = 'moscow'
            ORDER BY observed_at LIMIT 1""",
        )
        raise AssertionError("PG должен отклонить повтор ключа")
    except psycopg2.errors.UniqueViolation as error:
        pg_error = error.pgcode
    after = pg_rows(connection, "SELECT count(*) FROM weather_hourly")[0][0]
    assert before == after
    ch_execute(
        "CREATE TABLE weather.weather_replay AS weather.weather_city ENGINE = MergeTree ORDER BY (city_id, observed_at)"
    )
    ch_execute(
        "CREATE TABLE weather.daily_replay AS weather.weather_daily ENGINE = AggregatingMergeTree ORDER BY (city_id, observed_date)"
    )
    replay_mv = (
        (ROOT / "sql/mv.sql")
        .read_text()
        .replace("weather.weather_daily_mv", "weather.daily_replay_mv")
        .replace("weather.weather_daily", "weather.daily_replay")
        .replace("weather.weather_city", "weather.weather_replay")
    )
    ch_execute(replay_mv)
    ch_execute("SYSTEM STOP MERGES weather.daily_replay")
    base_insert = f"""INSERT INTO weather.weather_replay SELECT * FROM weather.weather_city
        WHERE city_id = 'moscow' AND toDate(observed_at) = '{increment_day}'"""
    repeated_insert = f"""INSERT INTO weather.weather_replay SELECT * FROM weather.weather_city
        WHERE city_id = 'moscow' AND toDate(observed_at) = '{increment_day}' AND toHour(observed_at) < 6"""
    check_sql = """SELECT sum(observations) AS observations, sum(temp_count) AS temp_count,
        sum(temp_sum_centi) AS temp_sum_centi, sum(precip_sum_centi) AS precip_sum_centi
        FROM weather.daily_replay"""
    ch_execute(base_insert)
    base = ch_rows(check_sql)[0]
    ch_execute(repeated_insert)
    replayed = ch_rows(check_sql)[0]
    assert base == [24, 24, 60000, 1500]
    assert replayed == [30, 30, 66000, 1650]
    result = {
        "isolation": "Only weather_replay and daily_replay; main tables unchanged",
        "pg_duplicate_sqlstate": pg_error,
        "pg_rows_before": before,
        "pg_rows_after": after,
        "sql_initial": base_insert,
        "sql_repeated": repeated_insert,
        "sql_check": check_sql,
        "before": dict(
            zip(
                [
                    "observations",
                    "temp_count",
                    "temp_sum_centi",
                    "precip_sum_centi",
                ],
                base,
            )
        ),
        "after": dict(
            zip(
                [
                    "observations",
                    "temp_count",
                    "temp_sum_centi",
                    "precip_sum_centi",
                ],
                replayed,
            )
        ),
        "average_c_before": "25.0000",
        "average_c_after": "22.0000",
        "duplicate_business_keys": ch_rows(
            "SELECT count() - uniqExact(tuple(city_id, observed_at)) FROM weather.weather_replay"
        )[0][0],
        "batch_averages_c": ["10.0000", "30.0000"],
        "wrong_unweighted_average_c": "20.0000",
        "correct_weighted_average_c": "25.0000",
    }
    save_json(directory, "checks/replay.json", result)
    ch_execute("SYSTEM START MERGES weather.daily_replay")
    return result


def metadata(connection, directory: Path, manifest: dict) -> None:
    pg_settings = pg_rows(
        connection,
        """SELECT name, setting, unit FROM pg_settings WHERE name IN
        ('server_version', 'TimeZone', 'shared_buffers', 'work_mem', 'max_parallel_workers_per_gather',
         'max_parallel_workers', 'max_worker_processes', 'jit', 'enable_seqscan', 'enable_indexscan',
         'enable_bitmapscan', 'random_page_cost', 'effective_cache_size', 'track_io_timing', 'autovacuum') ORDER BY name""",
    )
    pg_storage = pg_rows(
        connection,
        """SELECT pg_relation_size('weather_hourly'),
        pg_indexes_size('weather_hourly'), pg_total_relation_size('weather_hourly')""",
    )
    ch_storage = ch_rows(
        """SELECT table, sum(rows), count(), sum(bytes_on_disk),
        sum(data_compressed_bytes), sum(data_uncompressed_bytes), sum(marks)
        FROM system.parts WHERE active AND database = 'weather'
        GROUP BY table ORDER BY table"""
    )
    save_json(directory, "source_manifest.json", manifest)
    save_json(
        directory,
        "environment.json",
        {
            "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "postgres_version": pg_rows(connection, "SELECT version()")[0][0],
            "clickhouse_version": ch_rows("SELECT version()")[0][0],
            "pg_settings": pg_settings,
            "clickhouse_query_settings": CH_SETTINGS,
            "pg_indexes": pg_rows(
                connection,
                "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'weather_hourly' ORDER BY indexname",
            ),
            "pg_last_analyze": pg_rows(
                connection,
                "SELECT last_analyze, last_autoanalyze, last_autovacuum FROM pg_stat_user_tables WHERE relname = 'weather_hourly'",
            ),
            "resource_limits": {
                "postgres_cpus": 2,
                "clickhouse_cpus": 2,
                "memory_per_database_bytes": 2147483648,
                "runner_cpus": 1,
                "runner_memory_bytes": 1073741824,
            },
            "cache_policy": "Warm OS/DB caches, one explicit warmup per variant; CH result cache disabled; no cache eviction",
            "pg_explain_policy": "Separate execution after each wall timing; ANALYZE BUFFERS SETTINGS TIMING OFF",
            "ch_server_timer_policy": "query_log query_duration_ms (integer ms), JSON statistics.elapsed also retained",
        },
    )
    save_json(
        directory,
        "storage.json",
        {
            "pg_weather_heap_bytes": pg_storage[0][0],
            "pg_weather_index_bytes": pg_storage[0][1],
            "pg_weather_total_bytes": pg_storage[0][2],
            "ch_columns": [
                "table",
                "physical_rows",
                "active_parts",
                "bytes_on_disk",
                "compressed_bytes",
                "uncompressed_bytes",
                "marks",
            ],
            "ch_parts": ch_storage,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", default="evidence/main")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--days", type=int, default=278)
    parser.add_argument("--cities", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261013)
    args = parser.parse_args()
    if args.repeats < 5:
        parser.error("Нужно минимум пять измерений")
    connection = connect_pg()
    if (
        pg_rows(connection, "SELECT to_regclass('public.weather_hourly')")[0][
            0
        ]
        is not None
        or ch_rows("EXISTS TABLE weather.weather_city")[0][0]
    ):
        raise RuntimeError(
            "Проект уже инициализирован. Используйте новое имя Compose-проекта; существующие данные не очищаются."
        )
    directory = ROOT / args.evidence_dir
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "completed.json").exists():
        raise RuntimeError(
            "Каталог evidence уже содержит завершённый опыт; задайте другой --evidence-dir"
        )
    manifest = generate(args.days, args.cities, args.seed)
    # Проверяем уникальность всех бизнес-ключей до первой записи в СУБД.
    source = read_rows(["history", "batch_1", "batch_2"])
    assert len(source) == len({(row[0], row[1]) for row in source})
    execute_file(connection, "sql/postgres.sql", "pg")
    execute_file(connection, "sql/clickhouse.sql", "ch")
    with (ROOT / "data/generated/cities.csv").open(
        encoding="utf-8"
    ) as handle, connection.cursor() as cursor:
        cursor.copy_expert(
            "COPY dim_city FROM STDIN WITH (FORMAT CSV, HEADER TRUE)", handle
        )
    dimension = (
        "city_id\tcity_name\tfederal_district\n"
        + "\n".join("\t".join(row) for row in cities(args.cities))
        + "\n"
    )
    ch_request(
        "INSERT INTO weather.dim_city FORMAT TSVWithNames",
        data=dimension.encode(),
        formatted=False,
    )
    loads = [load_csv(connection, "history")]
    execute_file(connection, "sql/mv.sql", "ch")
    stopped = ("weather_city", "weather_time", "weather_daily")
    for table in stopped:
        ch_execute(f"SYSTEM STOP MERGES weather.{table}")
    try:
        execute_file(connection, "sql/backfill.sql", "ch")
        history = validate(
            connection, directory, "history", ["history"], args.cities
        )
        loads.append(load_csv(connection, "batch_1"))
        first = validate(
            connection,
            directory,
            "after_batch_1",
            ["history", "batch_1"],
            args.cities,
        )
        loads.append(load_csv(connection, "batch_2"))
        second = validate(
            connection,
            directory,
            "after_batch_2",
            ["history", "batch_1", "batch_2"],
            args.cities,
        )
        assert first["increment_moscow"][0][4:6] == [6, 6000]
        assert second["increment_moscow"][0][4:6] == [24, 60000]
        assert second["increment_moscow"][0][-1] == 250000
        assert second["physical_daily_rows"] > second["logical_daily_rows"]
        save_json(directory, "loads.json", loads)
        save_json(
            directory,
            "checks/incremental.json",
            {
                "historical_rows": history["transfer"]["source_rows"],
                "after_first_batch": first["increment_moscow"],
                "after_second_batch": second["increment_moscow"],
                "physical_rows_before_merges": second["physical_daily_rows"],
                "logical_groups_before_merges": second["logical_daily_rows"],
                "backfill_once_before_incoming_batches": True,
                "late_arrivals_update_existing_day": True,
            },
        )
        pg_rows(connection, "VACUUM (ANALYZE) weather_hourly")
        pg_rows(connection, "ANALYZE dim_city")
        metadata(connection, directory, manifest)
        summary = benchmark(connection, directory, args.repeats, args.cities)
        repeat_experiment(connection, directory, manifest["increment_day"])
        save_json(
            directory,
            "completed.json",
            {
                "status": "PASS",
                "total_facts": manifest["total_rows"],
                "daily_groups": second["logical_daily_rows"],
                "measured_variants": len(summary),
                "timed_executions": args.repeats * len(summary),
                "all_values_equal": True,
            },
        )
    finally:
        for table in stopped:
            ch_execute(f"SYSTEM START MERGES weather.{table}")
        connection.close()
    print(f"PASS complete: evidence saved to {args.evidence_dir}", flush=True)


if __name__ == "__main__":
    main()
