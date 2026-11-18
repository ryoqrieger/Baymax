"""
python manage.py check_llm

Makes ONE real call to Groq with sample data (no student information) and
says whether the key, model and address in your .env work.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from core.agents.llm_client import LLMClient
from core.agents.strategies import StatusDescriptionStrategy

SAMPLE = {
    'status': 'Challenged',
    'stress_level': 'moderate',
    'anxiety_level': 'mild',
    'mood_level': 'mild',
    'top_areas': ['academic pressure'],
}

HINTS = {
    'AuthenticationError': 'Groq rejected GROQ_API_KEY. Copy the key again from console.groq.com (API Keys).',
    'PermissionDeniedError': 'Your Groq account may not be allowed to use this model. Check GROQ_MODEL.',
    'NotFoundError': 'The address or model name was not found. Check GROQ_BASE_URL and GROQ_MODEL.',
    'RateLimitError': 'Groq says you are sending too many requests. Wait a minute and try again.',
    'APITimeoutError': 'The request timed out. Check your internet connection, or raise GROQ_TIMEOUT.',
    'APIConnectionError': 'Could not reach Groq. Check your internet connection and GROQ_BASE_URL.',
    'BadRequestError': 'Groq rejected the request. Check GROQ_MODEL.',
    'CutOff': 'The model ran out of tokens before finishing. Tell me, and I will raise the headroom.',
    'EmptyReply': 'The model answered with no text. Run the command again; if it repeats, tell me.',
}


class Command(BaseCommand):
    help = 'Make one real Groq call to check GROQ_API_KEY, GROQ_MODEL and GROQ_BASE_URL.'

    def handle(self, *args, **options):
        self.stdout.write(f'Model:    {settings.GROQ_MODEL}')
        self.stdout.write(f'Address:  {settings.GROQ_BASE_URL}')
        self.stdout.write(f'Timeout:  {settings.GROQ_TIMEOUT}s')
        self.stdout.write('Calling Groq ...')

        client = LLMClient()
        result = client.chat_with_strategy(StatusDescriptionStrategy(), SAMPLE)
        took = f'{client.last_duration:.1f}s' if client.last_duration is not None else '?'

        if result.from_ai:
            self.stdout.write(self.style.SUCCESS(f'OK ({took}). Groq replied:'))
            self.stdout.write(f'  {result.text}')
            return

        self.stdout.write(self.style.ERROR(f'FAILED ({took}). The built-in fallback text would be shown instead.'))
        self.stdout.write(f'  Reason: {client.last_error or "unknown"}')
        error_name = (client.last_error or '').split(':')[0]
        if error_name in HINTS:
            self.stdout.write(f'  Fix:    {HINTS[error_name]}')