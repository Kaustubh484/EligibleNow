from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import os
import subprocess
import sys
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.evaluator import build_actions, screen_trials
from app.extractor import DemoFactExtractor
from app.models import ScreenRequest, ScreenResponse
from app.repository import JsonRepository
from app.retrieval import retrieve_trials


BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "app" / "static"
DATA_DIR = BASE_DIR / "data"
logger = logging.getLogger(__name__)


def _latest_cache_timestamp() -> str | None:
    cache_files = list(DATA_DIR.glob("raw_trials*.json"))
    if not cache_files:
        return None
    latest_mtime = max(path.stat().st_mtime for path in cache_files)
    return datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat()


app = FastAPI(
    title="TrialCompiler",
    version="0.1.0",
    description="Auditable, deterministic clinical-trial screening.",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

repository = JsonRepository()
refresh_lock = threading.Lock()
refresh_state = {
    "status": "idle",
    "message": "Trial cache is ready.",
    "started_at": None,
    "finished_at": None,
    "last_refreshed_at": _latest_cache_timestamp(),
}


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
    trials = repository.all_trials
    synthetic_count = sum(trial.synthetic for trial in trials)
    manual_review_count = sum(
        rule.manual_review
        for trial in trials
        for rule in trial.rules
    )
    if synthetic_count == 0:
        data_source = "ClinicalTrials.gov"
    elif synthetic_count == len(trials):
        data_source = "Synthetic demo"
    else:
        data_source = "Mixed trial cache"

    return {
        "status": "ok",
        "cancer_type_count": len(repository.cancer_types),
        "trial_count": len(trials),
        "rule_count": sum(len(trial.rules) for trial in trials),
        "manual_review_count": manual_review_count,
        "extractor": extractor.__class__.__name__,
        "model": getattr(getattr(extractor, "bedrock", None), "model", "local"),
        "data_source": data_source,
        "live": synthetic_count == 0 and extractor.__class__.__name__ == "BedrockFactExtractor",
    }


@app.get("/api/cancer-types")
def list_cancer_types():
    return repository.cancer_types


@app.get("/api/patients")
def list_patients(cancer_type: str | None = None):
    if cancer_type and repository.get_trials(cancer_type) is None:
        raise HTTPException(status_code=404, detail="Cancer cohort not found")
    return [
        patient
        for patient in repository.patients
        if not cancer_type or patient.cancer_type == cancer_type
    ]


@app.get("/api/trials")
def list_trials(cancer_type: str | None = None):
    trials = repository.get_trials(cancer_type)
    if trials is None:
        raise HTTPException(status_code=404, detail="Cancer cohort not found")
    return trials


@app.get("/api/trial-refresh")
def get_trial_refresh():
    with refresh_lock:
        return dict(refresh_state)


@app.post("/api/trial-refresh", status_code=202)
def start_trial_refresh():
    if not os.getenv("BEDROCK_MODEL"):
        raise HTTPException(
            status_code=503,
            detail="Bedrock must be configured before refreshing trial rules.",
        )

    with refresh_lock:
        if refresh_state["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="A trial refresh is already running.",
            )
        refresh_state.update(
            {
                "status": "running",
                "message": "Fetching and compiling trial updates…",
                "started_at": _utc_now(),
                "finished_at": None,
            }
        )

    _start_trial_refresh_thread()
    with refresh_lock:
        return dict(refresh_state)


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

    cancer_type = (
        request.cancer_type
        or (patient.cancer_type if patient else None)
        or repository.default_cancer_type
    )
    trials = repository.get_trials(cancer_type)
    if trials is None:
        raise HTTPException(status_code=404, detail="Cancer cohort not found")

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

    retrieved_trials = retrieve_trials(
        trials,
        note,
        facts,
        request.retrieval_limit,
    )
    results = screen_trials(retrieved_trials, facts)
    return ScreenResponse(
        cancer_type=cancer_type,
        patient_id=patient.patient_id if patient else request.patient_id,
        patient_note=note,
        facts=facts,
        results=results,
        actions=build_actions(results),
        total_trial_count=len(trials),
        screened_trial_count=len(retrieved_trials),
        candidate_count=sum(result.fail_count == 0 for result in results),
        excluded_count=sum(result.fail_count > 0 for result in results),
    )


def _run_trial_refresh() -> None:
    global repository

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.sync_cohorts",
                "--workers",
                "3",
            ],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        repository = JsonRepository()
    except Exception:
        logger.exception("Manual trial refresh failed")
        with refresh_lock:
            refresh_state.update(
                {
                    "status": "failed",
                    "message": "Refresh failed. Check the server log and try again.",
                    "finished_at": _utc_now(),
                }
            )
        return

    with refresh_lock:
        refreshed_at = _utc_now()
        refresh_state.update(
            {
                "status": "succeeded",
                "message": (
                    f"Loaded {len(repository.all_trials)} refreshed trials."
                ),
                "finished_at": refreshed_at,
                "last_refreshed_at": refreshed_at,
            }
        )


def _start_trial_refresh_thread() -> None:
    threading.Thread(target=_run_trial_refresh, daemon=True).start()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
