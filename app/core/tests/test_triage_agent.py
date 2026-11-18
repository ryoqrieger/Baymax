"""Tests for TriageAgent. LLM, cache and database are all replaced by fakes."""
from unittest import mock

from django.test import SimpleTestCase

from core.agents.llm_client import LLMResult
from core.agents.strategies import StatusDescriptionStrategy
from core.agents.triage_agent import TriageAgent, compute_levels
from core.components import QUESTION_COLS, TRIAGE_RETRY_SECONDS


def answers(**overrides):
    base = {c: 0 for c in QUESTION_COLS}
    for c in ('pss5', 'pss6', 'pss7', 'pss8'):
        base[c] = 4                       # the calm pattern: positively worded items answered "Very Often"
    base.update(overrides)
    return base


class TestComputeLevels(SimpleTestCase):

    def test_calm_answers_are_low_everywhere(self):
        levels = compute_levels(answers())
        self.assertEqual((levels['stress_level'], levels['anxiety_level'], levels['mood_level']),
                         ('low', 'minimal', 'minimal'))
        self.assertEqual(levels['top_areas'], [])

    def test_positively_worded_pss_items_are_reversed(self):
        # Answering 0 on items 5-8 means LOW confidence -> adds 16 to the stress total.
        levels = compute_levels(answers(pss5=0, pss6=0, pss7=0, pss8=0))
        self.assertEqual(levels['stress_level'], 'moderate')        # total 16

    def test_stress_band_boundaries(self):
        for pss_sum, word in ((13, 'low'), (14, 'moderate'), (26, 'moderate'), (27, 'high')):
            with self.subTest(total=pss_sum):
                a = answers()
                remaining = pss_sum
                for c in ('pss1', 'pss2', 'pss3', 'pss4', 'pss9', 'pss10'):
                    a[c] = min(4, remaining); remaining -= a[c]
                for c in ('pss5', 'pss6', 'pss7', 'pss8'):     # each reversed item can add up to 4
                    give = min(4, remaining); a[c] = 4 - give; remaining -= give
                self.assertEqual(remaining, 0)
                self.assertEqual(compute_levels(a)['stress_level'], word)

    def test_anxiety_and_mood_bands(self):
        high = compute_levels(answers(**{f'gad{i}': 3 for i in range(1, 8)}, **{f'phq{i}': 3 for i in range(1, 10)}))
        self.assertEqual(high['anxiety_level'], 'severe')       # 21
        self.assertEqual(high['mood_level'], 'severe')          # 27
        mid = compute_levels(answers(gad1=3, gad2=3, gad3=3, gad4=1, phq1=3, phq2=3, phq3=3, phq4=1))
        self.assertEqual(mid['anxiety_level'], 'moderate')      # 10
        self.assertEqual(mid['mood_level'], 'moderate')         # 10

    def test_top_areas_are_ranked_capped_and_never_include_the_self_harm_item(self):
        a = answers(phq9=3, phq2=3, phq3=3, gad2=3, gad3=2, pss1=4, pss2=3)
        areas = compute_levels(a)['top_areas']
        self.assertEqual(len(areas), 3)
        self.assertNotIn('thoughts', ' '.join(areas))
        self.assertEqual(areas[0], 'being upset by events in academic affairs')     # pss1 4/4 ranks first

    def test_answers_below_the_halfway_point_do_not_stand_out(self):
        self.assertEqual(compute_levels(answers(gad1=1, phq1=1, pss1=1))['top_areas'], [])


def fake_connection(rowcount=1, fetchone=None):
    cursor = mock.MagicMock()
    cursor.rowcount = rowcount
    cursor.fetchone.return_value = fetchone
    conn = mock.MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


class TestDescribe(SimpleTestCase):

    def setUp(self):
        self.llm = mock.Mock()
        self.agent = TriageAgent(llm=self.llm, strategy=StatusDescriptionStrategy())
        cache_patch = mock.patch('core.agents.triage_agent.cache')
        self.cache = cache_patch.start()
        self.cache.get.return_value = None
        self.addCleanup(cache_patch.stop)

    def test_ai_success_is_saved_once_and_returned(self):
        self.llm.chat_with_strategy.return_value = LLMResult('Kind AI words.', True)
        conn, cursor = fake_connection(rowcount=1)
        with mock.patch('core.agents.triage_agent.connect_db', return_value=conn):
            result = self.agent.describe(7, 'Fall 2026', 'Challenged', answers())
        self.assertEqual(result, LLMResult('Kind AI words.', True))
        sql, params = cursor.execute.call_args.args
        self.assertIn('status_description IS NULL', sql)             # never overwrites an existing text
        self.assertEqual(params, ('Kind AI words.', 7, 'Fall 2026'))
        conn.commit.assert_called_once()

    def test_only_levels_and_status_reach_the_strategy(self):
        self.llm.chat_with_strategy.return_value = LLMResult('x', True)
        conn, _ = fake_connection()
        with mock.patch('core.agents.triage_agent.connect_db', return_value=conn):
            self.agent.describe(7, 'Fall 2026', 'Critical', answers(phq2=3))
        _, data = self.llm.chat_with_strategy.call_args.args
        self.assertEqual(set(data), {'status', 'stress_level', 'anxiety_level', 'mood_level', 'top_areas'})
        self.assertEqual(data['status'], 'Critical')

    def test_a_concurrent_request_that_saved_first_wins(self):
        self.llm.chat_with_strategy.return_value = LLMResult('My words.', True)
        conn, cursor = fake_connection(rowcount=0, fetchone={'status_description': 'Their words.'})
        with mock.patch('core.agents.triage_agent.connect_db', return_value=conn):
            result = self.agent.describe(7, 'Fall 2026', 'Challenged', answers())
        self.assertEqual(result, LLMResult('Their words.', True))

    def test_ai_failure_returns_fallback_saves_nothing_and_starts_the_wait(self):
        fallback = StatusDescriptionStrategy().build_fallback({'status': 'Challenged'})
        self.llm.chat_with_strategy.return_value = LLMResult(fallback, False)
        with mock.patch('core.agents.triage_agent.connect_db') as connect:
            result = self.agent.describe(7, 'Fall 2026', 'Challenged', answers())
        connect.assert_not_called()
        self.assertEqual(result, LLMResult(fallback, False))
        self.cache.set.assert_called_once_with('triage_cooldown:7:Fall 2026', 1, TRIAGE_RETRY_SECONDS)

    def test_during_the_wait_the_ai_is_not_called(self):
        self.cache.get.return_value = 1
        result = self.agent.describe(7, 'Fall 2026', 'Stable', answers())
        self.llm.chat_with_strategy.assert_not_called()
        self.assertFalse(result.from_ai)
        self.assertEqual(result.text, StatusDescriptionStrategy().build_fallback({'status': 'Stable'}))


class TestRecommendProfessional(SimpleTestCase):

    def test_query_is_parameterised_and_returns_the_row(self):
        row = {'id': 21, 'full_name': 'Dr. A', 'specialization': 'X', 'open_count': 0}
        conn, cursor = fake_connection(fetchone=row)
        with mock.patch('core.agents.triage_agent.connect_db', return_value=conn):
            result = TriageAgent.recommend_professional(55)
        self.assertEqual(result, row)
        sql, params = cursor.execute.call_args.args
        self.assertEqual(params, (55,))
        self.assertIn('ORDER BY open_count, u.full_name LIMIT 1', sql)
        self.assertNotIn('55', sql)
        conn.close.assert_called_once()

    def test_no_professional_gives_none(self):
        conn, _ = fake_connection(fetchone=None)
        with mock.patch('core.agents.triage_agent.connect_db', return_value=conn):
            self.assertIsNone(TriageAgent.recommend_professional(1))