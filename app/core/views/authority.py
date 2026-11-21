"""Authority portal views (Sprint 5): dashboard, stats and, later, events."""
import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.agents.analytics_agent import AnalyticsAgent

from core.components import (
    DASHBOARD_ALERTS_MAX,
    DASHBOARD_EVENTS_MAX,
    DEPARTMENT_AT_RISK_PCT,
    ROLE_AUTHORITY,
)
from core.db import connect_db, get_current_semester
from core.utils import (
    list_semesters,
    pick_semester,
    safe_reverse,
    semester_alerts,
    semester_overview,
    semester_overview_empty,
    semester_trend,
)
from core.views.auth import login_required_role

logger = logging.getLogger(__name__)


@login_required_role(ROLE_AUTHORITY)
def dashboard(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            semester = get_current_semester(cur)
            overview = semester_overview(cur, semester) if semester else semester_overview_empty()
            alerts = semester_alerts(cur, semester, include_dismissed=False)[:DASHBOARD_ALERTS_MAX] if semester else []
            cur.execute(
                "SELECT id, title, date, time, venue, rsvp_count FROM events "
                "WHERE date >= CURRENT_DATE ORDER BY date, time"
            )
            events = cur.fetchall()
    finally:
        conn.close()

    return render(request, 'authority/dashboard.html', {
        'semester': semester,
        'alerts': alerts,
        'can_dismiss': True,
        'next_page': 'dashboard',
        'events_total': len(events),
        'events': events[:DASHBOARD_EVENTS_MAX],
        'at_risk_departments': [d for d in overview['departments'] if d['is_at_risk']],
        'at_risk_threshold': DEPARTMENT_AT_RISK_PCT,
        'stats_url': safe_reverse('authority_stats'),
        'events_url': safe_reverse('authority_events'),
        **overview,
    })


@login_required_role(ROLE_AUTHORITY)
def stats(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            current = get_current_semester(cur)
            semesters = list_semesters(cur)
            semester = pick_semester(request.GET.get('semester'), semesters, current)
            overview = semester_overview(cur, semester) if semester else semester_overview_empty()
            if semester and semester == current and overview['total']:
                _generate_alerts(request, semester, overview)
            alerts = semester_alerts(cur, semester) if semester else []
            trend = semester_trend(cur)
    finally:
        conn.close()

    return render(request, 'authority/stats.html', {
        'semester': semester,
        'is_current': semester == current,
        'semesters': [{'name': name, 'active': name == semester} for name in semesters],
        'alerts': alerts,
        'can_dismiss': True,
        'next_page': 'stats',
        'trend': trend,
        'at_risk_threshold': DEPARTMENT_AT_RISK_PCT,
        **overview,
    })


def _generate_alerts(request, semester, overview):
    """Create any missing alerts for the current semester. A failure here never breaks the page."""
    try:
        created = AnalyticsAgent().run(semester, overview)
    except Exception:
        logger.exception('Alert generation failed')
        return
    if created:
        messages.info(request, f"{created} new alert{'s' if created != 1 else ''} created from this semester's figures.")


@login_required_role(ROLE_AUTHORITY)
@require_POST
def alert_dismiss(request, alert_id):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE analytics_alerts SET dismissed = TRUE WHERE id = %s RETURNING semester", (alert_id,))
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise Http404('Alert not found')
    messages.success(request, 'Alert dismissed.')
    if request.POST.get('next') == 'dashboard':
        return redirect('authority_dashboard')
    return redirect(f"{safe_reverse('authority_stats')}?semester={row['semester']}")