"""Tests for the LLM strategies and the alert factory. No network, no database."""
from django.test import SimpleTestCase

from core.agents.strategies import (
    AlertStrategyFactory,
    CriticalSurgeAlertStrategy,
    DepartmentAtRiskAlertStrategy,
    LLMStrategy,
    SemesterSummaryStrategy,
    StatusDescriptionStrategy,
    SymptomSpikeAlertStrategy,
)

STATUS_DATA = {'status': 'Challenged', 'stress_level': 'high', 'anxiety_level': 'moderate',
               'mood_level': 'mild', 'top_areas': ['academic pressure', 'sleep']}
SURGE = {'semester': 'Fall 2026', 'critical_pct': 45.5, 'total': 40, 'previous_pct': 20.0}
SPIKE = {'semester': 'Fall 2026', 'previous_semester': 'Summer 2026', 'symptom': 'Trouble sleeping'}
DEPT = {'semester': 'Fall 2026', 'department': 'CSE', 'at_risk_pct': 72.0, 'total': 25}
SUMMARY = {'semester': 'Fall 2026', 'total': 40, 'stable': 10, 'challenged': 20, 'critical': 10,
           'at_risk_pct': 75.0, 'top_symptom': 'Trouble sleeping', 'top_department': 'EEE'}

ALL = [
    (StatusDescriptionStrategy, STATUS_DATA, 200),
    (CriticalSurgeAlertStrategy, SURGE, 120),
    (SymptomSpikeAlertStrategy, SPIKE, 120),
    (DepartmentAtRiskAlertStrategy, DEPT, 120),
    (SemesterSummaryStrategy, SUMMARY, 220),
]


class TestStrategyContract(SimpleTestCase):

    def test_base_class_is_abstract(self):
        with self.assertRaises(TypeError):
            LLMStrategy()

    def test_token_budgets_match_the_spec(self):
        for cls, _, tokens in ALL:
            with self.subTest(cls=cls.__name__):
                self.assertEqual(cls().max_tokens, tokens)

    def test_every_strategy_uses_the_project_defaults(self):
        for cls, _, _ in ALL:
            with self.subTest(cls=cls.__name__):
                s = cls()
                self.assertEqual(s.temperature, 0.50)
                self.assertEqual(s.reasoning_effort, 'low')

    def test_every_strategy_builds_prompts_and_a_fallback(self):
        for cls, data, _ in ALL:
            with self.subTest(cls=cls.__name__):
                s = cls()
                self.assertTrue(s.build_system_prompt().strip())
                self.assertTrue(s.build_user_prompt(data).strip())
                self.assertTrue(s.build_fallback(data).strip())

    def test_system_prompt_is_fixed_and_never_contains_the_data(self):
        for cls, data, _ in ALL:
            with self.subTest(cls=cls.__name__):
                s = cls()
                self.assertEqual(s.build_system_prompt(), cls().build_system_prompt())
                self.assertNotIn('Fall 2026', s.build_system_prompt())

    def test_fallbacks_never_need_the_ai_or_raise_on_missing_keys(self):
        for cls, _, _ in ALL:
            with self.subTest(cls=cls.__name__):
                self.assertIsInstance(cls().build_fallback({}), str)
                self.assertIsInstance(cls().build_user_prompt({}), str)


class TestStatusDescriptionStrategy(SimpleTestCase):

    def test_prompt_contains_status_levels_and_areas(self):
        prompt = StatusDescriptionStrategy().build_user_prompt(STATUS_DATA)
        for fragment in ('Challenged', 'high', 'moderate', 'mild', 'academic pressure', 'sleep'):
            self.assertIn(fragment, prompt)

    def test_identifying_keys_are_never_put_in_the_prompt(self):
        data = dict(STATUS_DATA, full_name='Alex Johnson', email='alex@x.edu', student_id='2021-1-60-001')
        prompt = StatusDescriptionStrategy().build_user_prompt(data)
        for secret in ('Alex', 'alex@x.edu', '2021-1-60-001'):
            self.assertNotIn(secret, prompt)

    def test_fallback_is_the_builtin_text_for_each_status(self):
        s = StatusDescriptionStrategy()
        texts = {st: s.build_fallback({'status': st}) for st in ('Stable', 'Challenged', 'Critical')}
        self.assertEqual(len(set(texts.values())), 3)
        self.assertEqual(s.build_fallback({'status': 'Nonsense'}), texts['Stable'])

    def test_system_prompt_forbids_diagnosis_and_medication(self):
        prompt = StatusDescriptionStrategy().build_system_prompt().lower()
        self.assertIn('do not diagnose', prompt)
        self.assertIn('medication', prompt)

    def test_no_areas_is_handled(self):
        self.assertIn('none stood out', StatusDescriptionStrategy().build_user_prompt({'status': 'Stable', 'top_areas': []}))


class TestAlertAndSummaryStrategies(SimpleTestCase):

    def test_critical_surge_texts_use_the_numbers(self):
        s = CriticalSurgeAlertStrategy()
        self.assertIn('45.5', s.build_user_prompt(SURGE))
        self.assertIn('20.0', s.build_user_prompt(SURGE))
        self.assertIn('45.5%', s.build_fallback(SURGE))
        self.assertIn('40%', s.build_fallback(SURGE))

    def test_critical_surge_without_previous_semester(self):
        data = {k: v for k, v in SURGE.items() if k != 'previous_pct'}
        self.assertNotIn('Previous semester', CriticalSurgeAlertStrategy().build_user_prompt(data))

    def test_symptom_spike_texts(self):
        s = SymptomSpikeAlertStrategy()
        self.assertIn('Trouble sleeping', s.build_user_prompt(SPIKE))
        self.assertIn('Summer 2026', s.build_fallback(SPIKE))

    def test_department_at_risk_texts(self):
        s = DepartmentAtRiskAlertStrategy()
        self.assertIn('CSE', s.build_user_prompt(DEPT))
        self.assertIn('72.0%', s.build_fallback(DEPT))
        self.assertIn('60%', s.build_fallback(DEPT))

    def test_semester_summary_includes_optional_lines_only_when_given(self):
        s = SemesterSummaryStrategy()
        self.assertIn('Trouble sleeping', s.build_user_prompt(SUMMARY))
        self.assertIn('EEE', s.build_user_prompt(SUMMARY))
        bare = {k: v for k, v in SUMMARY.items() if not k.startswith('top_')}
        self.assertNotIn('Most reported symptom', s.build_user_prompt(bare))
        self.assertIn('10 Critical', s.build_fallback(SUMMARY))


class TestFinalize(SimpleTestCase):

    def setUp(self):
        self.s = StatusDescriptionStrategy()

    def test_empty_or_none_is_unusable(self):
        for bad in (None, '', '   ', '***'):
            with self.subTest(bad=bad):
                self.assertIsNone(self.s.finalize(bad))

    def test_markdown_quotes_and_whitespace_are_cleaned(self):
        self.assertEqual(self.s.finalize('  "You are **doing** fine.\n\nKeep going."  '), 'You are doing fine. Keep going.')

    def test_too_long_is_unusable(self):
        self.assertIsNone(self.s.finalize('word ' * 500))


class TestAlertStrategyFactory(SimpleTestCase):

    def test_creates_the_right_class_for_each_name(self):
        expected = {
            'critical_surge': CriticalSurgeAlertStrategy,
            'symptom_spike': SymptomSpikeAlertStrategy,
            'department_at_risk': DepartmentAtRiskAlertStrategy,
        }
        for name, cls in expected.items():
            with self.subTest(name=name):
                self.assertIsInstance(AlertStrategyFactory.create(name), cls)

    def test_unknown_name_raises(self):
        with self.assertRaisesMessage(ValueError, 'Unknown alert type: nope'):
            AlertStrategyFactory.create('nope')

    def test_each_call_returns_a_new_instance(self):
        self.assertIsNot(AlertStrategyFactory.create('critical_surge'), AlertStrategyFactory.create('critical_surge'))

    def test_created_strategies_are_llm_strategies(self):
        self.assertIsInstance(AlertStrategyFactory.create('symptom_spike'), LLMStrategy)