"""Tests for ResetAgent. The database and the AI are replaced by fakes."""
from unittest import mock

from django.test import SimpleTestCase

from core.agents.llm_client import LLMResult
from core.agents.reset_agent import ResetAgent, build_stats_data


def overview(total=30, departments=None, symptoms=None):
    return {
        'total': total,
        'at_risk_pct': 73,
        'split': [{'label': 'Stable', 'count': 8}, {'label': 'Challenged', 'count': 14}, {'label': 'Critical', 'count': 8}],
        'departments': departments if departments is not None else [
            {'department': 'CSE', 'total': 9, 'at_risk_pct': 89},
            {'department': 'EEE', 'total': 7, 'at_risk_pct': 71},
        ],
        'symptoms': symptoms if symptoms is not None else [{'label': 'trouble relaxing', 'count': 12, 'pct': 40}],
    }


class BuildStatsDataTests(SimpleTestCase):
    def test_counts_and_tops(self):
        data = build_stats_data('Fall 2026', overview())
        self.assertEqual((data['total'], data['stable'], data['challenged'], data['critical']), (30, 8, 14, 8))
        self.assertEqual(data['top_symptom'], 'trouble relaxing')
        self.assertEqual(data['top_department'], 'CSE')
        self.assertEqual(data['at_risk_pct'], 73)

    def test_tiny_departments_are_not_named(self):
        data = build_stats_data('Fall 2026', overview(departments=[{'department': 'ECO', 'total': 2, 'at_risk_pct': 100}]))
        self.assertIsNone(data['top_department'])

    def test_ties_are_broken_alphabetically(self):
        deps = [{'department': 'EEE', 'total': 5, 'at_risk_pct': 80}, {'department': 'BBA', 'total': 5, 'at_risk_pct': 80}]
        self.assertEqual(build_stats_data('S', overview(departments=deps))['top_department'], 'BBA')

    def test_empty_semester(self):
        data = build_stats_data('Fall 2026', {'total': 0, 'split': [], 'departments': [], 'symptoms': []})
        self.assertEqual((data['total'], data['stable'], data['top_symptom']), (0, 0, None))

    def test_no_personal_fields(self):
        data = build_stats_data('Fall 2026', overview())
        self.assertFalse({'name', 'email', 'student_id'} & set(data))


class SummaryTests(SimpleTestCase):
    def test_ai_text_is_used_when_available(self):
        llm = mock.Mock()
        llm.chat_with_strategy.return_value = LLMResult('AI summary', True)
        self.assertEqual(ResetAgent(llm=llm)._summary(build_stats_data('S', overview())), ('AI summary', True))

    def test_fallback_when_ai_is_down(self):
        llm = mock.Mock()
        llm.chat_with_strategy.return_value = LLMResult('built-in text', False)
        self.assertEqual(ResetAgent(llm=llm)._summary(build_stats_data('S', overview())), ('built-in text', False))

    def test_ai_is_not_asked_about_an_empty_semester(self):
        llm = mock.Mock()
        text, from_ai = ResetAgent(llm=llm)._summary(build_stats_data('S', {'total': 0, 'split': [], 'departments': [], 'symptoms': []}))
        llm.chat_with_strategy.assert_not_called()
        self.assertFalse(from_ai)
        self.assertIn('0 students', text)