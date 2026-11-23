"""
ResetAgent — moves the whole system from the current semester to a later one.

In order:
  1. compile the closing semester's anonymous figures (totals, split, at-risk %, top concern, top department)
  2. ask the AI for a short summary (SemesterSummaryStrategy, through chat_with_strategy);
     if the AI is unavailable, the built-in wording is saved instead
  3. in ONE database transaction: save the figures + summary to semester_stats, mark the semester
     compiled, close its open appointments (pending -> declined, accepted -> completed) and make the
     target semester the current one

Nothing is deleted. The old semester's check-ins, alerts and appointments stay in the database
under its name; students simply start the new semester with an empty check-in.
Only percentages, counts and a symptom/department name are sent to the AI, never any student detail.
"""
from core.agents.llm_client import LLMClient
from core.agents.strategies import SemesterSummaryStrategy
from core.components import ALERT_MIN_DEPARTMENT_RESPONDENTS
from core.db import connect_db, get_current_semester
from core.utils import semester_overview, semester_overview_empty


class TransitionError(Exception):
    """The transition cannot be done; the message is safe to show to the admin."""


def build_stats_data(semester: str, overview: dict) -> dict:
    """The figures for semester_stats and for the summary prompt. Pure function (easy to test)."""
    counts = {item['label'].lower(): item['count'] for item in overview.get('split', [])}
    departments = [d for d in overview.get('departments', []) if d['total'] >= ALERT_MIN_DEPARTMENT_RESPONDENTS]
    top_department = min(departments, key=lambda d: (-d['at_risk_pct'], d['department']))['department'] if departments else None
    symptoms = overview.get('symptoms', [])
    return {
        'semester': semester,
        'total': overview.get('total', 0),
        'stable': counts.get('stable', 0),
        'challenged': counts.get('challenged', 0),
        'critical': counts.get('critical', 0),
        'at_risk_pct': overview.get('at_risk_pct', 0),
        'top_symptom': symptoms[0]['label'] if symptoms else None,
        'top_department': top_department,
    }


class ResetAgent:

    def __init__(self, llm=None, strategy=None):
        self._llm = llm or LLMClient()
        self._strategy = strategy or SemesterSummaryStrategy()

    def run(self, target: str, expected_current) -> dict:
        """
        Do the transition. `expected_current` is the semester the admin saw on the page; if the
        active semester is no longer that one (someone else already did it), nothing happens.
        Returns {'closed_semester', 'target', 'summary', 'from_ai', 'declined', 'completed'}.
        """
        conn = connect_db()
        try:
            with conn.cursor() as cur:
                current = get_current_semester(cur)
                self._check(cur, current, expected_current, target)
                data, summary, from_ai = None, None, False
                if current:
                    overview = semester_overview(cur, current)
                    data = build_stats_data(current, overview)
                    summary, from_ai = self._summary(data)
                conn.rollback()                       # end the read-only phase before locking

                result = self._apply(cur, current, target, data, summary)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        result.update({'closed_semester': current, 'target': target, 'summary': summary, 'from_ai': from_ai})
        return result

    # ── steps ────────────────────────────────────────────────────────────────

    @staticmethod
    def _check(cur, current, expected_current, target):
        if current != expected_current:
            raise TransitionError('The active semester has changed since you opened this page. Please review and try again.')
        cur.execute("SELECT start_date FROM semester_schedule WHERE semester = %s", (target,))
        target_row = cur.fetchone()
        if target_row is None:
            raise TransitionError('That semester is not in the schedule.')
        if current is None:
            return
        if target == current:
            raise TransitionError('That semester is already the active one.')
        cur.execute("SELECT start_date FROM semester_schedule WHERE semester = %s", (current,))
        if target_row['start_date'] <= cur.fetchone()['start_date']:
            raise TransitionError('You can only move forward to a semester that starts after the current one.')

    def _summary(self, data: dict):
        """(text, from_ai). With no check-ins there is nothing to summarise, so the AI is not asked."""
        if not data['total']:
            return self._strategy.build_fallback(data), False
        result = self._llm.chat_with_strategy(self._strategy, data)
        return result.text, result.from_ai

    @staticmethod
    def _apply(cur, current, target, data, summary) -> dict:
        """All the database changes, in the caller's single transaction."""
        # Lock the schedule so two admins (or a double click) cannot run this at the same time.
        cur.execute("SELECT id FROM semester_schedule WHERE is_current = TRUE FOR UPDATE")
        locked = cur.fetchone()
        if (locked is not None) != (current is not None) or (current and get_current_semester(cur) != current):
            raise TransitionError('The active semester has changed. Please review and try again.')

        declined = completed = 0
        if current:
            cur.execute(
                "INSERT INTO semester_stats (semester, total, stable, challenged, critical, at_risk_pct, llm_summary) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (semester) DO UPDATE SET total = EXCLUDED.total, stable = EXCLUDED.stable, "
                "  challenged = EXCLUDED.challenged, critical = EXCLUDED.critical, "
                "  at_risk_pct = EXCLUDED.at_risk_pct, llm_summary = EXCLUDED.llm_summary, compiled_at = NOW()",
                (current, data['total'], data['stable'], data['challenged'], data['critical'],
                 data['at_risk_pct'], summary),
            )
            cur.execute("UPDATE semester_schedule SET stats_compiled = TRUE WHERE semester = %s", (current,))
            cur.execute("UPDATE appointments SET status = 'declined', is_new = FALSE WHERE status = 'pending'")
            declined = cur.rowcount
            cur.execute("UPDATE appointments SET status = 'completed' WHERE status = 'accepted'")
            completed = cur.rowcount

        cur.execute("UPDATE semester_schedule SET is_current = FALSE WHERE is_current = TRUE")
        cur.execute("UPDATE semester_schedule SET is_current = TRUE WHERE semester = %s", (target,))
        return {'declined': declined, 'completed': completed}