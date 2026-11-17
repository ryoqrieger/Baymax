"""
Strategy pattern for every LLM interaction.

Each kind of AI text (a student's status description, an alert, a semester
summary) is one class that owns ALL of its wording:
    * the system prompt and the user-prompt builder,
    * the token budget and temperature,
    * the fallback text shown when the AI is unavailable or its reply is unusable.

Agents never contain prompt strings; they pass data to
LLMClient.chat_with_strategy(strategy, data) and use the result.

Alert strategies are created by name through AlertStrategyFactory (Factory pattern).
"""
import re
from abc import ABC, abstractmethod

from core.components import (
    CRITICAL_SURGE_PCT,
    DEPARTMENT_AT_RISK_PCT,
    STATUS_CONTENT,
    STATUS_STABLE,
)


class LLMStrategy(ABC):
    """One kind of LLM call: prompts, budget and fallback."""

    max_tokens: int = 350               # visible-answer budget (the client adds headroom for reasoning)
    temperature: float = 0.50
    reasoning_effort: str = 'low'       # Groq gpt-oss models
    max_chars: int = 900                # longer replies are treated as unusable

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Fixed instructions: who the AI is and the rules for its answer."""

    @abstractmethod
    def build_user_prompt(self, data: dict) -> str:
        """The facts for this call, built only from `data`."""

    @abstractmethod
    def build_fallback(self, data: dict) -> str | None:
        """Text to show when the AI is unavailable. None means 'show nothing'."""

    def finalize(self, text: str | None) -> str | None:
        """Clean an AI reply. Returns None when it is empty or unusable."""
        if not text:
            return None
        cleaned = re.sub(r'[*_`#>]+', '', text)              # no markdown characters
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().strip('"“”').strip()
        if not cleaned or len(cleaned) > self.max_chars:
            return None
        return cleaned


# ── 1. Student status description (TriageAgent) ──────────────────────────────

class StatusDescriptionStrategy(LLMStrategy):
    """
    data keys: status ('Stable' | 'Challenged' | 'Critical'),
               stress_level, anxiety_level, mood_level  (plain words, e.g. 'moderate'),
               top_areas (list of short phrases, may be empty).
    No names or identifiers are ever part of `data`.
    """
    max_tokens = 200
    max_chars = 600

    def build_system_prompt(self) -> str:
        return (
            "You are Baymax, a warm and supportive wellbeing companion for university students. "
            "Write a short description of a student's wellbeing check-in result. "
            "Rules: 2 to 3 sentences, at most 60 words, addressed to the student as 'you'. "
            "Use plain, kind language. Do not diagnose, do not name medical conditions, "
            "do not mention medication, and do not quote numbers or scores. "
            "If the status is Challenged or Critical, gently encourage the student to talk to "
            "someone they trust or a campus mental health professional. "
            "Reply with plain text only: no lists, no headings, no markdown, no emojis."
        )

    def build_user_prompt(self, data: dict) -> str:
        areas = ', '.join(data.get('top_areas') or []) or 'none stood out'
        return (
            f"Status: {data.get('status', STATUS_STABLE)}\n"
            f"Stress level: {data.get('stress_level', 'unknown')}\n"
            f"Anxiety level: {data.get('anxiety_level', 'unknown')}\n"
            f"Mood level: {data.get('mood_level', 'unknown')}\n"
            f"Areas affecting the student most: {areas}"
        )

    def build_fallback(self, data: dict) -> str | None:
        content = STATUS_CONTENT.get(data.get('status'))
        return content['summary'] if content else STATUS_CONTENT[STATUS_STABLE]['summary']


# ── 2-4. Authority alerts (AnalyticsAgent, Sprint 5) ─────────────────────────

_ALERT_SYSTEM_PROMPT = (
    "You write one short alert for university authorities about student wellbeing statistics. "
    "Rules: exactly 1 or 2 sentences, at most 40 words, factual and calm, "
    "using only the numbers you are given. Do not mention individual students. "
    "Reply with plain text only: no headings, no markdown, no emojis."
)


class _AlertStrategy(LLMStrategy):
    max_tokens = 120
    max_chars = 400

    def build_system_prompt(self) -> str:
        return _ALERT_SYSTEM_PROMPT


class CriticalSurgeAlertStrategy(_AlertStrategy):
    """data keys: semester, critical_pct, total, previous_pct (optional)."""

    def build_user_prompt(self, data: dict) -> str:
        previous = data.get('previous_pct')
        compare = f" Previous semester: {previous}%." if previous is not None else ''
        return (
            f"Alert type: Critical Surge. Semester: {data.get('semester')}. "
            f"{data.get('critical_pct')}% of {data.get('total')} respondents are in the Critical status "
            f"(alert threshold {CRITICAL_SURGE_PCT}%).{compare}"
        )

    def build_fallback(self, data: dict) -> str | None:
        return (
            f"Critical cases make up {data.get('critical_pct')}% of respondents in {data.get('semester')}, "
            f"above the {CRITICAL_SURGE_PCT}% alert threshold."
        )


class SymptomSpikeAlertStrategy(_AlertStrategy):
    """data keys: semester, previous_semester, symptom."""

    def build_user_prompt(self, data: dict) -> str:
        return (
            f"Alert type: Symptom Spike. The most reported symptom, \"{data.get('symptom')}\", "
            f"was the top symptom in both {data.get('previous_semester')} and {data.get('semester')}."
        )

    def build_fallback(self, data: dict) -> str | None:
        return (
            f"\"{data.get('symptom')}\" has been the most reported symptom in two semesters in a row "
            f"({data.get('previous_semester')} and {data.get('semester')})."
        )


class DepartmentAtRiskAlertStrategy(_AlertStrategy):
    """data keys: semester, department, at_risk_pct, total."""

    def build_user_prompt(self, data: dict) -> str:
        return (
            f"Alert type: Department at Risk. Semester: {data.get('semester')}. "
            f"In the {data.get('department')} department, {data.get('at_risk_pct')}% of "
            f"{data.get('total')} respondents are Challenged or Critical "
            f"(alert threshold {DEPARTMENT_AT_RISK_PCT}%)."
        )

    def build_fallback(self, data: dict) -> str | None:
        return (
            f"{data.get('department')}: {data.get('at_risk_pct')}% of respondents in {data.get('semester')} "
            f"are Challenged or Critical, above the {DEPARTMENT_AT_RISK_PCT}% alert threshold."
        )


# ── 5. End-of-semester summary (ResetAgent, Sprint 6) ────────────────────────

class SemesterSummaryStrategy(LLMStrategy):
    """data keys: semester, total, stable, challenged, critical, at_risk_pct,
    top_symptom (optional), top_department (optional)."""
    max_tokens = 220
    max_chars = 700

    def build_system_prompt(self) -> str:
        return (
            "You write the end-of-semester wellbeing summary for university authorities. "
            "Rules: 2 to 4 sentences, at most 80 words, factual and calm, "
            "using only the numbers you are given. Do not mention individual students. "
            "Reply with plain text only: no lists, no headings, no markdown, no emojis."
        )

    def build_user_prompt(self, data: dict) -> str:
        lines = [
            f"Semester: {data.get('semester')}",
            f"Respondents: {data.get('total')}",
            f"Stable: {data.get('stable')}, Challenged: {data.get('challenged')}, Critical: {data.get('critical')}",
            f"At-risk share (Challenged + Critical): {data.get('at_risk_pct')}%",
        ]
        if data.get('top_symptom'):
            lines.append(f"Most reported symptom: {data['top_symptom']}")
        if data.get('top_department'):
            lines.append(f"Department with the highest at-risk share: {data['top_department']}")
        return '\n'.join(lines)

    def build_fallback(self, data: dict) -> str | None:
        return (
            f"{data.get('semester')}: {data.get('total')} students responded. "
            f"{data.get('stable')} Stable, {data.get('challenged')} Challenged, "
            f"{data.get('critical')} Critical ({data.get('at_risk_pct')}% at risk)."
        )


# ── Factory ──────────────────────────────────────────────────────────────────

class AlertStrategyFactory:
    """Creates the right alert strategy from its name (Factory pattern)."""

    _registry = {
        'critical_surge': CriticalSurgeAlertStrategy,
        'symptom_spike': SymptomSpikeAlertStrategy,
        'department_at_risk': DepartmentAtRiskAlertStrategy,
    }

    @classmethod
    def create(cls, alert_type: str) -> LLMStrategy:
        strategy_class = cls._registry.get(alert_type)
        if strategy_class is None:
            raise ValueError(f'Unknown alert type: {alert_type}')
        return strategy_class()