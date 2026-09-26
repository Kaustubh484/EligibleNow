from app.evaluator import build_actions, evaluate_rule, screen_trials
from app.models import (
    Operator,
    PatientFact,
    Rule,
    RuleType,
    Trial,
    TrialLocation,
    Verdict,
)


def rule(
    *,
    rule_type: RuleType = RuleType.inclusion,
    field: str = "creatinine_mg_dl",
    operator: Operator = Operator.lte,
    value: object = 1.5,
    manual_review: bool = False,
) -> Rule:
    return Rule(
        trial_id="T1",
        rule_id="r1",
        type=rule_type,
        field=field,
        operator=operator,
        value=value,
        source_text="Test criterion",
        manual_review=manual_review,
    )


def fact(field: str = "creatinine_mg_dl", value: object = 1.1) -> PatientFact:
    return PatientFact(field=field, value=value, source_text="Evidence sentence")


def trial(trial_id: str, rules: list[Rule]) -> Trial:
    return Trial(
        trial_id=trial_id,
        title=trial_id,
        phase="Phase 2",
        summary="Test trial",
        conditions=["NSCLC"],
        locations=[TrialLocation(facility="Site", city="City", state="CA")],
        rules=[item.model_copy(update={"trial_id": trial_id}) for item in rules],
    )


def test_inclusion_rule_passes_and_fails() -> None:
    assert evaluate_rule(rule(), fact(value=1.1)).verdict == Verdict.pass_
    assert evaluate_rule(rule(), fact(value=2.0)).verdict == Verdict.fail


def test_exclusion_match_is_a_fail() -> None:
    exclusion = rule(
        rule_type=RuleType.exclusion,
        field="brain_mets_active",
        operator=Operator.eq,
        value=True,
    )

    assert evaluate_rule(exclusion, fact("brain_mets_active", True)).verdict == Verdict.fail
    assert evaluate_rule(exclusion, fact("brain_mets_active", False)).verdict == Verdict.pass_


def test_missing_and_manual_review_are_unknown() -> None:
    assert evaluate_rule(rule(), None).verdict == Verdict.unknown
    assert evaluate_rule(rule(manual_review=True), fact()).verdict == Verdict.unknown


def test_candidates_rank_before_hard_fails() -> None:
    trials = [
        trial("FAIL", [rule(value=0.5)]),
        trial("UNKNOWN", [rule(field="lvef_pct", operator=Operator.gte, value=50)]),
        trial("PASS", [rule()]),
    ]
    results = screen_trials(trials, [fact()])

    assert [result.trial_id for result in results] == ["PASS", "UNKNOWN", "FAIL"]


def test_actions_group_unknowns_across_candidate_trials() -> None:
    lvef_rule = rule(field="lvef_pct", operator=Operator.gte, value=50)
    results = screen_trials(
        [trial("T1", [lvef_rule]), trial("T2", [lvef_rule]), trial("T3", [rule()])],
        [fact()],
    )

    actions = build_actions(results)

    assert actions[0].field == "lvef_pct"
    assert actions[0].trial_count == 2
    assert actions[0].trial_ids == ["T1", "T2"]
