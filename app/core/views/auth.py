"""
Authentication views and the two access-control decorators.

Session keys set at login (read by core.utils.nav_context and every view):
    user_id, role, user_name, email
"""
import functools
import hmac
import hashlib
import math
import re
import secrets
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.components import (
    ALL_ROLES,
    DEPARTMENT_CHOICES,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    OTP_MAX_ATTEMPTS,
    OTP_RESEND_SECONDS,
    OTP_TTL_SECONDS,
    ROLE_DASHBOARD,
    ROLE_STUDENT,
    VALID_DEPARTMENTS,
)
from core.db import connect_db
from core.email_utils import EmailSendError, send_otp_email
from core.utils import mask_email, safe_reverse


# ════════════════════════════════════════════════════════════════════
#  DECORATORS
# ════════════════════════════════════════════════════════════════════

def login_required_role(*roles):
    """Restrict a view to one or more user roles."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            current = request.session.get('role')
            if current in roles:
                return view_func(request, *args, **kwargs)
            if current in ROLE_DASHBOARD:
                # Signed in, but this page belongs to another role.
                messages.error(request, "You don't have access to that page.")
                return redirect(ROLE_DASHBOARD[current])
            return redirect('login')
        return wrapper
    return decorator


def _rate_limit_key(email: str) -> str:
    return f'rate_limit:{email.strip().lower()}'


def rate_limit(max_attempts: int = 5, window: int = 900):
    """
    Flag a POST as rate-limited once `max_attempts` failures were recorded
    for the submitted email within `window` seconds.

    The decorated view stays in charge of the response: it reads
    `request.rate_limited` and calls record_failed_attempt() /
    clear_failed_attempts() as the outcome becomes known.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            request.rate_limited = False
            request.rate_limit_key = None
            request.rate_limit_window = window
            if request.method == 'POST':
                request.rate_limit_key = _rate_limit_key(request.POST.get('email', ''))
                request.rate_limited = cache.get(request.rate_limit_key, 0) >= max_attempts
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def record_failed_attempt(request) -> None:
    """Count one failure. The window starts at the first failure and is not extended."""
    key = request.rate_limit_key
    if not key:
        return
    if not cache.add(key, 1, request.rate_limit_window):
        try:
            cache.incr(key)
        except ValueError:  # entry expired between add() and incr()
            cache.set(key, 1, request.rate_limit_window)


def clear_failed_attempts(request) -> None:
    if request.rate_limit_key:
        cache.delete(request.rate_limit_key)


# ════════════════════════════════════════════════════════════════════
#  HELPERS
# ════════════════════════════════════════════════════════════════════

_dummy_hash = None


def _verify_password(raw: str, stored) -> bool:
    """
    Check a password. When the user does not exist, a dummy hash is checked
    instead so a wrong email and a wrong password take the same time.
    """
    global _dummy_hash
    if stored is None:
        if _dummy_hash is None:
            _dummy_hash = make_password('baymax-timing-equaliser')
        check_password(raw, _dummy_hash)
        return False
    return check_password(raw, stored)


def _fetch_user_by_email(email: str):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, role, full_name, email, password, is_active "
                "FROM users WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def start_session(request, user) -> None:
    """Sign a user in. flush() issues a fresh session key (no session fixation)."""
    request.session.flush()
    request.session['user_id'] = user['id']
    request.session['role'] = user['role']
    request.session['user_name'] = user['full_name']
    request.session['email'] = user['email']


def redirect_to_dashboard(role):
    return redirect(ROLE_DASHBOARD[role])


# ════════════════════════════════════════════════════════════════════
#  VIEWS
# ════════════════════════════════════════════════════════════════════

def landing(request):
    """Public home page. Signed-in users go straight to their dashboard."""
    role = request.session.get('role')
    if role in ROLE_DASHBOARD:
        return redirect_to_dashboard(role)
    return render(request, 'auth/landing.html', {
        'login_url': safe_reverse('login'),
        'register_url': safe_reverse('register'),
    })


@rate_limit(max_attempts=LOGIN_MAX_ATTEMPTS, window=LOGIN_WINDOW_SECONDS)
def login_view(request):
    role = request.session.get('role')
    if role in ROLE_DASHBOARD:
        return redirect_to_dashboard(role)

    context = {
        'email': '',
        # Links appear automatically once those routes exist (later chunks).
        'register_url': safe_reverse('register'),
        'google_url': safe_reverse('google_start'),
        'landing_url': safe_reverse('landing'),
    }

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        context['email'] = email

        if not email or not password:
            messages.error(request, 'Please enter your email and password.')
        elif request.rate_limited:
            messages.error(
                request,
                f'Too many failed attempts. Please try again in {LOGIN_WINDOW_SECONDS // 60} minutes.',
            )
        else:
            user = _fetch_user_by_email(email)
            if _verify_password(password, user['password'] if user else None):
                if not user['is_active']:
                    messages.error(request, 'This account has been deactivated. Please contact Admin IT.')
                else:
                    clear_failed_attempts(request)
                    start_session(request, user)
                    messages.success(request, f"Welcome back, {user['full_name']}.")
                    return redirect_to_dashboard(user['role'])
            else:
                record_failed_attempt(request)
                messages.error(request, 'Invalid email or password.')

    return render(request, 'auth/login.html', context)


@require_POST
def logout_view(request):
    request.session.flush()
    messages.info(request, 'You have been signed out.')
    return redirect('login')


@login_required_role(*ALL_ROLES)
def change_password(request):
    """Password change for every role. Requires the current password."""
    user_id = request.session['user_id']

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT password FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()

            if row is None:  # account was removed while signed in
                request.session.flush()
                return redirect('login')

            if not is_password_usable(row['password']):
                messages.info(
                    request,
                    'Your account signs in with Google, so there is no password to change.',
                )
                return redirect_to_dashboard(request.session['role'])

            if request.method == 'POST':
                current = request.POST.get('current_password', '')
                new = request.POST.get('new_password', '')
                confirm = request.POST.get('confirm_password', '')

                errors = []
                if not check_password(current, row['password']):
                    errors.append('Your current password is incorrect.')
                if new != confirm:
                    errors.append('The new passwords do not match.')
                elif current and new == current:
                    errors.append('Your new password must be different from the current one.')
                if new and new == confirm:
                    try:
                        validate_password(new)
                    except ValidationError as exc:
                        errors.extend(exc.messages)
                if not new:
                    errors.append('Please enter a new password.')

                if errors:
                    for error in dict.fromkeys(errors):
                        messages.error(request, error)
                else:
                    cur.execute(
                        "UPDATE users SET password = %s WHERE id = %s",
                        (make_password(new), user_id),
                    )
                    conn.commit()
                    request.session.cycle_key()
                    messages.success(request, 'Your password has been changed.')
                    return redirect_to_dashboard(request.session['role'])
    finally:
        conn.close()

    return render(request, 'auth/change_password.html')


# ════════════════════════════════════════════════════════════════════
#  STUDENT REGISTRATION WITH EMAIL OTP
#
#  1. /register/         validate the form, email a 6-digit code, keep the
#                        pending account in the session (password hashed,
#                        code stored only as an HMAC)
#  2. /register/verify/  check the code (10-minute expiry, 5 tries),
#                        then create the account and sign the student in
#  3. /register/resend/  new code, at most one every 5 minutes
# ════════════════════════════════════════════════════════════════════

PENDING_KEY = 'registration_pending'
_STUDENT_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9\-_/]{2,29}$')


def _hash_otp(email: str, otp: str) -> str:
    """HMAC of the code, keyed with SECRET_KEY — the plain code is never stored."""
    return hmac.new(
        settings.SECRET_KEY.encode(), f'{email}:{otp}'.encode(), hashlib.sha256
    ).hexdigest()


def _new_otp() -> str:
    return f'{secrets.randbelow(10 ** 6):06d}'


def _cooldown_key(email: str) -> str:
    return f'otp_cooldown:{email}'


def _cooldown_remaining(email: str) -> int:
    """Seconds until another code may be sent to this address (0 = allowed now)."""
    sent_at = cache.get(_cooldown_key(email))
    if sent_at is None:
        return 0
    return max(0, math.ceil(OTP_RESEND_SECONDS - (time.time() - sent_at)))


def _minutes(seconds: int) -> int:
    return max(1, math.ceil(seconds / 60))


def _issue_otp(pending: dict) -> None:
    """Create a code, email it, and record it on `pending`. Raises EmailSendError."""
    otp = _new_otp()
    send_otp_email(pending['email'], pending['full_name'], otp, OTP_TTL_SECONDS // 60)
    now = time.time()
    pending['otp_hash'] = _hash_otp(pending['email'], otp)
    pending['otp_expires'] = now + OTP_TTL_SECONDS
    pending['attempts'] = 0
    cache.set(_cooldown_key(pending['email']), now, OTP_RESEND_SECONDS)


def _validate_registration(data: dict) -> dict:
    """Return {field: message} for every problem found (empty dict = valid)."""
    errors = {}

    name = data['full_name']
    if len(name) < 2 or len(name) > 120:
        errors['full_name'] = 'Please enter your full name (2–120 characters).'

    email = data['email']
    try:
        if len(email) > 254:
            raise ValidationError('too long')
        validate_email(email)
    except ValidationError:
        errors['email'] = 'Please enter a valid email address.'

    if not _STUDENT_ID_RE.match(data['student_id']):
        errors['student_id'] = 'Use 3–30 letters, numbers, or dashes (e.g. 2026-1-60-001).'

    if data['department'] not in VALID_DEPARTMENTS:
        errors['department'] = 'Please choose your department.'

    password = data['password']
    if password != data['confirm']:
        errors['confirm'] = 'The passwords do not match.'
    elif password:
        first, _, last = name.partition(' ')
        # Unsaved User: only used so the "too similar to your details" check has
        # something to compare with. Nothing is written to the database.
        probe = User(username=email.split('@')[0], first_name=first, last_name=last, email=email)
        try:
            validate_password(password, user=probe)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)
    else:
        errors['password'] = 'Please choose a password.'

    return errors


def _find_conflicts(email: str, student_id: str) -> dict:
    """Field errors for an email or student ID that is already registered."""
    conflicts = {}
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE LOWER(email) = LOWER(%s)", (email,))
            if cur.fetchone():
                conflicts['email'] = 'An account with this email already exists.'
            cur.execute("SELECT 1 FROM students WHERE LOWER(student_id) = LOWER(%s)", (student_id,))
            if cur.fetchone():
                conflicts['student_id'] = 'This student ID is already registered.'
    finally:
        conn.close()
    return conflicts


def register(request):
    role = request.session.get('role')
    if role in ROLE_DASHBOARD:
        return redirect_to_dashboard(role)

    form = {'full_name': '', 'email': '', 'student_id': '', 'department': ''}
    errors = {}

    if request.method == 'POST':
        data = {
            'full_name': ' '.join(request.POST.get('full_name', '').split()),
            'email': request.POST.get('email', '').strip().lower(),
            'student_id': request.POST.get('student_id', '').strip(),
            'department': request.POST.get('department', '').strip(),
            'password': request.POST.get('password', ''),
            'confirm': request.POST.get('confirm', ''),
        }
        form = {k: data[k] for k in form}
        errors = _validate_registration(data)

        if not errors:
            errors = _find_conflicts(data['email'], data['student_id'])

        if not errors:
            wait = _cooldown_remaining(data['email'])
            pending = request.session.get(PENDING_KEY)
            same_pending = pending and pending['email'] == data['email']
            if wait and not same_pending:
                messages.error(
                    request,
                    f'A verification code was sent to this address recently. '
                    f'Please check your inbox, or try again in {_minutes(wait)} minute(s).',
                )
            else:
                pending = {
                    'full_name': data['full_name'],
                    'email': data['email'],
                    'student_id': data['student_id'],
                    'department': data['department'],
                    'password_hash': make_password(data['password']),
                }
                if same_pending and wait:
                    # Same person re-submitting inside the cooldown: no new email.
                    pending.update({k: request.session[PENDING_KEY][k]
                                    for k in ('otp_hash', 'otp_expires', 'attempts')})
                    request.session[PENDING_KEY] = pending
                    return redirect('register_verify')
                try:
                    _issue_otp(pending)
                except EmailSendError:
                    messages.error(
                        request,
                        "We couldn't send the verification email. Please check the address and try again shortly.",
                    )
                else:
                    request.session[PENDING_KEY] = pending
                    messages.info(request, f"We sent a 6-digit code to {mask_email(data['email'])}.")
                    return redirect('register_verify')

    return render(request, 'auth/register.html', {
        'form': form,
        'errors': errors,
        'departments': DEPARTMENT_CHOICES,
        'login_url': safe_reverse('login'),
        'landing_url': safe_reverse('landing'),
        'google_url': safe_reverse('google_start'),
    })


def register_verify(request):
    pending = request.session.get(PENDING_KEY)
    if not pending:
        messages.info(request, 'Please fill in the registration form first.')
        return redirect('register')

    if request.method == 'POST':
        code = ''.join(ch for ch in request.POST.get('otp', '') if ch.isdigit())

        # Expiry is checked on EVERY attempt.
        if time.time() > pending['otp_expires']:
            messages.error(request, 'That code has expired. Please request a new one.')
        elif pending['attempts'] >= OTP_MAX_ATTEMPTS:
            messages.error(request, 'Too many incorrect codes. Please request a new one.')
        else:
            pending['attempts'] += 1
            request.session[PENDING_KEY] = pending
            expected = pending['otp_hash']
            if len(code) == 6 and hmac.compare_digest(_hash_otp(pending['email'], code), expected):
                return _complete_registration(request, pending)
            left = OTP_MAX_ATTEMPTS - pending['attempts']
            messages.error(
                request,
                'That code is not correct.' + (f' {left} attempt(s) left.' if left else ' Please request a new code.'),
            )

    wait = _cooldown_remaining(pending['email'])
    return render(request, 'auth/register_otp.html', {
        'masked_email': mask_email(pending['email']),
        'ttl_minutes': OTP_TTL_SECONDS // 60,
        'resend_wait_minutes': _minutes(wait) if wait else 0,
    })


def _complete_registration(request, pending):
    """Create the user + student rows, then sign the new student in."""
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (role, full_name, email, password) "
                "VALUES (%s, %s, %s, %s) RETURNING id, role, full_name, email",
                (ROLE_STUDENT, pending['full_name'], pending['email'], pending['password_hash']),
            )
            user = cur.fetchone()
            cur.execute(
                "INSERT INTO students (user_id, student_id, department) VALUES (%s, %s, %s)",
                (user['id'], pending['student_id'], pending['department']),
            )
        conn.commit()
    except IntegrityError:
        # Someone registered this email between the form and the code.
        conn.rollback()
        request.session.pop(PENDING_KEY, None)
        messages.error(request, 'An account with this email already exists. Please sign in.')
        return redirect('login')
    finally:
        conn.close()

    start_session(request, user)  # flush() also discards the pending data
    messages.success(request, f"Your email is verified. Welcome to Baymax, {user['full_name']}!")
    return redirect_to_dashboard(ROLE_STUDENT)


@require_POST
def register_resend(request):
    pending = request.session.get(PENDING_KEY)
    if not pending:
        return redirect('register')

    wait = _cooldown_remaining(pending['email'])
    if wait:
        messages.error(request, f'Please wait {_minutes(wait)} minute(s) before requesting a new code.')
        return redirect('register_verify')

    try:
        _issue_otp(pending)
    except EmailSendError:
        messages.error(request, "We couldn't send the email. Please try again shortly.")
    else:
        request.session[PENDING_KEY] = pending
        messages.info(request, f"A new code was sent to {mask_email(pending['email'])}.")
    return redirect('register_verify')


def register_cancel(request):
    """'Use a different email': drop the pending registration."""
    request.session.pop(PENDING_KEY, None)
    return redirect('register')