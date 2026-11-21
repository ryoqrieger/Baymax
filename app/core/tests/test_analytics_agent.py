"""Tests for AnalyticsAgent. The database and the AI are replaced by fakes."""
from unittest import mock

from django.test import SimpleTestCase

from core.agents.analytics_agent import AnalyticsAgent, find_alerts
from core.agents.llm_client import LLMResult


def overview(total=20, critical_pct=10, top='trouble relaxing', departments=()):
    return {
        'total': total,
        'critical_pct': critical_pct,
        'symptoms': [{'label': top, 'count': 5, 'pct': 25}] if top else [],
        'departments': [dict(d, is_at_risk=d['at_risk_pct'] > 60) for d in departments],
    }


class FindAlertsTests(SimpleTestCase):

    def types(self, found):
        return sorted((a['alert_type'], a['department']) for a in found)

    def test_calm_semester_has_no_alerts(self):
        self.assertEqual(find_alerts('Fall 2026', overview()), [])

    def test_critical_surge_needs_more_than_40_percent(self):
        self.assertEqual(find_alerts('Fall 2026', overview(critical_pct=40)), [])
        found = find_alerts('Fall 2026', overview(critical_pct=41), 'Summer 2026', overview(critical_pct=12, top='irritability'))
        self.assertEqual(self.types(found), [('critical_surge', None)])
        self.assertEqual(found[0]['data']['previous_pct'], 12)

    def test_symptom_spike_when_top_symptom_repeats(self):
        found = find_alerts('Fall 2026', overview(), 'Summer 2026', overview(top='trouble relaxing'))
        self.assertEqual(self.types(found), [('symptom_spike', None)])
        self.assertEqual(found[0]['data']['symptom'], 'trouble relaxing')
        self.assertEqual(find_alerts('Fall 2026', overview(), 'Summer 2026', overview(top='irritability')), [])

    def test_symptom_spike_needs_a_previous_semester(self):
        self.assertEqual(find_alerts('Fall 2026', overview(), None, None), [])

    def test_department_at_risk_above_60_percent_only(self):
        rows = [{'department': 'CSE', 'total': 9, 'at_risk_pct': 89},
                {'department': 'EEE', 'total': 5, 'at_risk_pct': 60},
                {'department': 'BBA', 'total': 5, 'at_risk_pct': 61}]
        found = find_alerts('Fall 2026', overview(departments=rows))
        self.assertEqual(self.types(found), [('department_at_risk', 'BBA'), ('department_at_risk', 'CSE')])

    def test_tiny_samples_never_alert(self):
        self.assertEqual(find_alerts('Fall 2026', overview(total=4, critical_pct=100)), [])
        rows = [{'department': 'ECO', 'total': 2, 'at_risk_pct': 100}]
        self.assertEqual(find_alerts('Fall 2026', overview(departments=rows)), [])

    def test_alert_data_has_no_personal_identifiers(self):
        rows = [{'department': 'CSE', 'total': 9, 'at_risk_pct': 89}]
        found = find_alerts('Fall 2026', overview(critical_pct=50, departments=rows), 'Summer 2026', overview())
        for alert in found:
            self.assertFalse({'name', 'email', 'student_id'} & set(alert['data']))


class RunTests(SimpleTestCase):

    def agent(self, results, existing=()):
        llm = mock.Mock()
        llm.chat_with_strategy.side_effect = results
        agent = AnalyticsAgent(llm=llm)
        patches = [
            mock.patch('core.agents.analytics_agent.connect_db'),
            mock.patch.object(AnalyticsAgent, '_previous_semester', return_value=None),
            mock.patch.object(AnalyticsAgent, '_existing_keys', return_value=set(existing)),
            mock.patch.object(AnalyticsAgent, '_insert', return_value=1),
        ]
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        return agent, llm, mocks[3]

    def surge_and_two_departments(self):
        rows = [{'department': 'CSE', 'total': 9, 'at_risk_pct': 89},
                {'department': 'EEE', 'total': 7, 'at_risk_pct': 71}]
        return overview(critical_pct=50, departments=rows)

    def test_creates_each_alert_with_ai_text(self):
        agent, llm, insert = self.agent([LLMResult('one', True), LLMResult('two', True), LLMResult('three', True)])
        self.assertEqual(agent.run('Fall 2026', self.surge_and_two_departments()), 3)
        self.assertEqual(llm.chat_with_strategy.call_count, 3)
        self.assertEqual([c.args[3] for c in insert.call_args_list], ['one', 'two', 'three'])

    def test_existing_alerts_are_not_repeated_or_sent_to_the_ai(self):
        agent, llm, insert = self.agent([LLMResult('x', True)], existing={('critical_surge', ''), ('department_at_risk', 'CSE')})
        self.assertEqual(agent.run('Fall 2026', self.surge_and_two_departments()), 1)
        self.assertEqual(llm.chat_with_strategy.call_count, 1)
        self.assertEqual(insert.call_args.args[2]['department'], 'EEE')

    def test_after_one_ai_failure_the_rest_use_built_in_text(self):
        fallback = LLMResult('built-in surge text', False)
        agent, llm, insert = self.agent([fallback])
        self.assertEqual(agent.run('Fall 2026', self.surge_and_two_departments()), 3)
        self.assertEqual(llm.chat_with_strategy.call_count, 1)        # no second wait on a broken AI
        texts = [c.args[3] for c in insert.call_args_list]
        self.assertEqual(texts[0], 'built-in surge text')
        self.assertTrue(all(texts))                                   # every alert has wording