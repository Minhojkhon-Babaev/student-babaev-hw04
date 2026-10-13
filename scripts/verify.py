#!/usr/bin/env python3
"""Повторный read-only контроль уже загруженных данных после фоновых merges."""
from __future__ import annotations

import argparse
import csv

from db import ROOT, ch_rows, connect_pg, pg_rows, save_json
from run import assert_equal, fingerprint, validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", default="evidence/main")
    args = parser.parse_args()
    directory = ROOT / args.evidence_dir
    connection = connect_pg()
    with (ROOT / "data/generated/cities.csv").open(encoding="utf-8") as handle:
        expected = list(csv.reader(handle))[1:]
    query = "SELECT city_id, city_name, federal_district FROM dim_city ORDER BY city_id"
    expected.sort()
    pg = pg_rows(connection, query)
    ch = ch_rows(query.replace("FROM dim_city", "FROM weather.dim_city"))
    assert_equal(expected, pg, "Справочник PG")
    assert_equal(expected, ch, "Справочник CH")
    save_json(
        directory,
        "checks/dimensions.json",
        {
            "all_fields_equal": True,
            "source_sha256": fingerprint(expected),
            "pg_sha256": fingerprint(pg),
            "ch_sha256": fingerprint(ch),
            "rows": len(expected),
        },
    )
    validate(
        connection,
        directory,
        "post_merge",
        ["history", "batch_1", "batch_2"],
        len(expected),
    )
    connection.close()
    print("PASS dimensions and post-merge control", flush=True)


if __name__ == "__main__":
    main()
