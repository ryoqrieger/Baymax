"""
LLM client: Singleton + Adapter to the Groq API.

Singleton — one LLMClient (and one HTTP client) per process, created lazily
on the first call, so importing this module is free.

Adapter — agents and strategies only know chat() / chat_with_strategy().
Everything Groq-specific (the OpenAI-compatible SDK, the address, the
reasoning parameters) stays inside this class. To change provider, change
only this file.

Nothing here raises into a view: any failure, empty reply or cut-off reply
makes chat() return None, and chat_with_strategy() then returns the
strategy's own fallback text.
"""
import logging
import threading
import time
from dataclasses import dataclass

from django.conf import settings

from core.components import LLM_REASONING_HEADROOM_TOKENS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResult:
    """What chat_with_strategy() returns."""
    text: str | None        # the AI text, or the strategy's fallback (None = show nothing)
    from_ai: bool           # True only when `text` was written by the model


class LLMClient:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._client = None          # lazy-init Groq client
                    instance.last_error = None       # short description of the latest failure
                    instance.last_duration = None    # seconds taken by the latest call
                    cls._instance = instance
        return cls._instance

    # ── internals ──
    def _get_client(self):
        if self._client is None:
            from openai import OpenAI   # imported here so merely importing this module is free
            self._client = OpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url=settings.GROQ_BASE_URL,
                timeout=settings.GROQ_TIMEOUT,
                max_retries=0,
            )
        return self._client

    def _remember_error(self, exc: Exception) -> None:
        message = str(exc).replace(settings.GROQ_API_KEY, '***')[:200]   # never keep the key
        self.last_error = f'{type(exc).__name__}: {message}'
        logger.warning('LLM call failed (%s)', type(exc).__name__)       # no prompt or answers are logged

    # ── our interface (what agents see) ──
    def chat(self, system: str, user: str, max_tokens: int, temperature: float,
             reasoning_effort: str = 'low') -> str | None:
        """One chat completion. Returns the reply text, or None if unusable."""
        self.last_error = None
        started = time.monotonic()
        try:
            response = self._get_client().chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user},
                ],
                max_completion_tokens=max_tokens + LLM_REASONING_HEADROOM_TOKENS,
                temperature=temperature,
                extra_body={'reasoning_effort': reasoning_effort},
            )
            self.last_duration = time.monotonic() - started

            if not response.choices:
                self.last_error = 'EmptyReply: the model returned no choices'
                return None
            choice = response.choices[0]
            if getattr(choice, 'finish_reason', None) == 'length':
                self.last_error = 'CutOff: the reply hit the token limit'
                return None
            content = (choice.message.content or '').strip()
            if not content:
                self.last_error = 'EmptyReply: the model returned no text'
                return None
            return content
        except Exception as exc:    # network, auth, rate limit, timeout, bad SDK call ...
            self.last_duration = time.monotonic() - started
            self._remember_error(exc)
            return None

    def chat_with_strategy(self, strategy, data: dict) -> LLMResult:
        """
        The single call path for every agent: prompts, budget and fallback all
        come from the strategy. A usable AI reply -> LLMResult(text, True);
        anything else -> LLMResult(strategy fallback, False).
        """
        reply = self.chat(
            system=strategy.build_system_prompt(),
            user=strategy.build_user_prompt(data),
            max_tokens=strategy.max_tokens,
            temperature=strategy.temperature,
            reasoning_effort=strategy.reasoning_effort,
        )
        text = strategy.finalize(reply)
        if text is None:
            if reply is not None:
                self.last_error = 'Unusable: the reply was empty after cleaning or too long'
            return LLMResult(strategy.build_fallback(data), False)
        return LLMResult(text, True)