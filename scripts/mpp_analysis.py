#!/usr/bin/env python3
"""Моделирование распределения, без MPP-кластера и без измерения его скорости."""
from __future__ import annotations

import collections
import hashlib

from db import ROOT, save_json
from generate import read_rows


def bucket(value: str, shards: int = 4) -> int:
    digest = hashlib.blake2b(value.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % shards


def stats(counts: list[int]) -> dict:
    return {
        "rows_per_shard": counts,
        "max_to_mean": max(counts) / (sum(counts) / len(counts)),
        "hash": "blake2b-64, big-endian integer mod 4",
    }


def main() -> None:
    rows = read_rows(["history", "batch_1", "batch_2"])
    city_counts = collections.Counter(row[0] for row in rows)
    counts = {
        name: [0] * 4 for name in ("city_id", "observed_date", "business_key")
    }
    for city, timestamp, *_ in rows:
        counts["city_id"][bucket(city)] += 1
        counts["observed_date"][bucket(timestamp[:10])] += 1
        counts["business_key"][bucket(city + "|" + timestamp)] += 1
    scenario = [0.0] * 4
    for city in city_counts:
        scenario[bucket(city)] += (
            0.60 if city == "moscow" else 0.40 / (len(city_counts) - 1)
        )
    save_json(
        ROOT / "evidence/main",
        "mpp.json",
        {
            "kind": "offline hash distribution model; no cluster deployment or runtime benchmark",
            "shards": 4,
            "actual_synthetic_rows": {
                name: stats(value) for name, value in counts.items()
            },
            "city_rows_min": min(city_counts.values()),
            "city_rows_max": max(city_counts.values()),
            "hypothetical_60_percent_moscow": {
                "fraction_per_shard": scenario,
                "max_to_mean": max(scenario) * 4,
                "not_observed_data": True,
            },
        },
    )
    print("MPP distribution model saved")


if __name__ == "__main__":
    main()
