"""
Authentication views and the two access-control decorators.

Session keys set at login (read by core.utils.nav_context and every view):
    user_id, role, user_name, email
"""
import functools

from django.contrib import messages
from django.contrib.auth.hashers import check_password, is_password_usable, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.components import (
    ALL_ROLES,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
    ROLE_DASHBOARD,
)
from core.db import connect_db
from core.utils import safe_reverse


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

def index(request):
    """Home. Replaced by the landing page in the next chunk."""
    role = request.session.get('role')
    if role in ROLE_DASHBOARD:
        return redirect_to_dashboard(role)
    return redirect('login')


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