from __future__ import annotations

import json
import os
from pathlib import Path

from app.models import PatientExample, Trial


class JsonRepository:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path(__file__).resolve().parents[1] / "data"
        trials_file = os.getenv("TRIALCOMPILER_TRIALS_FILE", "trials.json")
        self._trials = self._load(trials_file, Trial)
        self._patients = self._load("patients.json", PatientExample)

    @property
    def trials(self) -> list[Trial]:
        return self._trials

    @property
    def patients(self) -> list[PatientExample]:
        return self._patients

    def get_trial(self, trial_id: str) -> Trial | None:
        return next((trial for trial in self._trials if trial.trial_id == trial_id), None)

    def get_patient(self, patient_id: str) -> PatientExample | None:
        return next(
            (patient for patient in self._patients if patient.patient_id == patient_id),
            None,
        )

    def _load(self, filename: str, model: type[Trial] | type[PatientExample]):
        path = Path(filename)
        if not path.is_absolute():
            path = self.data_dir / path
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model.model_validate(item) for item in payload]
