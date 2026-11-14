"""
All outgoing email lives here (architecture rule 5) — views never send mail.

Emails are plain text on purpose: HTML email requires inline styles, which
this project forbids, and plain text is the most reliable for a one-time code.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.template.loader import render_to_string

from core.components import EMAIL_SEND_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when a message could not be delivered to the mail server."""


def _send(to_email: str, subject: str, body: str) -> None:
    try:
        connection = get_connection(timeout=EMAIL_SEND_TIMEOUT_SECONDS)
        EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            connection=connection,
        ).send(fail_silently=False)
    except Exception as exc:  # SMTP, DNS, timeout, authentication ...
        logger.exception('Could not send "%s" email', subject)
        raise EmailSendError(str(exc)) from exc


def send_otp_email(to_email: str, full_name: str, otp: str, ttl_minutes: int) -> None:
    """Send the registration verification code."""
    body = render_to_string('emails/otp.txt', {
        'full_name': full_name,
        'otp': otp,
        'ttl_minutes': ttl_minutes,
    })
    _send(to_email, f'{otp} is your Baymax verification code', body)