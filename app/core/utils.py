"""
Shared helpers (architecture rule 6: all shared helpers live here).
Sprint 4 adds get_page_range() for pagination.
"""
from datetime import date

from django.urls import NoReverseMatch, reverse

from core.db import connect_db

from core.components import (
    PAGE_SIZE,
    PAGE_WINDOW,
    ROLE_DASHBOARD,
    ROLE_PROFESSIONAL,
    ROLE_LABELS,
    ROLE_NAV,
    ROLE_TINT,
)


def safe_reverse(name, **kwargs):
    """reverse() that returns None instead of raising when a URL isn't built yet."""
    try:
        return reverse(name, kwargs=kwargs or None)
    except NoReverseMatch:
        return None


# ── Pagination ────────────────────────────────────────────────────────────────

def parse_page(request) -> int:
    """The ?page= value as a positive int. Anything invalid means page 1."""
    try:
        page = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        return 1
    return page if page >= 1 else 1


def total_pages_for(total_rows: int, page_size: int = PAGE_SIZE) -> int:
    """How many pages `total_rows` need (an empty list still has 1 page)."""
    return max(1, -(-total_rows // page_size))


def get_page_range(current: int, total_pages: int, window: int = PAGE_WINDOW) -> list:
    """
    Page numbers to show, with None where numbers are skipped (shown as "…").
    Always includes the first and last page and `window` pages around the current one.
        get_page_range(10, 20) -> [1, None, 8, 9, 10, 11, 12, None, 20]
    """
    shown = {1, total_pages}
    shown.update(range(max(1, current - window), min(total_pages, current + window) + 1))
    pages, previous = [], 0
    for number in sorted(shown):
        if number - previous > 1:
            pages.append(None)
        pages.append(number)
        previous = number
    return pages


def count_new_requests(professional_id: int) -> int:
    """Appointment requests this professional has not opened yet (the notification badge)."""
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM appointments "
                "WHERE professional_id = %s AND status = 'pending' AND is_new = TRUE",
                (professional_id,),
            )
            return cur.fetchone()['n']
    finally:
        conn.close()


def mask_email(email: str) -> str:
    """'alex.johnson@gmail.com' -> 'a***@gmail.com' (for on-screen confirmation)."""
    local, _, domain = email.partition('@')
    if not domain:
        return email
    return f"{local[:1]}***@{domain}"


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

    new_requests = 0
    if role == ROLE_PROFESSIONAL and session.get('user_id'):
        try:
            new_requests = count_new_requests(session['user_id'])
        except Exception:      # a badge must never break a page
            new_requests = 0

    nav_items = []
    for label, url_name in ROLE_NAV.get(role, []):
        url = safe_reverse(url_name)
        if url is None:
            continue
        nav_items.append({
            'label': label,
            'url': url,
            'active': request.path == url or (url != '/' and request.path.startswith(url)),
            'badge': new_requests if url_name == 'professional_appointments' else 0,
        })

    home_url = safe_reverse(ROLE_DASHBOARD.get(role, '')) or safe_reverse('landing') or '/'

    return {
        'role': role,
        'role_label': ROLE_LABELS.get(role, ''),
        'user_name': user_name,
        'role_tint': ROLE_TINT.get(role, 'bg-gradient-soft'),
        'nav_items': nav_items,
        'home_url': home_url,
        'login_url': safe_reverse('login'),
        'logout_url': safe_reverse('logout'),
        'password_url': safe_reverse('change_password'),
        'current_year': date.today().year,
    }