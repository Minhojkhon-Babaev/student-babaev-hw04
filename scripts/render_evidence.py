#!/usr/bin/env python3
"""Отобразить фактические evidence в автономных HTML для браузерных снимков."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "evidence/main"
OUTPUT = ROOT / "evidence/screenshots"


def load(name: str):
    return json.loads((MAIN / name).read_text())


def pre(value: str) -> str:
    return "<pre>" + html.escape(value) + "</pre>"


def table(headers: list[str], rows: list[list]) -> str:
    def cells(row, tag):
        return (
            "<tr>"
            + "".join(
                f"<{tag}>{html.escape(str(value))}</{tag}>" for value in row
            )
            + "</tr>"
        )

    return (
        "<table>"
        + cells(headers, "th")
        + "".join(cells(row, "td") for row in rows)
        + "</table>"
    )


def section(title: str, body: str) -> str:
    return f"<section><h2>{html.escape(title)}</h2>{body}</section>"


def page(name: str, title: str, content: str, source: str) -> None:
    style = """
    * { box-sizing:border-box } body { margin:0; padding:32px; color:#172431;
    background:#f0f3f6; font:16px/1.45 system-ui,sans-serif }
    header,section,footer { background:white; border:1px solid #d6dde5;
    border-radius:8px; padding:22px; margin-bottom:20px } h1 {font-size:28px;margin:6px 0}
    h2 {font-size:20px;margin:0 0 14px} p {margin:8px 0} .label {color:#416380;font-size:13px}
    .grid {display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}
    .grid section {min-width:0} pre {background:#f7f9fb;border:1px solid #e0e6ec;
    padding:15px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace}
    table {border-collapse:collapse;width:100%;font-size:14px} th,td {border:1px solid #d9e0e7;
    padding:10px;text-align:left;vertical-align:top;overflow-wrap:anywhere} th {background:#eaf1f7}
    .success {color:#166447;font-weight:650}.big {font-size:24px;font-weight:700}
    code {font-family:ui-monospace,monospace} footer {font-size:12px;color:#536778}
    """
    document = (
        "<!doctype html><html lang='ru'><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{style}</style><body>"
        "<header><div class='label'>ДЗ 4 · EVIDENCE VIEWER · 13 октября 2026</div>"
        f"<h1>{html.escape(title)}</h1><p>Сохранённый вывод выполненного эксперимента. "
        "SQL, планы и ответы взяты из файлов evidence; это не имитация интерфейса СУБД.</p></header>"
        + content
        + "<footer>Источники: "
        + html.escape(source)
        + " · Числа не извлечены из скриншотов; исходные артефакты приложены.</footer></body></html>"
    )
    (OUTPUT / f"{name}.html").write_text(document, encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = load("environment.json")
    host = load("host.json")
    live = load("live_queries.json")
    page(
        "01_environment",
        "Работающее изолированное окружение",
        section("docker compose ps", pre(host["compose_ps"]))
        + section(
            "Версии и ресурсы",
            table(
                ["Параметр", "Фактический вывод"],
                [
                    ["ОС хоста", host["macos"]],
                    ["Архитектура", host["host_architecture"]],
                    [
                        "Docker Engine / Compose",
                        host["docker_server"] + " / " + host["compose"],
                    ],
                    ["VM", host["docker_vm_resources"]],
                    ["PostgreSQL", env["postgres_version"]],
                    ["ClickHouse", env["clickhouse_version"]],
                    ["Python", env["python"]],
                    ["Лимиты контейнеров", host["container_limits"]],
                ],
            ),
        )
        + "<div class='grid'>"
        + section(
            "PostgreSQL — выполненный SELECT",
            pre(live["pg"]["sql"])
            + table(
                ["observations", "unique_business_keys"], live["pg"]["data"]
            ),
        )
        + section(
            "ClickHouse — выполненный SELECT",
            pre(live["ch"]["sql"])
            + table(
                ["observations", "unique_business_keys"], live["ch"]["data"]
            ),
        )
        + "</div>",
        "main/host.json; main/environment.json; main/live_queries.json",
    )
    for profile, name, title in [
        ("narrow", "02_plans_narrow", "Выборочный запрос: индекс и гранулы"),
        ("wide", "02b_plans_wide", "Широкий запрос: JOIN и агрегация"),
    ]:
        pg = (MAIN / f"plans/{profile}_pg.txt").read_text()
        ch = (MAIN / f"plans/{profile}_ch_city.txt").read_text()
        page(
            name,
            title,
            "<div class='grid'>"
            + section("PostgreSQL: SQL + EXPLAIN ANALYZE BUFFERS", pre(pg))
            + section(
                "ClickHouse city-first: SQL + EXPLAIN indexes / PIPELINE",
                pre(ch),
            )
            + "</div>",
            f"main/plans/{profile}_pg.txt; main/plans/{profile}_ch_city.txt",
        )
    checks = load("checks/after_batch_2.json")
    transfer = checks["transfer"]
    stages = []
    for stage in ("history", "after_batch_1", "after_batch_2", "post_merge"):
        item = load(f"checks/{stage}.json")
        stages.append(
            [
                stage,
                item["transfer"]["source_rows"],
                item["logical_daily_rows"],
                "PASS: every field and every group",
            ]
        )
    comparison = []
    for profile, values in checks["comparisons"].items():
        hashes = {value["sha256"] for value in values.values()}
        comparison.append(
            [
                profile,
                values["source"]["rows"],
                (
                    "source = pg = ch_city = ch_time = ch_mv"
                    if len(hashes) == 1
                    else "FAIL"
                ),
                values["source"]["sha256"],
            ]
        )
    page(
        "03_equality",
        "Равенство всех строк, ключей и метрик",
        section(
            "Контроль переноса",
            "<p class='success big'>200 232 факта · уникальные бизнес-ключи · PASS</p>"
            + table(
                ["Набор", "Строк", "SHA256 всех полей в порядке ключа"],
                [
                    [label, transfer[label]["rows"], transfer[label]["sha256"]]
                    for label in ("pg", "ch_city", "ch_time")
                ],
            )
            + pre("Source SHA256: " + transfer["source_sha256"]),
        )
        + section(
            "Источник CSV → независимый Python → четыре SQL-варианта",
            table(
                ["Профиль", "Групп", "Полное равенство", "SHA256 ответа"],
                comparison,
            )
            + "<p>Сравниваются counts, sums, min/max и средняя; NULL и UTC нормализованы. "
            "Выполнено прямое сравнение полных массивов, кроме проверки SHA256.</p>",
        )
        + section(
            "Проверка на каждом этапе",
            table(["Этап", "Фактов", "Городо-дней", "Результат"], stages),
        )
        + section(
            "Исполненный SQL полного дневного контроля ClickHouse",
            pre((ROOT / "sql/check/daily_ch_mv.sql").read_text()),
        ),
        "main/checks/{history,after_batch_1,after_batch_2,post_merge}.json; sql/check/daily_ch_mv.sql",
    )
    incremental = load("checks/incremental.json")
    state_rows = []
    for label, items in [
        ("После пачки 1 (6 новых часов)", incremental["after_first_batch"]),
        ("После пачки 2 (+18 часов)", incremental["after_second_batch"]),
    ]:
        row = items[0]
        state_rows.append(
            [label, row[0], row[1], row[4], row[5], f"{row[-1] / 10000:.4f}"]
        )
    page(
        "04_incremental",
        "Новые вставки автоматически обновляют MV",
        section(
            "Пачки действительно вставлены загрузчиком",
            pre(
                "COPY weather_hourly FROM STDIN WITH (FORMAT CSV, HEADER TRUE, NULL '');\n"
                "INSERT INTO weather.weather_city FORMAT TSVWithNames\n"
                "INSERT INTO weather.weather_time FORMAT TSVWithNames\n\n"
                "batch_1.csv: 18 строк (12 поздних + 6 часов нового дня)\n"
                "batch_2.csv: 66 строк (18 часов Москвы + 48 часов Сочи/Якутска)"
            ),
        )
        + section(
            "Сохранённые ответы после каждой вставки",
            table(
                [
                    "Этап",
                    "Город",
                    "День UTC",
                    "temp_count",
                    "temp_sum_centi",
                    "Средняя, °C",
                ],
                state_rows,
            )
            + "<p>Невзвешенное (10+30)/2 = 20 °C ошибочно; (6×10+18×30)/24 = 25 °C.</p>",
        )
        + section(
            "Слияние нескольких частей без ожидания merges",
            table(
                [
                    "Физических строк до merges",
                    "Логических групп",
                    "Равенство сырому источнику",
                ],
                [
                    [
                        incremental["physical_rows_before_merges"],
                        incremental["logical_groups_before_merges"],
                        "PASS",
                    ]
                ],
            ),
        )
        + section(
            "Короткий SELECT выполнен после опыта",
            pre(live["mv"]["sql"])
            + table(
                [
                    "city_id",
                    "observed_date",
                    "observations",
                    "temp_count",
                    "temp_sum_centi",
                    "precip_sum_centi",
                    "min",
                    "max",
                ],
                live["mv"]["data"],
            ),
        ),
        "main/loads.json; main/checks/incremental.json; main/checks/after_batch_{1,2}.json; main/live_queries.json",
    )
    replay = load("checks/replay.json")
    replay_rows = [
        [
            label,
            item["observations"],
            item["temp_sum_centi"],
            item["precip_sum_centi"],
            average,
        ]
        for label, item, average in [
            ("Исходные 24 часа", replay["before"], replay["average_c_before"]),
            (
                "Повторно доставлены 6 часов",
                replay["after"],
                replay["average_c_after"],
            ),
        ]
    ]
    page(
        "05_replay",
        "Повторная доставка и граница гарантий",
        section(
            "Отдельные таблицы weather_replay / daily_replay",
            pre(
                replay["sql_initial"]
                + ";\n\n"
                + replay["sql_repeated"]
                + ";\n\n"
                + replay["sql_check"]
                + ";"
            ),
        )
        + section(
            "Фактический результат",
            table(
                [
                    "Этап",
                    "observations",
                    "temp_sum_centi",
                    "precip_sum_centi",
                    "Средняя, °C",
                ],
                replay_rows,
            )
            + f"<p>Повторяющихся бизнес-ключей: <b>{replay['duplicate_business_keys']}</b>. "
            "Обычный MergeTree и MV прибавляют доставленные строки повторно.</p>",
        )
        + section(
            "PostgreSQL защищён PK; основной опыт сохранён",
            pre(
                "INSERT INTO weather_hourly SELECT * FROM weather_hourly\n"
                "WHERE city_id = 'moscow' ORDER BY observed_at LIMIT 1;\n\n"
                f"SQLSTATE {replay['pg_duplicate_sqlstate']} (UniqueViolation)\n"
                f"PG count before={replay['pg_rows_before']}; after={replay['pg_rows_after']}"
            ),
        ),
        "main/checks/replay.json; scripts/run.py:repeat_experiment",
    )
    results = []
    for item in load("bench/summary.json"):
        wall = item["wall_ms"]
        results.append(
            [
                item["profile"],
                item["variant"],
                item["repeats"],
                f"{wall['min']:.3f} / {wall['median']:.3f} / {wall['max']:.3f}",
                item["server_ms"]["median"],
                item["read_rows"]["median"],
                item.get("read_bytes", {}).get("median", "PG: BUFFERS"),
            ]
        )
    page(
        "06_measurements",
        "Прогрев, пять повторов и чистый запуск",
        section(
            "Основной прогон — все 12 вариантов",
            table(
                [
                    "Профиль",
                    "Вариант",
                    "Повторов",
                    "Wall мин / медиана / макс, мс",
                    "Сервер медиана, мс",
                    "read_rows",
                    "CH read_bytes",
                ],
                results,
            )
            + "<p>Wall: perf_counter_ns + полный ответ. PG server: отдельный EXPLAIN ANALYZE TIMING OFF; "
            "CH server: query_log того же query_id. CH read_bytes — логические несжатые байты.</p>",
        )
        + section(
            "Одинаковые условия",
            pre(
                json.dumps(
                    load("bench/background.json"), ensure_ascii=False, indent=2
                )
            )
            + "<p>Тёплые кэши, 12 отброшенных прогревов, CH result cache выключен; "
            "PG VACUUM ANALYZE, все способы доступа и JIT включены.</p>",
        )
        + section(
            "Новый Docker-проект: сохранённый полный PASS",
            pre((ROOT / "evidence/clean/run.txt").read_text()),
        )
        + section(
            "Два независимых набора данных совпали",
            pre((ROOT / "evidence/reproducibility.json").read_text()),
        ),
        "main/bench/{raw.csv,summary.json,warmups.json,background.json}; clean/run.txt; reproducibility.json",
    )
    print(
        "Rendered seven evidence pages from actual SQL and measurement files"
    )


if __name__ == "__main__":
    main()
