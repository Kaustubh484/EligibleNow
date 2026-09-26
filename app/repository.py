from __future__ import annotations

import json
import os
from pathlib import Path

from app.models import PatientExample, Trial


class JsonRepository:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path(__file__).resolve().parents[1] / "data"
        catalog_file = os.getenv("TRIALCOMPILER_COHORTS_FILE")
        if catalog_file:
            catalog = self._read_json(catalog_file)
        else:
            catalog = [
                {
                    "cancer_type": os.getenv(
                        "TRIALCOMPILER_DEFAULT_CANCER_TYPE",
                        "nsclc",
                    ),
                    "label": os.getenv(
                        "TRIALCOMPILER_DEFAULT_CANCER_LABEL",
                        "Non-small cell lung cancer",
                    ),
                    "condition": "non-small cell lung cancer",
                    "trials_file": os.getenv(
                        "TRIALCOMPILER_TRIALS_FILE",
                        "trials.json",
                    ),
                }
            ]

        if not catalog:
            raise ValueError("The cancer cohort catalog is empty")

        self._cohorts = {
            item["cancer_type"]: {
                "cancer_type": item["cancer_type"],
                "label": item["label"],
                "condition": item["condition"],
                "trials_file": item["trials_file"],
            }
            for item in catalog
        }
        self._trials_by_cancer = {
            cancer_type: self._load(item["trials_file"], Trial)
            for cancer_type, item in self._cohorts.items()
        }
        configured_default = os.getenv("TRIALCOMPILER_DEFAULT_CANCER_TYPE")
        self.default_cancer_type = (
            configured_default
            if configured_default in self._cohorts
            else next(iter(self._cohorts))
        )
        self._patients = self._load("patients.json", PatientExample)

    @property
    def trials(self) -> list[Trial]:
        return self._trials_by_cancer[self.default_cancer_type]

    @property
    def all_trials(self) -> list[Trial]:
        return [
            trial
            for trials in self._trials_by_cancer.values()
            for trial in trials
        ]

    @property
    def cancer_types(self) -> list[dict[str, str | int | bool]]:
        return [
            {
                "cancer_type": cancer_type,
                "label": cohort["label"],
                "condition": cohort["condition"],
                "trial_count": len(self._trials_by_cancer[cancer_type]),
                "rule_count": sum(
                    len(trial.rules)
                    for trial in self._trials_by_cancer[cancer_type]
                ),
                "default": cancer_type == self.default_cancer_type,
            }
            for cancer_type, cohort in self._cohorts.items()
        ]

    @property
    def patients(self) -> list[PatientExample]:
        return self._patients

    def get_trials(self, cancer_type: str | None = None) -> list[Trial] | None:
        return self._trials_by_cancer.get(cancer_type or self.default_cancer_type)

    def get_trial(self, trial_id: str) -> Trial | None:
        return next(
            (
                trial
                for trial in self.all_trials
                if trial.trial_id == trial_id
            ),
            None,
        )

    def get_patient(self, patient_id: str) -> PatientExample | None:
        return next(
            (patient for patient in self._patients if patient.patient_id == patient_id),
            None,
        )

    def _load(self, filename: str, model: type[Trial] | type[PatientExample]):
        payload = self._read_json(filename)
        return [model.model_validate(item) for item in payload]

    def _read_json(self, filename: str):
        path = Path(filename)
        if not path.is_absolute():
            path = self.data_dir / path
        return json.loads(path.read_text(encoding="utf-8"))
