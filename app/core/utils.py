"""
Shared helpers (architecture rule 6: all shared helpers live here).
Sprint 4 adds get_page_range() for pagination.
"""
from datetime import date

from django.urls import NoReverseMatch, reverse

from core.components import (
    ROLE_DASHBOARD,
    ROLE_LABELS,
    ROLE_NAV,
    ROLE_TINT,
)


def _safe_reverse(name):
    """reverse() that returns None instead of raising when a URL isn't built yet."""
    try:
        return reverse(name)
    except NoReverseMatch:
        return None


def nav_context(request):
    """
    Template context processor: everything base.html needs for the navbar.

    Reads the session keys set at login (Sprint 1):
        request.session['role']       one of the ROLE_* values
        request.session['user_name']  display name
    """
    session = getattr(request, 'session', None)
    role = session.get('role') if session is not None else None
    user_name = session.get('user_name', '') if session is not None else ''

    nav_items = []
    for label, url_name in ROLE_NAV.get(role, []):
        url = _safe_reverse(url_name)
        if url is None:
            continue
        nav_items.append({
            'label': label,
            'url': url,
            'active': request.path == url or (url != '/' and request.path.startswith(url)),
        })

    home_url = _safe_reverse(ROLE_DASHBOARD.get(role, '')) or _safe_reverse('landing') or '/'

    return {
        'role': role,
        'role_label': ROLE_LABELS.get(role, ''),
        'user_name': user_name,
        'role_tint': ROLE_TINT.get(role, 'bg-gradient-soft'),
        'nav_items': nav_items,
        'home_url': home_url,
        'login_url': _safe_reverse('login'),
        'logout_url': _safe_reverse('logout'),
        'current_year': date.today().year,
    }