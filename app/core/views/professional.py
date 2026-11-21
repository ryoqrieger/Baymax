"""Professional portal views (Sprint 4)."""
from datetime import datetime, timedelta

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.components import (
    APPOINTMENT_MAX_DAYS_AHEAD,
    APPOINTMENT_SLOT_MINUTES,
    APPOINTMENT_STATUS_BADGES,
    APPOINTMENT_TABS,
    DEFAULT_APPOINTMENT_TAB,
    DATETIME_INPUT_FORMAT,
    DEPARTMENT_AT_RISK_PCT,
    PAGE_SIZE,
    QUESTION_COLS,
    ROLE_PROFESSIONAL,
    STATUS_CONTENT,
)
from core.db import connect_db, get_current_semester
from core.utils import (
    answer_groups, get_page_range, list_semesters, parse_page, pick_semester, safe_reverse,
    scale_scores, semester_alerts, semester_overview, semester_overview_empty, total_pages_for,
)
from core.views.auth import login_required_role

# One appointment row with its student. A student's classification is only
# visible while the request is pending or accepted (never after decline/release).
_ROW_SELECT = (
    "SELECT a.id, a.status, a.is_new, a.created_at, a.scheduled_at, "
    "       u.full_name AS student_name, s.department, s.student_id AS student_code, "
    "       CASE WHEN a.status IN ('pending', 'accepted') THEN q.final_status END AS final_status "
    "FROM appointments a "
    "JOIN users u ON u.id = a.student_id "
    "JOIN students s ON s.user_id = a.student_id "
    "LEFT JOIN questionnaire_responses q ON q.student_id = a.student_id AND q.semester = %s "
)


def _decorate(rows):
    """Add the display label, badge class and detail link to each appointment row."""
    for row in rows:
        row['status_label'], row['status_badge'] = APPOINTMENT_STATUS_BADGES[row['status']]
        row['detail_url'] = safe_reverse('professional_appointment', appointment_id=row['id'])
    return rows


@login_required_role(ROLE_PROFESSIONAL)
def dashboard(request):
    pro_id = request.session['user_id']
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            semester = get_current_semester(cur)

            cur.execute(
                "SELECT p.specialization, "
                "  (SELECT start_date FROM semester_schedule WHERE semester = %s) AS semester_start "
                "FROM professionals p WHERE p.user_id = %s",
                (semester, pro_id),
            )
            profile = cur.fetchone() or {'specialization': '', 'semester_start': None}

            cur.execute(
                "SELECT COUNT(*) FILTER (WHERE status = 'pending')  AS pending, "
                "       COUNT(*) FILTER (WHERE status = 'pending' AND is_new) AS new_requests, "
                "       COUNT(*) FILTER (WHERE status = 'accepted') AS active, "
                "       COUNT(*) FILTER (WHERE status = 'completed' "
                "                        AND created_at >= COALESCE(%s, TIMESTAMP '-infinity')) AS completed "
                "FROM appointments WHERE professional_id = %s",
                (profile['semester_start'], pro_id),
            )
            counts = cur.fetchone()

            cur.execute(
                _ROW_SELECT + "WHERE a.professional_id = %s AND a.status = 'pending' "
                              "ORDER BY a.is_new DESC, a.created_at DESC LIMIT 5",
                (semester, pro_id),
            )
            recent = _decorate(cur.fetchall())

            cur.execute(
                _ROW_SELECT + "WHERE a.professional_id = %s AND a.status = 'accepted' "
                              "AND a.scheduled_at >= %s ORDER BY a.scheduled_at LIMIT 5",
                (semester, pro_id, datetime.now()),
            )
            upcoming = _decorate(cur.fetchall())
    finally:
        conn.close()

    return render(request, 'professional/dashboard.html', {
        'specialization': profile['specialization'],
        'counts': counts,
        'recent': recent,
        'upcoming': upcoming,
        'appointments_url': safe_reverse('professional_appointments'),
        'stats_url': safe_reverse('professional_stats'),
    })


@login_required_role(ROLE_PROFESSIONAL)
def appointments(request):
    pro_id = request.session['user_id']
    tab = request.GET.get('tab', DEFAULT_APPOINTMENT_TAB)
    if tab not in APPOINTMENT_TABS:
        tab = DEFAULT_APPOINTMENT_TAB
    statuses = list(APPOINTMENT_TABS[tab][1])

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            semester = get_current_semester(cur)

            cur.execute(
                "SELECT COUNT(*) FILTER (WHERE status = 'pending')  AS pending, "
                "       COUNT(*) FILTER (WHERE status = 'accepted') AS active, "
                "       COUNT(*) FILTER (WHERE status IN ('completed', 'declined')) AS completed "
                "FROM appointments WHERE professional_id = %s",
                (pro_id,),
            )
            tab_counts = cur.fetchone()

            total_rows = tab_counts[tab]
            total_pages = total_pages_for(total_rows)
            page = min(parse_page(request), total_pages)

            order = {
                'pending': "a.is_new DESC, a.created_at DESC",
                'active': "a.scheduled_at ASC NULLS LAST, a.created_at",
                'completed': "COALESCE(a.scheduled_at, a.created_at) DESC",
            }[tab]                                           # fixed strings, never user input
            cur.execute(
                _ROW_SELECT + "WHERE a.professional_id = %s AND a.status = ANY(%s) "
                              f"ORDER BY {order} LIMIT %s OFFSET %s",
                (semester, pro_id, statuses, PAGE_SIZE, (page - 1) * PAGE_SIZE),
            )
            rows = _decorate(cur.fetchall())
    finally:
        conn.close()

    return render(request, 'professional/appointments.html', {
        'tab': tab,
        'show_when': tab != 'pending',
        'tabs': [{'key': key, 'label': label, 'count': tab_counts[key], 'active': key == tab}
                 for key, (label, _) in APPOINTMENT_TABS.items()],
        'rows': rows,
        'page': page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'page_numbers': get_page_range(page, total_pages),
        'page_query': f'tab={tab}',
    })


# ════════════════════════════════════════════════════════════════════
#  STUDENT DETAIL + ACTIONS
# ════════════════════════════════════════════════════════════════════

def _fetch_own_appointment(cur, appointment_id, pro_id):
    """The appointment with its student, or None if it is not this professional's."""
    cur.execute(
        "SELECT a.id, a.status, a.is_new, a.created_at, a.scheduled_at, a.student_id, "
        "       u.full_name AS student_name, s.department, s.student_id AS student_code "
        "FROM appointments a "
        "JOIN users u ON u.id = a.student_id "
        "JOIN students s ON s.user_id = a.student_id "
        "WHERE a.id = %s AND a.professional_id = %s",
        (appointment_id, pro_id),
    )
    return cur.fetchone()


@login_required_role(ROLE_PROFESSIONAL)
def appointment_detail(request, appointment_id):
    pro_id = request.session['user_id']
    answer_columns = ', '.join(QUESTION_COLS)      # constant column names, never user input
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            appointment = _fetch_own_appointment(cur, appointment_id, pro_id)
            if appointment is None:
                raise Http404('Appointment not found')

            # Opening a pending request marks it as seen.
            if appointment['status'] == 'pending' and appointment['is_new']:
                cur.execute(
                    "UPDATE appointments SET is_new = FALSE WHERE id = %s AND professional_id = %s",
                    (appointment_id, pro_id),
                )
                conn.commit()
                appointment['is_new'] = False

            result = None
            if appointment['status'] in ('pending', 'accepted'):      # answers are visible only while open
                semester = get_current_semester(cur)
                cur.execute(
                    f"SELECT final_status, status_description, submitted_at, {answer_columns} "
                    "FROM questionnaire_responses WHERE student_id = %s AND semester = %s",
                    (appointment['student_id'], semester),
                )
                result = cur.fetchone()
    finally:
        conn.close()

    appointment['status_label'], appointment['status_badge'] = APPOINTMENT_STATUS_BADGES[appointment['status']]
    context = {'appointment': appointment, 'result': None}
    if result:
        answers = {column: result[column] for column in QUESTION_COLS}
        content = STATUS_CONTENT.get(result['final_status'], {})
        context.update({
            'result': result,
            'description': result['status_description'] or content.get('summary', ''),
            'is_ai_description': bool(result['status_description']),
            'scores': scale_scores(answers),
            'groups': answer_groups(answers),
        })
    context.update({
        'now_input': datetime.now().strftime(DATETIME_INPUT_FORMAT),
        'slot_minutes': APPOINTMENT_SLOT_MINUTES,
        'list_url': safe_reverse('professional_appointments'),
    })
    return render(request, 'professional/appointment_detail.html', context)


def _back_to(appointment_id):
    return redirect('professional_appointment', appointment_id=appointment_id)


def _parse_future_time(raw):
    """The submitted time as a datetime, or (None, reason) when it can't be used."""
    try:
        when = datetime.strptime((raw or '').strip(), DATETIME_INPUT_FORMAT)
    except ValueError:
        return None, 'Please choose a date and time for the appointment.'
    now = datetime.now()
    if when <= now:
        return None, 'The appointment time must be in the future.'
    if when > now + timedelta(days=APPOINTMENT_MAX_DAYS_AHEAD):
        return None, 'That date is too far ahead. Please pick a closer one.'
    return when, None


@login_required_role(ROLE_PROFESSIONAL)
@require_POST
def appointment_accept(request, appointment_id):
    pro_id = request.session['user_id']
    when, problem = _parse_future_time(request.POST.get('scheduled_at'))
    if problem:
        messages.error(request, problem)
        return _back_to(appointment_id)

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            appointment = _fetch_own_appointment(cur, appointment_id, pro_id)
            if appointment is None:
                raise Http404('Appointment not found')
            if appointment['status'] != 'pending':
                messages.error(request, 'This request has already been answered.')
                return _back_to(appointment_id)

            # One accept at a time per professional, so two clicks cannot both pass the clash check.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (pro_id,))
            cur.execute(
                "UPDATE appointments SET status = 'accepted', scheduled_at = %s, is_new = FALSE "
                "WHERE id = %s AND professional_id = %s AND status = 'pending' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM appointments o "
                "  WHERE o.professional_id = %s AND o.status = 'accepted' AND o.id <> %s "
                "    AND o.scheduled_at > %s - make_interval(mins => %s) "
                "    AND o.scheduled_at < %s + make_interval(mins => %s)"
                ") RETURNING id",
                (when, appointment_id, pro_id, pro_id, appointment_id,
                 when, APPOINTMENT_SLOT_MINUTES, when, APPOINTMENT_SLOT_MINUTES),
            )
            done = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    if done:
        messages.success(request, f"Accepted. {appointment['student_name']} is booked for {when:%a %d %b, %I:%M %p}.")
    else:
        messages.error(request, f'You already have an appointment within {APPOINTMENT_SLOT_MINUTES} minutes of that time. Please choose another.')
    return _back_to(appointment_id)


def _change_status(request, appointment_id, from_status, to_status, success_text):
    """Move an appointment from one status to the next, only if it is still in `from_status`."""
    pro_id = request.session['user_id']
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            appointment = _fetch_own_appointment(cur, appointment_id, pro_id)
            if appointment is None:
                raise Http404('Appointment not found')
            cur.execute(
                "UPDATE appointments SET status = %s, is_new = FALSE "
                "WHERE id = %s AND professional_id = %s AND status = %s RETURNING id",
                (to_status, appointment_id, pro_id, from_status),
            )
            done = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if done:
        messages.success(request, success_text.format(name=appointment['student_name']))
    else:
        messages.error(request, 'This request has already been answered.')
    return _back_to(appointment_id)


@login_required_role(ROLE_PROFESSIONAL)
@require_POST
def appointment_decline(request, appointment_id):
    return _change_status(request, appointment_id, 'pending', 'declined', 'Request from {name} declined.')


@login_required_role(ROLE_PROFESSIONAL)
@require_POST
def appointment_release(request, appointment_id):
    return _change_status(request, appointment_id, 'accepted', 'completed', '{name} has been released and moved to Completed.')


# ════════════════════════════════════════════════════════════════════
#  CAMPUS STATS (anonymous, campus-wide, one semester at a time)
# ════════════════════════════════════════════════════════════════════

@login_required_role(ROLE_PROFESSIONAL)
def stats(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            current = get_current_semester(cur)
            semesters = list_semesters(cur)
            semester = pick_semester(request.GET.get('semester'), semesters, current)
            overview = semester_overview(cur, semester) if semester else semester_overview_empty()
            alerts = semester_alerts(cur, semester) if semester else []
    finally:
        conn.close()

    return render(request, 'professional/stats.html', {
        'semester': semester,
        'is_current': semester == current,
        'semesters': [{'name': name, 'active': name == semester} for name in semesters],
        'alerts': alerts,
        'at_risk_threshold': DEPARTMENT_AT_RISK_PCT,
        **overview,
    })