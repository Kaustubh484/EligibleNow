from __future__ import annotations

import logging
from pathlib import Path
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.evaluator import build_actions, screen_trials
from app.extractor import DemoFactExtractor
from app.models import ScreenRequest, ScreenResponse
from app.repository import JsonRepository


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "app" / "static"
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TrialCompiler",
    version="0.1.0",
    description="Auditable, deterministic clinical-trial screening.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

repository = JsonRepository()


def build_extractor():
    if os.getenv("TRIALCOMPILER_EXTRACTOR", "demo").lower() == "bedrock":
        from app.bedrock import BedrockFactExtractor

        return BedrockFactExtractor.from_env()
    return DemoFactExtractor()


extractor = build_extractor()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str | int | bool]:
    synthetic_count = sum(trial.synthetic for trial in repository.trials)
    manual_review_count = sum(
        rule.manual_review
        for trial in repository.trials
        for rule in trial.rules
    )
    if synthetic_count == 0:
        data_source = "ClinicalTrials.gov"
    elif synthetic_count == len(repository.trials):
        data_source = "Synthetic demo"
    else:
        data_source = "Mixed trial cache"

    return {
        "status": "ok",
        "trial_count": len(repository.trials),
        "rule_count": sum(len(trial.rules) for trial in repository.trials),
        "manual_review_count": manual_review_count,
        "extractor": extractor.__class__.__name__,
        "model": getattr(getattr(extractor, "bedrock", None), "model", "local"),
        "data_source": data_source,
        "live": synthetic_count == 0 and extractor.__class__.__name__ == "BedrockFactExtractor",
    }


@app.get("/api/patients")
def list_patients():
    return repository.patients


@app.get("/api/trials")
def list_trials():
    return repository.trials


@app.get("/api/trials/{trial_id}")
@app.get("/trials/{trial_id}", include_in_schema=False)
def get_trial(trial_id: str):
    trial = repository.get_trial(trial_id)
    if not trial:
        raise HTTPException(status_code=404, detail="Trial not found")
    return trial


@app.post("/api/screen", response_model=ScreenResponse)
@app.post("/screen", response_model=ScreenResponse, include_in_schema=False)
def screen(request: ScreenRequest) -> ScreenResponse:
    patient = repository.get_patient(request.patient_id) if request.patient_id else None
    if request.patient_id and not patient:
        raise HTTPException(status_code=404, detail="Patient example not found")

    note = request.note or (patient.note if patient else "")
    if request.facts:
        facts = request.facts
    else:
        try:
            facts = extractor.extract(note)
        except Exception as exc:
            logger.exception("Patient fact extraction failed")
            raise HTTPException(
                status_code=502,
                detail=(
                    "The model could not produce evidence-grounded patient facts. "
                    "Please retry the screening request."
                ),
            ) from exc
    if not facts:
        raise HTTPException(
            status_code=422,
            detail="No supported clinical facts were found in the note",
        )

    results = screen_trials(repository.trials, facts)
    return ScreenResponse(
        patient_id=patient.patient_id if patient else request.patient_id,
        patient_note=note,
        facts=facts,
        results=results,
        actions=build_actions(results),
        candidate_count=sum(result.fail_count == 0 for result in results),
        excluded_count=sum(result.fail_count > 0 for result in results),
    )
