from __future__ import annotations

import re
from collections.abc import Iterable

from app.models import PatientFact


FIELD_VOCABULARY = {
    "age_years",
    "sex",
    "diagnosis",
    "stage",
    "histology",
    "ecog",
    "measurable_disease",
    "unresectable_disease",
    "metastatic_disease",
    "liver_metastases",
    "life_expectancy_months",
    "tumor_tissue_available",
    "creatinine_mg_dl",
    "creatinine_clearance_ml_min",
    "bilirubin_mg_dl",
    "bilirubin_uln_multiple",
    "alt_uln_multiple",
    "ast_uln_multiple",
    "alp_uln_multiple",
    "anc_10e9_l",
    "platelets_10e9_l",
    "hemoglobin_g_dl",
    "lvef_pct",
    "prior_systemic_therapy",
    "prior_therapy_lines",
    "prior_platinum_therapy",
    "prior_pd1_pdl1_therapy",
    "prior_docetaxel_therapy",
    "prior_taxane_therapy",
    "prior_anthracycline_therapy",
    "prior_endocrine_therapy",
    "prior_her2_therapy",
    "prior_cdk4_6_inhibitor",
    "prior_fluoropyrimidine_therapy",
    "prior_oxaliplatin_therapy",
    "prior_irinotecan_therapy",
    "prior_anti_vegf_therapy",
    "prior_anti_egfr_therapy",
    "prior_ctla4_therapy",
    "prior_tim3_therapy",
    "disease_progression_after_platinum",
    "disease_progression_after_pd1_pdl1",
    "rapid_progression_weeks",
    "treatment_toxicity_grade",
    "radiation_lung_gy",
    "radiation_within_days",
    "palliative_radiation_within_days",
    "brain_mets_active",
    "brain_mets_stable",
    "leptomeningeal_disease",
    "corticosteroid_free_days",
    "biomarkers",
    "er_positive",
    "pr_positive",
    "her2_positive",
    "triple_negative_breast_cancer",
    "brca1_mutation",
    "brca2_mutation",
    "pik3ca_mutation",
    "kras_mutation",
    "nras_mutation",
    "braf_v600e_mutation",
    "msi_high",
    "mmr_deficient",
    "pd_l1_expression_pct",
    "menopausal_status",
    "egfr_sensitizing_mutation",
    "alk_rearrangement",
    "ros1_rearrangement",
    "hepatitis_b_active",
    "hepatitis_c_active",
    "hiv_positive",
    "autoimmune_disease_active",
    "immunocompromised",
    "systemic_immunosuppression",
    "interstitial_lung_disease",
    "pneumonitis_history",
    "pleural_effusion_symptomatic",
    "ascites_symptomatic",
    "peripheral_neuropathy_grade",
    "live_vaccine_within_days",
    "can_interrupt_nsaids",
    "other_malignancy_active",
    "pregnant",
    "breastfeeding",
    "contraception_agreement",
}


class DemoFactExtractor:
    """Offline extractor for the demo vocabulary.

    Production deployments can replace this class with a Bedrock implementation.
    The evaluator only depends on the PatientFact contract.
    """

    _sentence_splitter = re.compile(r"(?<=[.!?])\s+|\n+")

    def extract(self, note: str) -> list[PatientFact]:
        sentences = [part.strip() for part in self._sentence_splitter.split(note) if part.strip()]
        facts: dict[str, PatientFact] = {}

        age = self._search(sentences, r"\b(\d{1,3})\s*[- ]?year[- ]old\b")
        if age:
            self._put(facts, "age_years", int(age.group(1)), age.string)

        sex = self._search(sentences, r"\b(woman|female|man|male)\b")
        if sex:
            value = "female" if sex.group(1).lower() in {"woman", "female"} else "male"
            self._put(facts, "sex", value, sex.string)

        diagnosis = self._search(
            sentences,
            r"\b(non[- ]small cell lung cancer|NSCLC)\b",
            re.IGNORECASE,
        )
        if diagnosis:
            self._put(facts, "diagnosis", "NSCLC", diagnosis.string)

        stage = self._search(sentences, r"\bstage\s+(I{1,3}|IV|[1-4])\b", re.IGNORECASE)
        if stage:
            value = stage.group(1).upper()
            value = {"1": "I", "2": "II", "3": "III", "4": "IV"}.get(value, value)
            self._put(facts, "stage", value, stage.string)

        histology = self._search(sentences, r"\b(adenocarcinoma|squamous)\b", re.IGNORECASE)
        if histology:
            self._put(facts, "histology", histology.group(1).lower(), histology.string)

        self._numeric_fact(facts, sentences, "ecog", r"\bECOG(?:\s+performance status)?\s*[:=]?\s*([0-4])\b", int)
        self._numeric_fact(
            facts,
            sentences,
            "creatinine_mg_dl",
            r"\bcreatinine\s*[:=]?\s*(\d+(?:\.\d+)?)\s*mg/dL\b",
            float,
        )
        self._numeric_fact(
            facts,
            sentences,
            "bilirubin_mg_dl",
            r"\bbilirubin\s*[:=]?\s*(\d+(?:\.\d+)?)\s*mg/dL\b",
            float,
        )
        self._numeric_fact(
            facts,
            sentences,
            "lvef_pct",
            r"\b(?:LVEF|left ventricular ejection fraction)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?",
            float,
        )

        prior_none = self._search(
            sentences,
            r"\b(no|without)\s+prior\s+(?:systemic\s+)?(?:therapy|treatment)\b",
            re.IGNORECASE,
        )
        prior_yes = self._search(
            sentences,
            r"\b(?:received|had|after)\s+prior\s+(?:systemic\s+)?(?:therapy|treatment)\b",
            re.IGNORECASE,
        )
        if prior_none:
            self._put(facts, "prior_systemic_therapy", False, prior_none.string)
        elif prior_yes:
            self._put(facts, "prior_systemic_therapy", True, prior_yes.string)

        brain_none = self._search(
            sentences,
            r"\b(?:no|without)\s+(?:known\s+)?active\s+brain\s+metasta",
            re.IGNORECASE,
        )
        brain_yes = self._search(sentences, r"\bactive\s+brain\s+metasta", re.IGNORECASE)
        if brain_none:
            self._put(facts, "brain_mets_active", False, brain_none.string)
        elif brain_yes:
            self._put(facts, "brain_mets_active", True, brain_yes.string)

        biomarker_sentence = self._first_sentence_with(
            sentences, ("EGFR", "ALK", "ROS1", "KRAS", "PD-L1")
        )
        if biomarker_sentence:
            positives: list[str] = []
            patterns = {
                "EGFR-sensitizing": r"\bEGFR\b.{0,20}\b(?:positive|mutated|mutation detected)\b",
                "ALK-positive": r"\bALK\b.{0,20}\bpositive\b",
                "ROS1-positive": r"\bROS1\b.{0,20}\bpositive\b",
                "KRAS-G12C": r"\bKRAS\s*G12C\b",
            }
            for label, pattern in patterns.items():
                if re.search(pattern, biomarker_sentence, re.IGNORECASE):
                    positives.append(label)
            self._put(facts, "biomarkers", positives, biomarker_sentence)

        return list(facts.values())

    @staticmethod
    def _search(
        sentences: Iterable[str], pattern: str, flags: int = re.IGNORECASE
    ) -> re.Match[str] | None:
        compiled = re.compile(pattern, flags)
        for sentence in sentences:
            match = compiled.search(sentence)
            if match:
                return match
        return None

    def _numeric_fact(
        self,
        facts: dict[str, PatientFact],
        sentences: list[str],
        field: str,
        pattern: str,
        cast: type[int] | type[float],
    ) -> None:
        match = self._search(sentences, pattern)
        if match:
            self._put(facts, field, cast(match.group(1)), match.string)

    @staticmethod
    def _first_sentence_with(sentences: list[str], terms: tuple[str, ...]) -> str | None:
        for sentence in sentences:
            if any(term.lower() in sentence.lower() for term in terms):
                return sentence
        return None

    @staticmethod
    def _put(
        facts: dict[str, PatientFact], field: str, value: object, source_text: str
    ) -> None:
        if field not in FIELD_VOCABULARY:
            raise ValueError(f"Unsupported field: {field}")
        facts[field] = PatientFact(field=field, value=value, source_text=source_text)
