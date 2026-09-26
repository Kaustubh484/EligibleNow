from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class RuleType(str, Enum):
    inclusion = "inclusion"
    exclusion = "exclusion"


class Operator(str, Enum):
    eq = "eq"
    neq = "neq"
    lt = "lt"
    lte = "lte"
    gt = "gt"
    gte = "gte"
    in_ = "in"
    not_in = "not_in"
    present = "present"
    absent = "absent"


class Verdict(str, Enum):
    pass_ = "pass"
    fail = "fail"
    unknown = "unknown"


class PatientFact(BaseModel):
    field: str
    value: Any
    source_text: str


class Rule(BaseModel):
    trial_id: str
    rule_id: str
    type: RuleType
    field: str
    operator: Operator
    value: Any = None
    source_text: str
    manual_review: bool = False


class TrialLocation(BaseModel):
    facility: str
    city: str
    state: str


class Trial(BaseModel):
    trial_id: str
    title: str
    phase: str
    status: str = "Recruiting"
    summary: str
    conditions: list[str]
    locations: list[TrialLocation]
    rules: list[Rule]
    study_type: str = "Interventional"
    intervention_types: list[str] = Field(default_factory=list)
    intervention_names: list[str] = Field(default_factory=list)
    eligibility_hash: str | None = None
    synthetic: bool = True


class PatientExample(BaseModel):
    patient_id: str
    name: str
    label: str
    note: str
    cancer_type: str = "nsclc"


class CriterionResult(BaseModel):
    trial_id: str
    rule_id: str
    type: RuleType
    field: str
    criterion: str
    verdict: Verdict
    evidence: str | None = None
    manual_review: bool = False


class TrialResult(BaseModel):
    trial_id: str
    title: str
    phase: str
    status: str
    summary: str
    locations: list[TrialLocation]
    study_type: str
    intervention_types: list[str]
    intervention_names: list[str]
    disposition: str
    pass_count: int
    fail_count: int
    unknown_count: int
    known_match_percent: int
    criteria: list[CriterionResult]


class ActionItem(BaseModel):
    field: str
    label: str
    trial_count: int
    trial_ids: list[str]


class ScreenRequest(BaseModel):
    cancer_type: str | None = None
    retrieval_limit: int = Field(default=25, ge=5, le=100)
    patient_id: str | None = None
    note: str | None = Field(default=None, min_length=10, max_length=20_000)
    facts: list[PatientFact] | None = None

    @model_validator(mode="after")
    def require_input(self) -> "ScreenRequest":
        if not self.patient_id and not self.note and not self.facts:
            raise ValueError("Provide patient_id, note, or facts")
        return self


class ScreenResponse(BaseModel):
    cancer_type: str
    patient_id: str | None
    patient_note: str
    facts: list[PatientFact]
    results: list[TrialResult]
    actions: list[ActionItem]
    total_trial_count: int
    screened_trial_count: int
    candidate_count: int
    excluded_count: int
    disclaimer: str = (
        "Decision support only. A qualified clinical-trial coordinator must verify "
        "eligibility against the current protocol."
    )


class GuidedAnswerRequest(BaseModel):
    cancer_type: str
    note: str = Field(min_length=10, max_length=20_000)
    facts: list[PatientFact]
    answer: str = Field(min_length=1, max_length=1_000)
    retrieval_limit: int = Field(default=25, ge=5, le=100)


class GuidedAnswerResponse(BaseModel):
    screening: ScreenResponse
    resolved_action: ActionItem
    resolved_fact: PatientFact
