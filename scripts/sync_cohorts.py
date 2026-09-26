from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

from scripts.fetch_trials import fetch_recruiting_trials


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh and incrementally compile every configured cancer cohort."
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("data/cohorts.json"),
    )
    parser.add_argument(
        "--cohort",
        action="append",
        help="Refresh only this cancer_type; repeat to select multiple cohorts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override each cohort's configured trial limit.",
    )
    parser.add_argument(
        "--fetch-only",
        action="store_true",
        help="Refresh raw registry caches without invoking Bedrock.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Concurrent Bedrock compilations per cohort.",
    )
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    selected = set(args.cohort or [])
    compile_jobs: list[tuple[str, Path, Path]] = []

    for cohort in catalog:
        cancer_type = cohort["cancer_type"]
        if selected and cancer_type not in selected:
            continue

        limit = args.limit or cohort.get("limit", 100)
        raw_path = args.catalog.parent / cohort["raw_file"]
        compiled_path = args.catalog.parent / cohort["trials_file"]
        trials = fetch_recruiting_trials(
            cohort["condition"],
            limit,
            treatment_only=True,
        )
        temporary_path = raw_path.with_name(f"{raw_path.name}.tmp")
        temporary_path.write_text(
            json.dumps(trials, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(raw_path)
        print(f"{cancer_type}: fetched {len(trials)} treatment studies")

        if args.fetch_only:
            continue

        compile_jobs.append((cancer_type, raw_path, compiled_path))

    def compile_cohort(job: tuple[str, Path, Path]) -> None:
        cancer_type, raw_path, compiled_path = job
        print(f"{cancer_type}: compiling changed protocols", flush=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.compile_trials",
                "--input",
                str(raw_path),
                "--output",
                str(compiled_path),
                "--resume",
                "--workers",
                str(args.workers),
            ],
            check=True,
        )

    with ThreadPoolExecutor(max_workers=min(3, len(compile_jobs) or 1)) as pool:
        list(pool.map(compile_cohort, compile_jobs))


if __name__ == "__main__":
    main()
