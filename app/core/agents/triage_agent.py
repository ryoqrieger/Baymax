"""
TriageAgent — turns a student's saved result into (1) a short AI description
and (2) a recommended professional.

It contains no prompt text: wording lives in StatusDescriptionStrategy, and the
only LLM call is chat_with_strategy(). Only status, three level words and a few
symptom phrases are sent to the AI — never a name, email or student ID.
"""
from django.core.cache import cache

from core.agents.llm_client import LLMClient, LLMResult
from core.agents.strategies import StatusDescriptionStrategy
from core.components import (
    GAD_BANDS,
    PHQ_BANDS,
    PSS_BANDS,
    PSS_REVERSED_COLUMNS,
    QUESTIONS,
    SYMPTOM_LABELS,
    TOP_AREAS_MAX,
    TRIAGE_RETRY_SECONDS,
)
from core.db import connect_db


def _band(total: int, bands) -> str:
    for minimum, word in bands:
        if total >= minimum:
            return word
    return bands[-1][1]


def compute_levels(answers: dict) -> dict:
    """
    answers: {'pss1': 0-4, ..., 'gad1': 0-3, ..., 'phq9': 0-3}
    -> the facts the status prompt needs (level words and up to 3 standout areas).
    """
    pss = sum((4 - answers[c]) if c in PSS_REVERSED_COLUMNS else answers[c]
              for c in answers if c.startswith('pss'))
    gad = sum(answers[c] for c in answers if c.startswith('gad'))
    phq = sum(answers[c] for c in answers if c.startswith('phq'))

    top_scored = []
    for question in QUESTIONS:
        column = question['column']
        if column not in SYMPTOM_LABELS or column not in answers:
            continue
        top = max(question['valid_values'])
        share = answers[column] / top
        if share >= 0.5:                               # only answers at "fairly often" / "more than half" or above
            top_scored.append((share, question['number'], SYMPTOM_LABELS[column]))
    top_scored.sort(key=lambda item: (-item[0], item[1]))

    return {
        'stress_level': _band(pss, PSS_BANDS),
        'anxiety_level': _band(gad, GAD_BANDS),
        'mood_level': _band(phq, PHQ_BANDS),
        'top_areas': [label for _, _, label in top_scored[:TOP_AREAS_MAX]],
    }


def _cooldown_key(student_id: int, semester: str) -> str:
    return f'triage_cooldown:{student_id}:{semester}'


class TriageAgent:

    def __init__(self, llm=None, strategy=None):
        self._llm = llm or LLMClient()
        self._strategy = strategy or StatusDescriptionStrategy()

    def describe(self, student_id: int, semester: str, status: str, answers: dict) -> LLMResult:
        """
        The description for a saved result that has none yet.
        AI success -> saved once (never overwritten) and returned with from_ai=True.
        AI failure -> the strategy fallback is returned, nothing is saved, and the
        AI is not asked again for TRIAGE_RETRY_SECONDS (so the page is not slow every time).
        """
        data = dict(compute_levels(answers), status=status)

        if cache.get(_cooldown_key(student_id, semester)):
            return LLMResult(self._strategy.build_fallback(data), False)

        result = self._llm.chat_with_strategy(self._strategy, data)
        if not result.from_ai:
            cache.set(_cooldown_key(student_id, semester), 1, TRIAGE_RETRY_SECONDS)
            return result

        return LLMResult(self._save_description(student_id, semester, result.text), True)

    @staticmethod
    def _save_description(student_id: int, semester: str, text: str) -> str:
        """Store the text only if none exists yet; if another request won, use theirs."""
        conn = connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE questionnaire_responses SET status_description = %s "
                    "WHERE student_id = %s AND semester = %s AND status_description IS NULL",
                    (text, student_id, semester),
                )
                if cur.rowcount == 0:
                    cur.execute(
                        "SELECT status_description FROM questionnaire_responses "
                        "WHERE student_id = %s AND semester = %s",
                        (student_id, semester),
                    )
                    row = cur.fetchone()
                    if row and row['status_description']:
                        text = row['status_description']
            conn.commit()
        finally:
            conn.close()
        return text

    @staticmethod
    def recommend_professional(student_id: int):
        """
        The active professional with the fewest open (pending or accepted) requests,
        ties broken by name, skipping anyone this student already has an open request with.
        Returns {'id', 'full_name', 'specialization', 'open_count'} or None.
        """
        conn = connect_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT u.id, u.full_name, p.specialization, "
                    "       COUNT(a.id) FILTER (WHERE a.status IN ('pending', 'accepted')) AS open_count "
                    "FROM users u "
                    "JOIN professionals p ON p.user_id = u.id "
                    "LEFT JOIN appointments a ON a.professional_id = u.id "
                    "WHERE u.role = 'professional' AND u.is_active = TRUE "
                    "  AND NOT EXISTS (SELECT 1 FROM appointments mine "
                    "                  WHERE mine.professional_id = u.id AND mine.student_id = %s "
                    "                    AND mine.status IN ('pending', 'accepted')) "
                    "GROUP BY u.id, u.full_name, p.specialization "
                    "ORDER BY open_count, u.full_name LIMIT 1",
                    (student_id,),
                )
                return cur.fetchone()
        finally:
            conn.close()