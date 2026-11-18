"""Tests for LLMClient. The Groq SDK is replaced by a fake: no network, no key, no database."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from core.agents.llm_client import LLMClient, LLMResult
from core.agents.strategies import StatusDescriptionStrategy
from core.components import LLM_REASONING_HEADROOM_TOKENS

SETTINGS = dict(GROQ_API_KEY='gsk_secret_key', GROQ_MODEL='test/model',
                GROQ_TIMEOUT=7, GROQ_BASE_URL='https://example.test/v1')
DATA = {'status': 'Challenged', 'stress_level': 'high', 'anxiety_level': 'mild', 'mood_level': 'mild', 'top_areas': []}


def reply(text, finish='stop', choices=True):
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message, finish_reason=finish)
    return SimpleNamespace(choices=[choice] if choices else [])


@override_settings(**SETTINGS)
class LLMClientTestCase(SimpleTestCase):

    def setUp(self):
        LLMClient._instance = None
        patcher = mock.patch('openai.OpenAI')
        self.OpenAI = patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: setattr(LLMClient, '_instance', None))
        self.create = self.OpenAI.return_value.chat.completions.create
        self.create.return_value = reply('You are doing your best this semester.')


class TestSingleton(LLMClientTestCase):

    def test_there_is_only_one_instance(self):
        self.assertIs(LLMClient(), LLMClient())

    def test_no_groq_client_is_created_until_the_first_call(self):
        LLMClient()
        self.OpenAI.assert_not_called()

    def test_the_groq_client_is_created_once_with_the_env_settings(self):
        client = LLMClient()
        client.chat('s', 'u', 100, 0.5)
        client.chat('s', 'u', 100, 0.5)
        self.OpenAI.assert_called_once_with(
            api_key='gsk_secret_key', base_url='https://example.test/v1', timeout=7, max_retries=0)


class TestChat(LLMClientTestCase):

    def test_returns_the_stripped_reply(self):
        self.create.return_value = reply('  Hello there.  ')
        self.assertEqual(LLMClient().chat('s', 'u', 100, 0.5), 'Hello there.')

    def test_request_is_adapted_to_the_groq_interface(self):
        LLMClient().chat('SYSTEM', 'USER', 200, 0.5, reasoning_effort='low')
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs['model'], 'test/model')
        self.assertEqual(kwargs['messages'], [{'role': 'system', 'content': 'SYSTEM'},
                                              {'role': 'user', 'content': 'USER'}])
        self.assertEqual(kwargs['max_completion_tokens'], 200 + LLM_REASONING_HEADROOM_TOKENS)
        self.assertEqual(kwargs['temperature'], 0.5)
        self.assertEqual(kwargs['extra_body'], {'reasoning_effort': 'low'})

    def test_an_exception_gives_none_and_never_leaks_the_key(self):
        self.create.side_effect = RuntimeError('bad key gsk_secret_key rejected')
        client = LLMClient()
        self.assertIsNone(client.chat('s', 'u', 100, 0.5))
        self.assertIn('RuntimeError', client.last_error)
        self.assertNotIn('gsk_secret_key', client.last_error)

    def test_empty_text_gives_none(self):
        for empty in ('', '   ', None):
            with self.subTest(empty=empty):
                self.create.return_value = reply(empty)
                self.assertIsNone(LLMClient().chat('s', 'u', 100, 0.5))

    def test_a_cut_off_reply_gives_none(self):
        self.create.return_value = reply('The answer was cut o', finish='length')
        client = LLMClient()
        self.assertIsNone(client.chat('s', 'u', 100, 0.5))
        self.assertIn('CutOff', client.last_error)

    def test_no_choices_gives_none(self):
        self.create.return_value = reply('x', choices=False)
        self.assertIsNone(LLMClient().chat('s', 'u', 100, 0.5))

    def test_failing_to_build_the_sdk_client_gives_none(self):
        self.OpenAI.side_effect = ImportError('no module')
        self.assertIsNone(LLMClient().chat('s', 'u', 100, 0.5))

    def test_a_success_clears_the_previous_error(self):
        client = LLMClient()
        self.create.side_effect = RuntimeError('boom')
        client.chat('s', 'u', 100, 0.5)
        self.create.side_effect = None
        client.chat('s', 'u', 100, 0.5)
        self.assertIsNone(client.last_error)


class TestChatWithStrategy(LLMClientTestCase):

    def setUp(self):
        super().setUp()
        self.strategy = StatusDescriptionStrategy()

    def test_a_good_reply_is_used(self):
        self.create.return_value = reply('You are carrying a lot. Talking to someone could help.')
        result = LLMClient().chat_with_strategy(self.strategy, DATA)
        self.assertEqual(result, LLMResult('You are carrying a lot. Talking to someone could help.', True))

    def test_the_strategy_supplies_prompts_and_budget(self):
        LLMClient().chat_with_strategy(self.strategy, DATA)
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs['messages'][0]['content'], self.strategy.build_system_prompt())
        self.assertEqual(kwargs['messages'][1]['content'], self.strategy.build_user_prompt(DATA))
        self.assertEqual(kwargs['max_completion_tokens'], self.strategy.max_tokens + LLM_REASONING_HEADROOM_TOKENS)
        self.assertEqual(kwargs['temperature'], self.strategy.temperature)

    def test_a_failure_returns_the_strategy_fallback(self):
        self.create.side_effect = RuntimeError('down')
        result = LLMClient().chat_with_strategy(self.strategy, DATA)
        self.assertFalse(result.from_ai)
        self.assertEqual(result.text, self.strategy.build_fallback(DATA))

    def test_an_unusable_reply_returns_the_fallback(self):
        for bad in ('***', 'word ' * 500):
            with self.subTest(bad=bad[:10]):
                self.create.return_value = reply(bad)
                result = LLMClient().chat_with_strategy(self.strategy, DATA)
                self.assertEqual(result, LLMResult(self.strategy.build_fallback(DATA), False))

    def test_the_reply_is_cleaned(self):
        self.create.return_value = reply('"You are **doing** fine."')
        self.assertEqual(LLMClient().chat_with_strategy(self.strategy, DATA).text, 'You are doing fine.')

    def test_a_strategy_without_fallback_gives_none_text(self):
        class NoFallback(StatusDescriptionStrategy):
            def build_fallback(self, data):
                return None

        self.create.side_effect = RuntimeError('down')
        result = LLMClient().chat_with_strategy(NoFallback(), DATA)
        self.assertEqual(result, LLMResult(None, False))