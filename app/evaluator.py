from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.models import (
    ActionItem,
    CriterionResult,
    Operator,
    PatientFact,
    Rule,
    RuleType,
    Trial,
    TrialResult,
    Verdict,
)


ACTION_LABELS = {
    "age_years": "Confirm date of birth",
    "sex": "Confirm administrative sex",
    "diagnosis": "Confirm cancer diagnosis",
    "stage": "Confirm current disease stage",
    "histology": "Confirm tumor histology",
    "ecog": "Document ECOG performance status",
    "measurable_disease": "Confirm measurable disease on imaging",
    "unresectable_disease": "Confirm whether disease is unresectable",
    "metastatic_disease": "Confirm metastatic disease",
    "liver_metastases": "Confirm liver metastasis status",
    "life_expectancy_months": "Document estimated life expectancy",
    "tumor_tissue_available": "Confirm archival tissue or biopsy availability",
    "creatinine_mg_dl": "Order serum creatinine",
    "creatinine_clearance_ml_min": "Calculate creatinine clearance",
    "bilirubin_mg_dl": "Order total bilirubin",
    "bilirubin_uln_multiple": "Compare bilirubin with the laboratory ULN",
    "alt_uln_multiple": "Compare ALT with the laboratory ULN",
    "ast_uln_multiple": "Compare AST with the laboratory ULN",
    "alp_uln_multiple": "Compare alkaline phosphatase with the laboratory ULN",
    "anc_10e9_l": "Order absolute neutrophil count",
    "platelets_10e9_l": "Order platelet count",
    "hemoglobin_g_dl": "Order hemoglobin",
    "lvef_pct": "Order echocardiogram for LVEF",
    "prior_systemic_therapy": "Confirm prior systemic therapy",
    "prior_therapy_lines": "Confirm number of prior therapy lines",
    "prior_platinum_therapy": "Confirm prior platinum chemotherapy",
    "prior_pd1_pdl1_therapy": "Confirm prior PD-1/PD-L1 therapy",
    "prior_docetaxel_therapy": "Confirm prior docetaxel exposure",
    "prior_taxane_therapy": "Confirm prior taxane therapy",
    "prior_anthracycline_therapy": "Confirm prior anthracycline therapy",
    "prior_endocrine_therapy": "Confirm prior endocrine therapy",
    "prior_her2_therapy": "Confirm prior HER2-directed therapy",
    "prior_cdk4_6_inhibitor": "Confirm prior CDK4/6 inhibitor therapy",
    "prior_fluoropyrimidine_therapy": "Confirm prior fluoropyrimidine therapy",
    "prior_oxaliplatin_therapy": "Confirm prior oxaliplatin therapy",
    "prior_irinotecan_therapy": "Confirm prior irinotecan therapy",
    "prior_anti_vegf_therapy": "Confirm prior anti-VEGF therapy",
    "prior_anti_egfr_therapy": "Confirm prior anti-EGFR therapy",
    "disease_progression_after_platinum": "Confirm progression after platinum therapy",
    "disease_progression_after_pd1_pdl1": "Confirm progression after PD-1/PD-L1 therapy",
    "brain_mets_active": "Confirm active brain metastasis status",
    "brain_mets_stable": "Confirm CNS disease stability",
    "leptomeningeal_disease": "Confirm leptomeningeal disease status",
    "biomarkers": "Confirm tumor biomarker results",
    "er_positive": "Confirm estrogen receptor status",
    "pr_positive": "Confirm progesterone receptor status",
    "her2_positive": "Confirm HER2 status",
    "triple_negative_breast_cancer": "Confirm triple-negative status",
    "brca1_mutation": "Confirm BRCA1 mutation status",
    "brca2_mutation": "Confirm BRCA2 mutation status",
    "pik3ca_mutation": "Confirm PIK3CA mutation status",
    "kras_mutation": "Confirm KRAS mutation status",
    "nras_mutation": "Confirm NRAS mutation status",
    "braf_v600e_mutation": "Confirm BRAF V600E mutation status",
    "msi_high": "Confirm microsatellite instability status",
    "mmr_deficient": "Confirm mismatch repair status",
    "pd_l1_expression_pct": "Confirm PD-L1 expression",
    "menopausal_status": "Confirm menopausal status",
    "egfr_sensitizing_mutation": "Confirm EGFR mutation status",
    "alk_rearrangement": "Confirm ALK rearrangement status",
    "ros1_rearrangement": "Confirm ROS1 rearrangement status",
    "hepatitis_b_active": "Order hepatitis B screening",
    "hepatitis_c_active": "Order hepatitis C screening",
    "hiv_positive": "Confirm HIV screening status",
    "autoimmune_disease_active": "Review active autoimmune disease",
    "systemic_immunosuppression": "Review systemic immunosuppressive therapy",
    "interstitial_lung_disease": "Review interstitial lung disease history",
    "pneumonitis_history": "Review pneumonitis history",
    "peripheral_neuropathy_grade": "Document peripheral neuropathy grade",
    "other_malignancy_active": "Review other active malignancies",
    "pregnant": "Confirm pregnancy status",
    "breastfeeding": "Confirm breastfeeding status",
    "contraception_agreement": "Confirm contraception requirements",
}


def evaluate_rule(rule: Rule, fact: PatientFact | None) -> CriterionResult:
    if rule.manual_review or fact is None:
        return _criterion(rule, Verdict.unknown, None if fact is None else fact.source_text)

    try:
        condition_matches = _compare(fact.value, rule.operator, rule.value)
    except (TypeError, ValueError):
        return _criterion(rule, Verdict.unknown, fact.source_text)

    if rule.type == RuleType.exclusion:
        verdict = Verdict.fail if condition_matches else Verdict.pass_
    else:
        verdict = Verdict.pass_ if condition_matches else Verdict.fail
    return _criterion(rule, verdict, fact.source_text)


def screen_trials(trials: list[Trial], facts: list[PatientFact]) -> list[TrialResult]:
    facts_by_field = {fact.field: fact for fact in facts}
    results: list[TrialResult] = []

    for trial in trials:
        criteria = [evaluate_rule(rule, facts_by_field.get(rule.field)) for rule in trial.rules]
        pass_count = sum(item.verdict == Verdict.pass_ for item in criteria)
        fail_count = sum(item.verdict == Verdict.fail for item in criteria)
        unknown_count = sum(item.verdict == Verdict.unknown for item in criteria)
        known_total = pass_count + fail_count
        known_match_percent = round(pass_count / known_total * 100) if known_total else 0

        if fail_count:
            disposition = "Not eligible on known facts"
        elif unknown_count:
            disposition = "Likely eligible - needs review"
        else:
            disposition = "Eligible on known facts"

        results.append(
            TrialResult(
                trial_id=trial.trial_id,
                title=trial.title,
                phase=trial.phase,
                status=trial.status,
                summary=trial.summary,
                locations=trial.locations,
                study_type=trial.study_type,
                intervention_types=trial.intervention_types,
                intervention_names=trial.intervention_names,
                disposition=disposition,
                pass_count=pass_count,
                fail_count=fail_count,
                unknown_count=unknown_count,
                known_match_percent=known_match_percent,
                criteria=criteria,
            )
        )

    return sorted(
        results,
        key=lambda result: (
            result.fail_count > 0,
            result.fail_count,
            result.unknown_count,
            -result.pass_count,
            result.title,
        ),
    )


def build_actions(results: list[TrialResult], candidate_limit: int = 5) -> list[ActionItem]:
    grouped: dict[str, set[str]] = defaultdict(set)
    candidates = [result for result in results if result.fail_count == 0][:candidate_limit]
    for result in candidates:
        for criterion in result.criteria:
            if criterion.verdict == Verdict.unknown:
                grouped[criterion.field].add(result.trial_id)

    actions = [
        ActionItem(
            field=field,
            label=ACTION_LABELS.get(field, f"Confirm {field.replace('_', ' ')}"),
            trial_count=len(trial_ids),
            trial_ids=sorted(trial_ids),
        )
        for field, trial_ids in grouped.items()
    ]
    return sorted(actions, key=lambda action: (-action.trial_count, action.label))


def _criterion(
    rule: Rule, verdict: Verdict, evidence: str | None
) -> CriterionResult:
    return CriterionResult(
        trial_id=rule.trial_id,
        rule_id=rule.rule_id,
        type=rule.type,
        field=rule.field,
        criterion=rule.source_text,
        verdict=verdict,
        evidence=evidence,
        manual_review=rule.manual_review,
    )


def _compare(actual: Any, operator: Operator, expected: Any) -> bool:
    if operator == Operator.present:
        return actual not in (None, "", [], {})
    if operator == Operator.absent:
        return actual in (None, "", [], {}, False)

    if operator in {Operator.lt, Operator.lte, Operator.gt, Operator.gte}:
        left = float(actual)
        right = float(expected)
        return {
            Operator.lt: left < right,
            Operator.lte: left <= right,
            Operator.gt: left > right,
            Operator.gte: left >= right,
        }[operator]

    if operator in {Operator.in_, Operator.not_in}:
        if isinstance(actual, list):
            actual_values = {_normalize(item) for item in actual}
            expected_values = (
                {_normalize(item) for item in expected}
                if isinstance(expected, list)
                else {_normalize(expected)}
            )
            matched = bool(actual_values & expected_values)
        elif isinstance(expected, list):
            if isinstance(actual, (int, float)) and not isinstance(actual, bool):
                actual_value = float(actual)
                expected_values = {
                    _numeric_or_normalized(item)
                    for item in expected
                }
            else:
                actual_value = _normalize(actual)
                expected_values = {_normalize(item) for item in expected}
            matched = actual_value in expected_values
        else:
            matched = _normalize(actual) == _normalize(expected)
        return matched if operator == Operator.in_ else not matched

    equal = _normalize(actual) == _normalize(expected)
    if operator == Operator.eq:
        return equal
    if operator == Operator.neq:
        return not equal
    raise ValueError(f"Unsupported operator: {operator}")


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        compact = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
        aliases = {
            "non small cell lung cancer": "nsclc",
            "triple negative breast cancer": "tnbc",
            "colorectal adenocarcinoma": "crc",
            "colorectal cancer": "crc",
            "stage 4": "iv",
            "4": "iv",
        }
        return aliases.get(compact, compact)
    return value


def _numeric_or_normalized(value: Any) -> Any:
    try:
        return float(value)
    except (TypeError, ValueError):
        return _normalize(value)
