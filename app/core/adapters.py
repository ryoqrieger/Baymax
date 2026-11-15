"""
Bridge between django-allauth and Baymax's own session login.

allauth does the Google OAuth handshake (redirect, state check, token
exchange, profile fetch). It would normally then create a Django auth user.
Baymax does not use Django auth users, so this adapter intercepts the result
in pre_social_login(), keeps only the verified email + name in the session,
and sends the browser to Baymax's own `google_complete` view.
"""
import time

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from core.components import GOOGLE_PROFILE_KEY


class BaymaxSocialAccountAdapter(DefaultSocialAccountAdapter):

    def pre_social_login(self, request, sociallogin):
        verified = [a for a in sociallogin.email_addresses if a.verified and a.email]
        if not verified:
            messages.error(request, 'Your Google account has no verified email address.')
            raise ImmediateHttpResponse(redirect('login'))

        data = sociallogin.account.extra_data or {}
        email = verified[0].email.strip().lower()
        name = (data.get('name') or '').strip()

        request.session[GOOGLE_PROFILE_KEY] = {
            'email': email,
            'full_name': name,
            'issued_at': int(time.time()),
        }
        raise ImmediateHttpResponse(redirect('google_complete'))

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        messages.error(request, 'Google sign-in was cancelled or failed. Please try again.')
        raise ImmediateHttpResponse(redirect('login'))