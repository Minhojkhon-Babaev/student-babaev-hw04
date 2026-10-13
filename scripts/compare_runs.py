#!/usr/bin/env python3
"""Сравнить сохранённые артефакты основного и чистого прогонов."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(run: str, name: str):
    return json.loads((ROOT / "evidence" / run / name).read_text())


def main() -> None:
    assert load("main", "source_manifest.json") == load(
        "clean", "source_manifest.json"
    )
    checks = []
    for stage in ("history", "after_batch_1", "after_batch_2", "post_merge"):
        original = load("main", f"checks/{stage}.json")
        clean = load("clean", f"checks/{stage}.json")
        assert original["all_checks_passed"] and clean["all_checks_passed"]
        assert original["transfer"] == clean["transfer"]
        assert original["comparisons"] == clean["comparisons"]
        checks.append(
            {"stage": stage, "same_source_and_all_result_values": True}
        )
    assert load("main", "checks/dimensions.json") == load(
        "clean", "checks/dimensions.json"
    )
    for run in ("main", "clean"):
        completed = load(run, "completed.json")
        assert completed["status"] == "PASS"
        measurements = load(run, "bench/raw.json")
        assert len(measurements) == 60
        variants = {(row["profile"], row["variant"]) for row in measurements}
        assert len(variants) == 12
        for profile, variant in variants:
            assert (
                len(
                    [
                        row
                        for row in measurements
                        if row["profile"] == profile
                        and row["variant"] == variant
                    ]
                )
                == 5
            )
    payload = {
        "status": "PASS",
        "clean_project": "hw04-clean-20261013",
        "main_project": "hw04-chweather",
        "new_named_volumes_proof": "clean/startup.txt",
        "same_generator_manifest": True,
        "same_dimension_all_fields": True,
        "stages": checks,
        "timed_selects_per_run": 60,
        "versions_and_limits": "main/environment.json and clean/environment.json",
        "scope": "Two fresh Docker data projects on the same macOS ARM64 host; build cache reused",
    }
    path = ROOT / "evidence/reproducibility.json"
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        "PASS clean reproduction: manifest, full data, all metric results and dimensions match"
    )


if __name__ == "__main__":
    main()
