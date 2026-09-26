import json
from pathlib import Path

from app.extractor import FIELD_VOCABULARY


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_live_cache_is_real_open_and_traceable() -> None:
    cohorts = json.loads((DATA_DIR / "cohorts.json").read_text())

    assert {cohort["cancer_type"] for cohort in cohorts} == {
        "nsclc",
        "breast",
        "colorectal",
    }

    for cohort in cohorts:
        cancer_type = cohort["cancer_type"]
        raw_trials = json.loads(
            (DATA_DIR / f"raw_trials.{cancer_type}.json").read_text()
        )
        live_trials = json.loads(
            (DATA_DIR / cohort["trials_file"]).read_text()
        )
        raw_by_id = {trial["trial_id"]: trial for trial in raw_trials}

        assert len(live_trials) == 10
        assert len(raw_by_id) == 10
        assert {trial["trial_id"] for trial in live_trials} == set(raw_by_id)
        assert all(not trial["synthetic"] for trial in live_trials)
        assert all(
            trial["status"] in {"Recruiting", "Not Yet Recruiting"}
            and trial["study_type"] == "Interventional"
            and set(trial["intervention_types"]) & {"Drug", "Biological"}
            for trial in live_trials
        )

        for trial in live_trials:
            rules = trial["rules"]
            assert rules
            assert len({rule["rule_id"] for rule in rules}) == len(rules)
            assert all(rule["field"] in FIELD_VOCABULARY for rule in rules)
            assert all(
                rule["source_text"].strip()
                in raw_by_id[trial["trial_id"]]["eligibility_text"]
                for rule in rules
            )
