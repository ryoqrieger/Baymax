"""Professional portal views (Sprint 4)."""
from django.shortcuts import render

from core.components import (
    APPOINTMENT_STATUS_BADGES,
    APPOINTMENT_TABS,
    DEFAULT_APPOINTMENT_TAB,
    PAGE_SIZE,
    ROLE_PROFESSIONAL,
)
from core.db import connect_db, get_current_semester
from core.utils import get_page_range, parse_page, safe_reverse, total_pages_for
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
                              "AND a.scheduled_at >= NOW() ORDER BY a.scheduled_at LIMIT 5",
                (semester, pro_id),
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