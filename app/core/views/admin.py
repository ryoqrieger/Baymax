"""Admin IT portal views (Sprint 6): dashboard and user management."""
from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.components import (
    ADMIN_ACCOUNT_LOCK_ID,
    ALL_ROLES,
    PAGE_SIZE,
    ROLE_ADMIN,
    ROLE_LABELS,
    USER_SEARCH_MAX,
)
from core.db import connect_db, get_current_semester
from core.utils import get_page_range, parse_page, safe_reverse, total_pages_for
from core.views.auth import login_required_role


@login_required_role(ROLE_ADMIN)
def dashboard(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, COUNT(*) FILTER (WHERE is_active) AS active, "
                "       COUNT(*) FILTER (WHERE NOT is_active) AS inactive "
                "FROM users GROUP BY role"
            )
            by_role = {row['role']: row for row in cur.fetchall()}

            semester = get_current_semester(cur)
            cur.execute("SELECT start_date, end_date FROM semester_schedule WHERE semester = %s", (semester,))
            dates = cur.fetchone()

            cur.execute(
                "SELECT COUNT(*) FILTER (WHERE status = 'pending')  AS pending, "
                "       COUNT(*) FILTER (WHERE status = 'accepted') AS accepted "
                "FROM appointments"
            )
            appointments = cur.fetchone()

            cur.execute("SELECT COUNT(*) AS n FROM events WHERE date >= CURRENT_DATE")
            events_total = cur.fetchone()['n']
    finally:
        conn.close()

    roles = []
    for role in ALL_ROLES:
        row = by_role.get(role, {'active': 0, 'inactive': 0})
        roles.append({'label': ROLE_LABELS[role], 'active': row['active'], 'inactive': row['inactive']})

    return render(request, 'admin/dashboard.html', {
        'roles': roles,
        'users_total': sum(r['active'] + r['inactive'] for r in roles),
        'semester': semester,
        'semester_dates': dates,
        'appointments': appointments,
        'events_total': events_total,
        'users_url': safe_reverse('admin_users'),
        'semester_url': safe_reverse('admin_semester'),
        'appointments_url': safe_reverse('admin_appointments'),
        'events_url': safe_reverse('admin_events'),
    })


def _like_pattern(text: str) -> str:
    """Search text as an ILIKE pattern in which %, _ and \\ typed by a person are plain characters."""
    escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@login_required_role(ROLE_ADMIN)
def users(request):
    role = request.GET.get('role', 'all')
    if role not in ALL_ROLES:
        role = 'all'
    search = (request.GET.get('q') or '').strip()[:USER_SEARCH_MAX]

    where, params = [], []
    if role != 'all':
        where.append('u.role = %s')
        params.append(role)
    if search:
        where.append('(u.full_name ILIKE %s OR u.email ILIKE %s)')
        params.extend([_like_pattern(search)] * 2)
    where_sql = (' WHERE ' + ' AND '.join(where)) if where else ''     # fixed fragments only

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT role, COUNT(*) AS n FROM users GROUP BY role")
            counts = {row['role']: row['n'] for row in cur.fetchall()}

            cur.execute(f"SELECT COUNT(*) AS n FROM users u{where_sql}", params)
            total_rows = cur.fetchone()['n']
            total_pages = total_pages_for(total_rows)
            page = min(parse_page(request), total_pages)

            cur.execute(
                "SELECT u.id, u.role, u.full_name, u.email, u.is_active, u.created_at, "
                "       s.department, s.student_id AS student_code, p.specialization "
                "FROM users u "
                "LEFT JOIN students s ON s.user_id = u.id "
                "LEFT JOIN professionals p ON p.user_id = u.id"
                f"{where_sql} ORDER BY u.full_name, u.id LIMIT %s OFFSET %s",
                params + [PAGE_SIZE, (page - 1) * PAGE_SIZE],
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    for row in rows:
        row['role_label'] = ROLE_LABELS[row['role']]
        row['is_me'] = row['id'] == request.session['user_id']
        row['detail'] = row['department'] or row['specialization'] or ''

    query_parts = [f'role={role}'] + ([f'q={_url_quote(search)}'] if search else [])
    chips = [{'key': 'all', 'label': 'All', 'count': sum(counts.values()), 'active': role == 'all'}]
    chips += [{'key': r, 'label': ROLE_LABELS[r], 'count': counts.get(r, 0), 'active': role == r} for r in ALL_ROLES]

    return render(request, 'admin/users.html', {
        'rows': rows,
        'chips': chips,
        'role': role,
        'search': search,
        'search_max': USER_SEARCH_MAX,
        'page': page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'page_numbers': get_page_range(page, total_pages),
        'page_query': '&'.join(query_parts),
    })


def _url_quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe='')


def _back_to_users(request):
    """Return to the list the admin was on (only same-site list pages are allowed)."""
    base = safe_reverse('admin_users')
    query = request.POST.get('return_query', '')
    if query and all(ch.isalnum() or ch in '=&%-_.+' for ch in query):
        return redirect(f'{base}?{query}')
    return redirect(base)


@login_required_role(ROLE_ADMIN)
@require_POST
def user_deactivate(request, user_id):
    if user_id == request.session['user_id']:
        messages.error(request, 'You cannot deactivate your own account.')
        return _back_to_users(request)

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (ADMIN_ACCOUNT_LOCK_ID,))
            cur.execute(
                "UPDATE users SET is_active = FALSE "
                "WHERE id = %s AND is_active = TRUE "
                "  AND (role <> %s OR (SELECT COUNT(*) FROM users WHERE role = %s AND is_active = TRUE) > 1) "
                "RETURNING full_name",
                (user_id, ROLE_ADMIN, ROLE_ADMIN),
            )
            done = cur.fetchone()
            if done is None:
                cur.execute("SELECT full_name, role, is_active FROM users WHERE id = %s", (user_id,))
                user = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    if done:
        messages.success(request, f"{done['full_name']} was deactivated and can no longer sign in.")
    elif user is None:
        raise Http404('User not found')
    elif not user['is_active']:
        messages.info(request, f"{user['full_name']} is already deactivated.")
    else:
        messages.error(request, 'At least one active Admin IT account must remain.')
    return _back_to_users(request)


@login_required_role(ROLE_ADMIN)
@require_POST
def user_reactivate(request, user_id):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_active = TRUE WHERE id = %s RETURNING full_name", (user_id,))
            done = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if done is None:
        raise Http404('User not found')
    messages.success(request, f"{done['full_name']} was reactivated.")
    return _back_to_users(request)