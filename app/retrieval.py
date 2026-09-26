from __future__ import annotations

from collections import Counter
import math
import re

from app.models import PatientFact, Trial


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def retrieve_trials(
    trials: list[Trial],
    note: str,
    facts: list[PatientFact],
    limit: int,
) -> list[Trial]:
    if len(trials) <= limit:
        return trials

    query_tokens = _tokens(note)
    for fact in facts:
        query_tokens.update(_tokens(str(fact.value)))

    documents = {
        trial.trial_id: _trial_tokens(trial)
        for trial in trials
    }
    document_frequency = Counter(
        token
        for tokens in documents.values()
        for token in set(tokens)
    )
    fact_fields = {fact.field for fact in facts}
    population = len(trials)

    def score(trial: Trial) -> tuple[float, int, str]:
        tokens = documents[trial.trial_id]
        lexical = sum(
            1.0 + math.log((population + 1) / (document_frequency[token] + 1))
            for token in query_tokens & tokens
        )
        field_overlap = len(
            fact_fields
            & {rule.field for rule in trial.rules if not rule.manual_review}
        )
        return lexical + field_overlap * 0.75, field_overlap, trial.trial_id

    ranked = sorted(trials, key=score, reverse=True)
    return ranked[:limit]


def _trial_tokens(trial: Trial) -> set[str]:
    text = " ".join(
        [
            trial.title,
            trial.summary,
            *trial.conditions,
            *trial.intervention_names,
        ]
    )
    return _tokens(text)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if len(token) > 1 and token not in STOP_WORDS
    }
