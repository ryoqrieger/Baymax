"""
AnalyticsAgent — checks a semester's anonymous figures against three thresholds
and saves an alert (worded by the AI) for each one that is crossed.

    Critical Surge      Critical share of respondents above CRITICAL_SURGE_PCT
    Symptom Spike       the single most-reported concern is the same as last semester's
    Department at Risk  Challenged + Critical share of a department above DEPARTMENT_AT_RISK_PCT

It contains no prompt text: wording lives in the alert strategies, which are
created through AlertStrategyFactory. The only AI call is chat_with_strategy().
Only percentages, department codes and a symptom phrase are sent — never a
name, email or student ID.

Each (semester, alert type, department) is saved once and never repeated, even
if it was dismissed. If the AI is unavailable the built-in wording is saved, so
the alert still appears.
"""
import logging

from core.agents.llm_client import LLMClient
from core.agents.strategies import AlertStrategyFactory
from core.components import (
    ALERT_MIN_DEPARTMENT_RESPONDENTS,
    ALERT_MIN_RESPONDENTS,
    CRITICAL_SURGE_PCT,
)
from core.db import connect_db
from core.utils import semester_overview

logger = logging.getLogger(__name__)


def find_alerts(semester, overview, previous_semester=None, previous_overview=None) -> list:
    """
    Which alerts the figures call for: [{'alert_type', 'department', 'data'}].
    Pure function (no database, no AI) so it is easy to test.
    """
    total = overview.get('total', 0)
    if total < ALERT_MIN_RESPONDENTS:
        return []

    found = []
    if overview['critical_pct'] > CRITICAL_SURGE_PCT:
        found.append({
            'alert_type': 'critical_surge',
            'department': None,
            'data': {
                'semester': semester,
                'critical_pct': overview['critical_pct'],
                'total': total,
                'previous_pct': previous_overview['critical_pct'] if previous_overview and previous_overview.get('total') else None,
            },
        })

    if previous_overview and previous_overview.get('symptoms') and overview['symptoms']:
        top, previous_top = overview['symptoms'][0]['label'], previous_overview['symptoms'][0]['label']
        if top == previous_top:
            found.append({
                'alert_type': 'symptom_spike',
                'department': None,
                'data': {'semester': semester, 'previous_semester': previous_semester, 'symptom': top},
            })

    for row in overview['departments']:
        if row['is_at_risk'] and row['total'] >= ALERT_MIN_DEPARTMENT_RESPONDENTS:
            found.append({
                'alert_type': 'department_at_risk',
                'department': row['department'],
                'data': {
                    'semester': semester,
                    'department': row['department'],
                    'at_risk_pct': row['at_risk_pct'],
                    'total': row['total'],
                },
            })
    return found


class AnalyticsAgent:

    def __init__(self, llm=None):
        self._llm = llm or LLMClient()

    def run(self, semester: str, overview: dict = None) -> int:
        """Create every missing alert for the semester. Returns how many were created."""
        conn = connect_db()
        try:
            with conn.cursor() as cur:
                overview = overview or semester_overview(cur, semester)
                previous_semester = self._previous_semester(cur, semester)
                previous_overview = semester_overview(cur, previous_semester) if previous_semester else None
                wanted = find_alerts(semester, overview, previous_semester, previous_overview)
                existing = self._existing_keys(cur, semester)

                created, ai_down = 0, False
                for alert in wanted:
                    key = (alert['alert_type'], alert['department'] or '')
                    if key in existing:
                        continue
                    strategy = AlertStrategyFactory.create(alert['alert_type'])
                    if ai_down:                       # one failure is enough; don't wait on the AI again
                        text = strategy.build_fallback(alert['data'])
                    else:
                        result = self._llm.chat_with_strategy(strategy, alert['data'])
                        text, ai_down = result.text, not result.from_ai
                    created += self._insert(cur, semester, alert, text)
            conn.commit()
            return created
        finally:
            conn.close()

    @staticmethod
    def _previous_semester(cur, semester):
        """The most recent earlier semester that has check-ins."""
        cur.execute(
            "SELECT semester FROM semester_schedule "
            "WHERE start_date < (SELECT start_date FROM semester_schedule WHERE semester = %s) "
            "  AND semester IN (SELECT DISTINCT semester FROM questionnaire_responses) "
            "ORDER BY start_date DESC LIMIT 1",
            (semester,),
        )
        row = cur.fetchone()
        return row['semester'] if row else None

    @staticmethod
    def _existing_keys(cur, semester) -> set:
        cur.execute(
            "SELECT alert_type, COALESCE(department, '') AS department "
            "FROM analytics_alerts WHERE semester = %s",
            (semester,),
        )
        return {(row['alert_type'], row['department']) for row in cur.fetchall()}

    @staticmethod
    def _insert(cur, semester, alert, text) -> int:
        """Insert unless an identical alert appeared in the meantime. Returns 1 if inserted."""
        cur.execute(
            "INSERT INTO analytics_alerts (alert_type, message, semester, department) "
            "SELECT %s, %s, %s, %s WHERE NOT EXISTS ("
            "  SELECT 1 FROM analytics_alerts WHERE semester = %s AND alert_type = %s "
            "    AND COALESCE(department, '') = %s)",
            (alert['alert_type'], text, semester, alert['department'],
             semester, alert['alert_type'], alert['department'] or ''),
        )
        return cur.rowcount