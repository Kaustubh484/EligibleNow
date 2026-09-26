from app.models import PatientFact, Trial
from app.retrieval import retrieve_trials


def make_trial(
    trial_id: str,
    *,
    title: str,
    summary: str = "",
    conditions: list[str] | None = None,
    interventions: list[str] | None = None,
) -> Trial:
    return Trial(
        trial_id=trial_id,
        title=title,
        phase="Phase 2",
        summary=summary,
        conditions=conditions or [],
        intervention_names=interventions or [],
        locations=[],
        rules=[],
    )


def test_retrieval_prioritizes_matching_disease_and_treatment() -> None:
    trials = [
        make_trial(
            "LUNG",
            title="Study of osimertinib in EGFR-positive NSCLC",
            conditions=["Non-small cell lung cancer"],
            interventions=["Osimertinib"],
        ),
        make_trial(
            "BREAST",
            title="Endocrine therapy in breast cancer",
            conditions=["Breast cancer"],
            interventions=["Fulvestrant"],
        ),
        make_trial(
            "COLON",
            title="Immunotherapy in colorectal cancer",
            conditions=["Colorectal cancer"],
            interventions=["Pembrolizumab"],
        ),
    ]

    selected = retrieve_trials(
        trials,
        "Patient has EGFR-positive non-small cell lung cancer and is considering osimertinib.",
        [PatientFact(field="diagnosis", value="NSCLC", source_text="NSCLC")],
        limit=1,
    )

    assert [trial.trial_id for trial in selected] == ["LUNG"]


def test_retrieval_returns_every_trial_when_below_limit() -> None:
    trials = [
        make_trial("A", title="Trial A"),
        make_trial("B", title="Trial B"),
    ]

    assert retrieve_trials(trials, "patient note", [], limit=25) == trials
