from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import threading

from app.bedrock import BedrockRuleCompiler
from app.models import Trial, TrialLocation


_thread_state = threading.local()


def compile_trial(raw: dict, attempts: int = 1) -> Trial:
    compiler = getattr(_thread_state, "compiler", None)
    if compiler is None:
        compiler = BedrockRuleCompiler.from_env()
        _thread_state.compiler = compiler

    for attempt in range(1, attempts + 1):
        try:
            rules = compiler.compile(raw["trial_id"], raw["eligibility_text"])
            break
        except Exception:
            if attempt == attempts:
                raise
    locations = raw.get("locations") or [
        {"facility": "Contact study team", "city": "Unknown", "state": ""}
    ]
    metadata = {
        key: value
        for key, value in raw.items()
        if key not in {"eligibility_text", "locations"}
    }
    return Trial(
        **metadata,
        locations=[TrialLocation.model_validate(item) for item in locations],
        rules=rules,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile cached eligibility text into TrialCompiler rules."
    )
    parser.add_argument("--input", type=Path, default=Path("data/raw_trials.json"))
    parser.add_argument("--output", type=Path, default=Path("data/trials.live.json"))
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Compile only the first N input trials (useful for a smoke test).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Keep trials already present in the output and compile the remainder.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first model or validation error.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Maximum concurrent Bedrock compilations.",
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=2,
        help="Attempts for transient or invalid model responses.",
    )
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8:
        parser.error("--workers must be between 1 and 8")
    if args.attempts < 1 or args.attempts > 3:
        parser.error("--attempts must be between 1 and 3")

    raw_trials = json.loads(args.input.read_text(encoding="utf-8"))
    selected_trials = raw_trials[: args.limit] if args.limit else raw_trials
    compiled_by_id: dict[str, dict] = {}
    if args.resume and args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        compiled_by_id = {trial["trial_id"]: trial for trial in existing}
    errors: list[dict[str, str]] = []
    pending: list[tuple[int, dict]] = []

    def persist() -> None:
        ordered = [
            compiled_by_id[item["trial_id"]]
            for item in selected_trials
            if item["trial_id"] in compiled_by_id
        ]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = args.output.with_name(f"{args.output.name}.tmp")
        temporary_path.write_text(
            json.dumps(ordered, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(args.output)

    for index, raw in enumerate(selected_trials, start=1):
        cached = compiled_by_id.get(raw["trial_id"])
        cache_is_current = cached and (
            not cached.get("eligibility_hash")
            or cached.get("eligibility_hash") == raw.get("eligibility_hash")
        )
        if cache_is_current:
            locations = raw.get("locations") or [
                {"facility": "Contact study team", "city": "Unknown", "state": ""}
            ]
            metadata = {
                key: value
                for key, value in raw.items()
                if key not in {"eligibility_text", "locations"}
            }
            refreshed = Trial(
                **metadata,
                locations=[
                    TrialLocation.model_validate(item)
                    for item in locations
                ],
                rules=cached["rules"],
            )
            compiled_by_id[raw["trial_id"]] = refreshed.model_dump(mode="json")
            print(
                f"[{index}/{len(selected_trials)}] cached {raw['trial_id']}",
                flush=True,
            )
            continue
        if not raw["eligibility_text"]:
            print(
                f"[{index}/{len(selected_trials)}] skipped "
                f"{raw['trial_id']}: no criteria",
                flush=True,
            )
            continue
        compiled_by_id.pop(raw["trial_id"], None)
        pending.append((index, raw))

    persist()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(compile_trial, raw, args.attempts): (index, raw)
            for index, raw in pending
        }
        for future in as_completed(futures):
            index, raw = futures[future]
            try:
                trial = future.result()
            except Exception as exc:
                message = str(exc).replace("\n", " ")[:500]
                errors.append(
                    {
                        "trial_id": raw["trial_id"],
                        "error_type": type(exc).__name__,
                        "message": message,
                    }
                )
                print(
                    f"[{index}/{len(selected_trials)}] failed "
                    f"{raw['trial_id']}: {type(exc).__name__}: {message}",
                    flush=True,
                )
                error_path = args.output.with_suffix(".errors.json")
                error_path.write_text(
                    json.dumps(errors, indent=2),
                    encoding="utf-8",
                )
                if args.fail_fast:
                    for item in futures:
                        item.cancel()
                    raise
                continue

            compiled_by_id[trial.trial_id] = trial.model_dump(mode="json")
            persist()
            print(
                f"[{index}/{len(selected_trials)}] compiled "
                f"{trial.trial_id}: {len(trial.rules)} rules",
                flush=True,
            )

    persist()
    error_path = args.output.with_suffix(".errors.json")
    error_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")
    print(
        f"Saved {sum(item['trial_id'] in compiled_by_id for item in selected_trials)} "
        f"compiled trials to {args.output}; "
        f"{len(errors)} failures in {error_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
