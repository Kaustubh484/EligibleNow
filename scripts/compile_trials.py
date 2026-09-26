from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.bedrock import BedrockRuleCompiler
from app.models import Trial, TrialLocation


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
    args = parser.parse_args()

    compiler = BedrockRuleCompiler.from_env()
    raw_trials = json.loads(args.input.read_text(encoding="utf-8"))
    selected_trials = raw_trials[: args.limit] if args.limit else raw_trials
    compiled_by_id: dict[str, dict] = {}
    if args.resume and args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8"))
        compiled_by_id = {trial["trial_id"]: trial for trial in existing}
    errors: list[dict[str, str]] = []

    for index, raw in enumerate(selected_trials, start=1):
        if raw["trial_id"] in compiled_by_id:
            cached = compiled_by_id[raw["trial_id"]]
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
            print(f"[{index}/{len(selected_trials)}] cached {raw['trial_id']}")
            continue
        eligibility_text = raw["eligibility_text"]
        if not eligibility_text:
            print(f"[{index}/{len(selected_trials)}] skipped {raw['trial_id']}: no criteria")
            continue
        try:
            rules = compiler.compile(raw["trial_id"], eligibility_text)
            locations = raw.get("locations") or [
                {"facility": "Contact study team", "city": "Unknown", "state": ""}
            ]
            metadata = {
                key: value
                for key, value in raw.items()
                if key not in {"eligibility_text", "locations"}
            }
            trial = Trial(
                **metadata,
                locations=[TrialLocation.model_validate(item) for item in locations],
                rules=rules,
            )
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
                f"[{index}/{len(selected_trials)}] failed {raw['trial_id']}: "
                f"{type(exc).__name__}: {message}"
            )
            error_path = args.output.with_suffix(".errors.json")
            error_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")
            if args.fail_fast:
                raise
            continue

        compiled_by_id[trial.trial_id] = trial.model_dump(mode="json")
        ordered = [
            compiled_by_id[item["trial_id"]]
            for item in selected_trials
            if item["trial_id"] in compiled_by_id
        ]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
        print(
            f"[{index}/{len(selected_trials)}] compiled "
            f"{trial.trial_id}: {len(rules)} rules"
        )

    ordered = [
        compiled_by_id[item["trial_id"]]
        for item in selected_trials
        if item["trial_id"] in compiled_by_id
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ordered, indent=2), encoding="utf-8")
    error_path = args.output.with_suffix(".errors.json")
    error_path.write_text(json.dumps(errors, indent=2), encoding="utf-8")
    print(
        f"Saved {len(ordered)} compiled trials to {args.output}; "
        f"{len(errors)} failures in {error_path}"
    )


if __name__ == "__main__":
    main()
