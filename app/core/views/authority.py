"""Authority portal views (Sprint 5): dashboard, stats and, later, events."""
import logging
from datetime import datetime

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.agents.analytics_agent import AnalyticsAgent

from core.components import (
    DASHBOARD_ALERTS_MAX,
    DASHBOARD_EVENTS_MAX,
    DEPARTMENT_AT_RISK_PCT,
    EVENT_DATE_FORMAT,
    EVENT_DESCRIPTION_MAX,
    EVENT_TIME_FORMAT,
    EVENT_TITLE_MAX,
    EVENT_VENUE_MAX,
    PAGE_SIZE,
    ROLE_AUTHORITY,
)
from core.db import connect_db, get_current_semester
from core.utils import (
    get_page_range,
    list_semesters,
    parse_page,
    pick_semester,
    safe_reverse,
    semester_alerts,
    semester_overview,
    semester_overview_empty,
    semester_trend,
    total_pages_for,
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


# ════════════════════════════════════════════════════════════════════
#  EVENTS: create, edit, delete. Only upcoming events are ever listed.
# ════════════════════════════════════════════════════════════════════

def _today(cur):
    """The database's CURRENT_DATE, the same clock that hides past events everywhere."""
    cur.execute("SELECT CURRENT_DATE AS today")
    return cur.fetchone()['today']


def clean_event_form(post, today):
    """
    Validate the event form. Returns (values, errors): `values` is what to save
    (or to show again), `errors` maps a field name to a message.
    """
    values = {
        'title': (post.get('title') or '').strip(),
        'venue': (post.get('venue') or '').strip(),
        'description': (post.get('description') or '').strip(),
        'date': (post.get('date') or '').strip(),
        'time': (post.get('time') or '').strip(),
    }
    errors = {}
    if not values['title']:
        errors['title'] = 'Please enter a title.'
    elif len(values['title']) > EVENT_TITLE_MAX:
        errors['title'] = f'The title can be at most {EVENT_TITLE_MAX} characters.'
    if not values['venue']:
        errors['venue'] = 'Please enter a venue.'
    elif len(values['venue']) > EVENT_VENUE_MAX:
        errors['venue'] = f'The venue can be at most {EVENT_VENUE_MAX} characters.'
    if len(values['description']) > EVENT_DESCRIPTION_MAX:
        errors['description'] = f'The description can be at most {EVENT_DESCRIPTION_MAX} characters.'

    try:
        when_date = datetime.strptime(values['date'], EVENT_DATE_FORMAT).date()
        if when_date < today:
            errors['date'] = 'The date cannot be in the past.'
        values['date_value'] = when_date
    except ValueError:
        errors['date'] = 'Please choose a date.'
    try:
        values['time_value'] = datetime.strptime(values['time'], EVENT_TIME_FORMAT).time()
    except ValueError:
        errors['time'] = 'Please choose a time.'
    return values, errors


@login_required_role(ROLE_AUTHORITY)
def events(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM events WHERE date >= CURRENT_DATE")
            total_rows = cur.fetchone()['n']
            total_pages = total_pages_for(total_rows)
            page = min(parse_page(request), total_pages)
            cur.execute(
                "SELECT id, title, date, time, venue, rsvp_count FROM events "
                "WHERE date >= CURRENT_DATE ORDER BY date, time, id LIMIT %s OFFSET %s",
                (PAGE_SIZE, (page - 1) * PAGE_SIZE),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return render(request, 'authority/events.html', {
        'events': rows,
        'page': page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'page_numbers': get_page_range(page, total_pages),
        'page_query': '',
        'new_url': safe_reverse('authority_event_new'),
    })


def _event_form_context(values, errors, event=None, today=None):
    return {
        'form': values,
        'errors': errors,
        'event': event,
        'min_date': today.strftime(EVENT_DATE_FORMAT) if today else '',
        'title_max': EVENT_TITLE_MAX,
        'venue_max': EVENT_VENUE_MAX,
        'description_max': EVENT_DESCRIPTION_MAX,
        'list_url': safe_reverse('authority_events'),
    }


@login_required_role(ROLE_AUTHORITY)
def event_new(request):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            today = _today(cur)
            if request.method == 'POST':
                values, errors = clean_event_form(request.POST, today)
                if not errors:
                    cur.execute(
                        "INSERT INTO events (title, date, time, venue, description, created_by) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (values['title'], values['date_value'], values['time_value'], values['venue'],
                         values['description'] or None, request.session['user_id']),
                    )
                    conn.commit()
                    messages.success(request, f"Event “{values['title']}” created.")
                    return redirect('authority_events')
            else:
                values, errors = {'title': '', 'venue': '', 'description': '', 'date': '', 'time': ''}, {}
    finally:
        conn.close()
    return render(request, 'authority/event_form.html', _event_form_context(values, errors, today=today))


@login_required_role(ROLE_AUTHORITY)
def event_edit(request, event_id):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            today = _today(cur)
            cur.execute(
                "SELECT id, title, date, time, venue, description, rsvp_count FROM events "
                "WHERE id = %s AND date >= CURRENT_DATE",
                (event_id,),
            )
            event = cur.fetchone()
            if event is None:
                raise Http404('Event not found')

            if request.method == 'POST':
                values, errors = clean_event_form(request.POST, today)
                if not errors:
                    cur.execute(
                        "UPDATE events SET title = %s, date = %s, time = %s, venue = %s, description = %s "
                        "WHERE id = %s AND date >= CURRENT_DATE",
                        (values['title'], values['date_value'], values['time_value'], values['venue'],
                         values['description'] or None, event_id),
                    )
                    conn.commit()
                    messages.success(request, f"Event “{values['title']}” updated.")
                    return redirect('authority_events')
            else:
                values, errors = {
                    'title': event['title'],
                    'venue': event['venue'],
                    'description': event['description'] or '',
                    'date': event['date'].strftime(EVENT_DATE_FORMAT),
                    'time': event['time'].strftime(EVENT_TIME_FORMAT),
                }, {}
    finally:
        conn.close()
    return render(request, 'authority/event_form.html', _event_form_context(values, errors, event, today))


@login_required_role(ROLE_AUTHORITY)
@require_POST
def event_delete(request, event_id):
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM events WHERE id = %s AND date >= CURRENT_DATE RETURNING title",
                (event_id,),
            )
            row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    if row is None:
        raise Http404('Event not found')
    messages.success(request, f"Event “{row['title']}” deleted along with its RSVPs.")
    return redirect('authority_events')