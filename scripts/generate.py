#!/usr/bin/env python3
"""Детерминированная синтетика погодного домена; без внешних данных и float."""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = [
    "city_id",
    "observed_at",
    "temp_centi",
    "precip_centi",
    "is_valid",
    "batch_id",
]
START = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)


def cities(count: int) -> list[tuple[str, str, str]]:
    base = [
        ("moscow", "Москва", "Центральный"),
        ("sochi", "Сочи", "Южный"),
        ("yakutsk", "Якутск", "Дальневосточный"),
    ]
    return base + [
        (f"syn_{i:02d}", f"SYN-город-{i:02d}", f"SYN-округ-{i % 3}")
        for i in range(1, count - 2)
    ]


def observation(city: str, index: int, day: int, hour: int, seed: int) -> list:
    timestamp = START + dt.timedelta(days=day, hours=hour)
    digest = hashlib.blake2b(
        f"{seed}|{city}|{day}|{hour}".encode(), digest_size=8
    ).digest()
    noise = int.from_bytes(digest, "big")
    seasonal = [
        -1500,
        -1000,
        -300,
        600,
        1300,
        1800,
        2000,
        1700,
        1000,
        300,
        -500,
        -1200,
    ]
    diurnal = [
        -400,
        -430,
        -460,
        -480,
        -470,
        -400,
        -300,
        -150,
        0,
        150,
        300,
        420,
        500,
        550,
        500,
        420,
        300,
        180,
        50,
        -100,
        -220,
        -300,
        -350,
        -380,
    ]
    base = {"moscow": 500, "sochi": 1200, "yakutsk": -800}.get(
        city, -300 + index * 35
    )
    temperature = (
        base
        + seasonal[timestamp.month - 1]
        + diurnal[hour]
        + noise % 301
        - 150
    )
    precipitation = noise % 301 if noise % 9 == 0 else 0
    if noise % 97 == 0 or (city == "syn_27" and day == 0):
        temperature = None
    if noise % 89 == 0:
        precipitation = None
    valid = int(noise % 113 != 0 and not (city == "syn_26" and day == 1))
    return [
        city,
        timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        temperature,
        precipitation,
        valid,
        0,
    ]


def write_csv(path: Path, rows: list | object, fields: list[str]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(fields)
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def generate(days: int = 278, count: int = 30, seed: int = 20261013) -> dict:
    if days < 185 or count < 3 or count > 100:
        raise ValueError(
            "Нужно >=185 дней и 3..100 городов для фиксированных SQL-профилей"
        )
    dimension = cities(count)
    history = []
    late = []
    for day in range(days):
        for index, (city, _, _) in enumerate(dimension):
            for hour in range(24):
                row = observation(city, index, day, hour, seed)
                if day == days - 1 and city == "moscow" and hour >= 12:
                    row[-1] = 1
                    late.append(row)
                else:
                    history.append(row)
    first = late + [
        [
            "moscow",
            (START + dt.timedelta(days=days, hours=hour)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            1000,
            25,
            1,
            1,
        ]
        for hour in range(6)
    ]
    second = [
        [
            "moscow",
            (START + dt.timedelta(days=days, hours=hour)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            3000,
            75,
            1,
            2,
        ]
        for hour in range(6, 24)
    ]
    for index, (city, _, _) in enumerate(dimension[1:3], start=1):
        for hour in range(24):
            row = observation(city, index, days, hour, seed)
            row[-1] = 2
            second.append(row)
    write_csv(
        ROOT / "data/generated/cities.csv",
        dimension,
        ["city_id", "city_name", "federal_district"],
    )
    batches = {}
    for name, rows in [
        ("history", history),
        ("batch_1", first),
        ("batch_2", second),
    ]:
        path = ROOT / "data/generated" / f"{name}.csv"
        size = write_csv(path, rows, FIELDS)
        batches[name] = {
            "rows": size,
            "csv_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        if name != "history":
            write_csv(ROOT / "data/examples" / f"{name}.csv", rows, FIELDS)
    manifest = {
        "seed": seed,
        "days": days,
        "cities": count,
        "start_utc": START.isoformat(),
        "increment_day": (START + dt.timedelta(days=days)).date().isoformat(),
        "batches": batches,
        "total_rows": len(history) + len(first) + len(second),
        "synthetic": True,
    }
    (ROOT / "data/generated/manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest


def read_rows(names: list[str]) -> list[list]:
    rows = []
    for name in names:
        with (ROOT / "data/generated" / f"{name}.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            for row in csv.DictReader(handle):
                rows.append(
                    [
                        row["city_id"],
                        row["observed_at"],
                        int(row["temp_centi"]) if row["temp_centi"] else None,
                        (
                            int(row["precip_centi"])
                            if row["precip_centi"]
                            else None
                        ),
                        int(row["is_valid"]),
                        int(row["batch_id"]),
                    ]
                )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=278)
    parser.add_argument("--cities", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261013)
    args = parser.parse_args()
    print(json.dumps(generate(args.days, args.cities, args.seed), indent=2))
