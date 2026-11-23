"""Admin IT portal views (Sprint 6): dashboard and user management."""
from django.contrib import messages
from django.contrib.auth.hashers import is_password_usable, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.components import (
    ADMIN_ACCOUNT_LOCK_ID,
    ADMIN_APPOINTMENT_TABS,
    ADMIN_CREATABLE_ROLES,
    ALL_ROLES,
    APPOINTMENT_STATUS_BADGES,
    DEFAULT_ADMIN_APPOINTMENT_TAB,
    EMAIL_MAX,
    FULL_NAME_MAX,
    PAGE_SIZE,
    PASSWORD_LINK_TTL_SECONDS,
    ROLE_ADMIN,
    ROLE_LABELS,
    SPECIALIZATION_MAX,
    USER_SEARCH_MAX,
)
from core.db import connect_db, get_current_semester
from core.email_utils import EmailSendError, send_password_set_email
from core.utils import (
    get_page_range, make_password_link_token, parse_page, safe_reverse, total_pages_for,
)
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
                "SELECT u.id, u.role, u.full_name, u.email, u.password, u.is_active, u.created_at, "
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
        # Staff accounts that were created by Admin IT and have not set a password yet.
        row['awaiting_password'] = row['role'] != 'student' and not is_password_usable(row['password'])
        del row['password']

    query_parts = [f'role={role}'] + ([f'q={_url_quote(search)}'] if search else [])
    chips = [{'key': 'all', 'label': 'All', 'count': sum(counts.values()), 'active': role == 'all'}]
    chips += [{'key': r, 'label': ROLE_LABELS[r], 'count': counts.get(r, 0), 'active': role == r} for r in ALL_ROLES]

    return render(request, 'admin/users.html', {
        'rows': rows,
        'chips': chips,
        'role': role,
        'search': search,
        'search_max': USER_SEARCH_MAX,
        'new_url': safe_reverse('admin_user_new'),
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


# ════════════════════════════════════════════════════════════════════
#  NEW STAFF ACCOUNTS: the person receives a password-set link by email
# ════════════════════════════════════════════════════════════════════

def clean_new_user_form(post) -> tuple:
    """Validate the "new user" form. Returns (values, errors)."""
    values = {
        'role': (post.get('role') or '').strip(),
        'full_name': (post.get('full_name') or '').strip(),
        'email': (post.get('email') or '').strip().lower(),
        'specialization': (post.get('specialization') or '').strip(),
    }
    errors = {}
    if values['role'] not in ADMIN_CREATABLE_ROLES:
        errors['role'] = 'Please choose a role.'
    if not values['full_name']:
        errors['full_name'] = 'Please enter a name.'
    elif len(values['full_name']) > FULL_NAME_MAX:
        errors['full_name'] = f'The name can be at most {FULL_NAME_MAX} characters.'
    try:
        if len(values['email']) > EMAIL_MAX:
            raise ValidationError('too long')
        validate_email(values['email'])
    except ValidationError:
        errors['email'] = 'Please enter a valid email address.'
    if values['role'] == 'professional':
        if not values['specialization']:
            errors['specialization'] = 'Please enter the specialization.'
        elif len(values['specialization']) > SPECIALIZATION_MAX:
            errors['specialization'] = f'The specialization can be at most {SPECIALIZATION_MAX} characters.'
    return values, errors


def _password_link(request, user_id, stored_password) -> str:
    token = make_password_link_token(user_id, stored_password)
    return request.build_absolute_uri(safe_reverse('set_password', token=token))


def _email_password_link(request, user) -> bool:
    """Email the password-set link. Returns False if the mail server could not deliver it."""
    ttl_days = PASSWORD_LINK_TTL_SECONDS // 86400
    try:
        send_password_set_email(
            user['email'], user['full_name'], ROLE_LABELS[user['role']],
            _password_link(request, user['id'], user['password']), ttl_days,
        )
        return True
    except EmailSendError:
        return False


@login_required_role(ROLE_ADMIN)
def user_new(request):
    choices = [{'key': role, 'label': ROLE_LABELS[role]} for role in ADMIN_CREATABLE_ROLES]
    values, errors = {'role': '', 'full_name': '', 'email': '', 'specialization': ''}, {}

    if request.method == 'POST':
        values, errors = clean_new_user_form(request.POST)
        if not errors:
            conn = connect_db()
            try:
                with conn.cursor() as cur:
                    unusable = make_password(None)          # no password until the person sets one
                    cur.execute(
                        "INSERT INTO users (role, full_name, email, password) "
                        "SELECT %s, %s, %s, %s WHERE NOT EXISTS (SELECT 1 FROM users WHERE LOWER(email) = %s) "
                        "RETURNING id",
                        (values['role'], values['full_name'], values['email'], unusable, values['email']),
                    )
                    created = cur.fetchone()
                    if created and values['role'] == 'professional':
                        cur.execute(
                            "INSERT INTO professionals (user_id, specialization) VALUES (%s, %s)",
                            (created['id'], values['specialization']),
                        )
                conn.commit()
            finally:
                conn.close()

            if created is None:
                errors['email'] = 'An account with this email already exists.'
            else:
                user = {'id': created['id'], 'email': values['email'], 'full_name': values['full_name'],
                        'role': values['role'], 'password': unusable}
                if _email_password_link(request, user):
                    messages.success(request, f"Account created. A password-set link was emailed to {values['email']}.")
                else:
                    messages.warning(
                        request,
                        f"Account created, but the email to {values['email']} could not be sent. "
                        "Use “Resend link” on the Users page once the mail settings work.",
                    )
                return redirect('admin_users')

    return render(request, 'admin/user_form.html', {
        'form': values,
        'errors': errors,
        'choices': choices,
        'full_name_max': FULL_NAME_MAX,
        'email_max': EMAIL_MAX,
        'specialization_max': SPECIALIZATION_MAX,
        'ttl_days': PASSWORD_LINK_TTL_SECONDS // 86400,
        'list_url': safe_reverse('admin_users'),
    })


@login_required_role(ROLE_ADMIN)
@require_POST
def user_resend(request, user_id):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, role, full_name, email, password, is_active FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
    finally:
        conn.close()
    if user is None:
        raise Http404('User not found')

    if user['role'] == 'student' or is_password_usable(user['password']):
        messages.info(request, f"{user['full_name']} has already set a password.")
    elif not user['is_active']:
        messages.error(request, 'Reactivate this account before sending a link.')
    elif _email_password_link(request, user):
        messages.success(request, f"A new password-set link was emailed to {user['email']}.")
    else:
        messages.error(request, f"The email to {user['email']} could not be sent. Check the email settings and try again.")
    return _back_to_users(request)


# ════════════════════════════════════════════════════════════════════
#  MONITORS (read-only)
# ════════════════════════════════════════════════════════════════════

@login_required_role(ROLE_ADMIN)
def appointments(request):
    tab = request.GET.get('tab', DEFAULT_ADMIN_APPOINTMENT_TAB)
    if tab not in ADMIN_APPOINTMENT_TABS:
        tab = DEFAULT_ADMIN_APPOINTMENT_TAB
    statuses = list(ADMIN_APPOINTMENT_TABS[tab][1])

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FILTER (WHERE status IN ('pending', 'accepted')) AS active, "
                "       COUNT(*) FILTER (WHERE status = 'completed') AS completed, "
                "       COUNT(*) FILTER (WHERE status = 'declined')  AS declined, "
                "       COUNT(*) AS all_rows FROM appointments"
            )
            counts = cur.fetchone()
            counts['all'] = counts.pop('all_rows')

            total_rows = counts[tab]
            total_pages = total_pages_for(total_rows)
            page = min(parse_page(request), total_pages)
            cur.execute(
                "SELECT a.id, a.status, a.created_at, a.scheduled_at, "
                "       su.full_name AS student_name, pu.full_name AS professional_name "
                "FROM appointments a "
                "JOIN users su ON su.id = a.student_id "
                "JOIN users pu ON pu.id = a.professional_id "
                "WHERE a.status = ANY(%s) "
                "ORDER BY COALESCE(a.scheduled_at, a.created_at) DESC, a.id DESC LIMIT %s OFFSET %s",
                (statuses, PAGE_SIZE, (page - 1) * PAGE_SIZE),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    for row in rows:
        row['status_label'], row['status_badge'] = APPOINTMENT_STATUS_BADGES[row['status']]
    return render(request, 'admin/appointments.html', {
        'rows': rows,
        'tabs': [{'key': key, 'label': label, 'count': counts[key], 'active': key == tab}
                 for key, (label, _) in ADMIN_APPOINTMENT_TABS.items()],
        'page': page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'page_numbers': get_page_range(page, total_pages),
        'page_query': f'tab={tab}',
    })


@login_required_role(ROLE_ADMIN)
def events(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM events WHERE date >= CURRENT_DATE")
            total_rows = cur.fetchone()['n']
            total_pages = total_pages_for(total_rows)
            page = min(parse_page(request), total_pages)
            cur.execute(
                "SELECT e.id, e.title, e.date, e.time, e.venue, e.rsvp_count, u.full_name AS creator "
                "FROM events e LEFT JOIN users u ON u.id = e.created_by "
                "WHERE e.date >= CURRENT_DATE ORDER BY e.date, e.time, e.id LIMIT %s OFFSET %s",
                (PAGE_SIZE, (page - 1) * PAGE_SIZE),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return render(request, 'admin/events.html', {
        'rows': rows,
        'page': page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'page_numbers': get_page_range(page, total_pages),
        'page_query': '',
    })