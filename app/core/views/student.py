"""Student portal views. Sprint 2: dashboard, assessment, status, help, events, profile."""
import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core import ml
from django.contrib.auth.hashers import is_password_usable

from core.components import (
    QUESTION_COLS,
    QUESTION_COUNT,
    QUESTIONS,
    ROLE_STUDENT,
    SELF_HARM_COLUMN,
    STATUS_CONTENT,
    STATUS_CRITICAL,
)
from core.db import connect_db, get_current_semester
from core.utils import safe_reverse
from core.views.auth import login_required_role

logger = logging.getLogger(__name__)

ASSESSMENT_KEY = 'assessment'   # session: {'semester': 'Fall 2026', 'answers': {'1': 2, ...}}


@login_required_role(ROLE_STUDENT)
def dashboard(request):
    """Status summary, appointment badge and the next upcoming events."""
    user_id = request.session['user_id']
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            semester = get_current_semester(cur)

            result = None
            if semester:
                cur.execute(
                    "SELECT final_status FROM questionnaire_responses "
                    "WHERE student_id = %s AND semester = %s",
                    (user_id, semester),
                )
                result = cur.fetchone()

            cur.execute(
                "SELECT COUNT(*) FILTER (WHERE status = 'pending')  AS pending, "
                "       COUNT(*) FILTER (WHERE status = 'accepted') AS accepted "
                "FROM appointments WHERE student_id = %s",
                (user_id,),
            )
            counts = cur.fetchone()

            cur.execute(
                "SELECT scheduled_at FROM appointments "
                "WHERE student_id = %s AND status = 'accepted' AND scheduled_at >= NOW() "
                "ORDER BY scheduled_at LIMIT 1",
                (user_id,),
            )
            next_appointment = cur.fetchone()

            cur.execute(
                "SELECT id, title, date, time FROM events "
                "WHERE date >= CURRENT_DATE ORDER BY date, time LIMIT 3"
            )
            events = cur.fetchall()
    finally:
        conn.close()

    status = result['final_status'] if result else None
    return render(request, 'student/dashboard.html', {
        'semester': semester,
        'status': status,
        'status_content': STATUS_CONTENT.get(status),
        'pending_count': counts['pending'],
        'accepted_count': counts['accepted'],
        'next_appointment': next_appointment['scheduled_at'] if next_appointment else None,
        'events': events,
        'help_url': safe_reverse('student_help'),
        'events_url': safe_reverse('student_events'),
    })


@login_required_role(ROLE_STUDENT)
def status(request):
    """This semester's classification and description, plus earlier semesters."""
    user_id = request.session['user_id']
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            semester = get_current_semester(cur)
            cur.execute(
                f"SELECT semester, final_status, status_description, submitted_at, {SELF_HARM_COLUMN} "
                "FROM questionnaire_responses WHERE student_id = %s ORDER BY submitted_at DESC",
                (user_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    current = next((r for r in rows if r['semester'] == semester), None)
    history = [r for r in rows if r is not current]

    content = STATUS_CONTENT.get(current['final_status']) if current else None
    description = None
    if current:
        description = current['status_description'] or content['summary']

    # Support note: a Critical result, or any answer above 0 on the self-harm question.
    needs_support_note = bool(current) and (
        current['final_status'] == STATUS_CRITICAL or (current[SELF_HARM_COLUMN] or 0) > 0
    )

    return render(request, 'student/status.html', {
        'semester': semester,
        'current': current,
        'content': content,
        'description': description,
        'is_ai_description': bool(current and current['status_description']),
        'needs_support_note': needs_support_note,
        'history': history,
        'assessment_url': safe_reverse('chatbot'),
        'help_url': safe_reverse('student_help'),
    })


@login_required_role(ROLE_STUDENT)
def profile(request):
    """Read-only account details."""
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.full_name, u.email, u.created_at, u.password, "
                "       s.student_id, s.department "
                "FROM users u JOIN students s ON s.user_id = u.id WHERE u.id = %s",
                (request.session['user_id'],),
            )
            account = cur.fetchone()
    finally:
        conn.close()

    if account is None:   # removed while signed in
        request.session.flush()
        return redirect('login')

    has_password = is_password_usable(account['password'])
    return render(request, 'student/profile.html', {
        'account': account,
        'sign_in_method': 'Email and password' if has_password else 'Google (no password set)',
        'has_password': has_password,
    })


# ════════════════════════════════════════════════════════════════════
#  ASSESSMENT (chatbot): 26 questions, one per page
#  Answers stay in the session until question 26; only then is one row
#  written to questionnaire_responses (one per student per semester).
# ════════════════════════════════════════════════════════════════════

def _load_state(request, semester):
    """The in-progress assessment for this semester (a fresh one if none/outdated)."""
    state = request.session.get(ASSESSMENT_KEY)
    if not state or state.get('semester') != semester:
        state = {'semester': semester, 'answers': {}}
    return state


def _save_state(request, state):
    request.session[ASSESSMENT_KEY] = state   # reassigned, so the session notices the change


def _first_unanswered(state):
    """Number (1-26) of the first unanswered question, or None when all are answered."""
    for number in range(1, QUESTION_COUNT + 1):
        if str(number) not in state['answers']:
            return number
    return None


def _fetch_result(user_id, semester):
    """This student's saved result for the semester, or None."""
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT final_status, submitted_at FROM questionnaire_responses "
                "WHERE student_id = %s AND semester = %s",
                (user_id, semester),
            )
            return cur.fetchone()
    finally:
        conn.close()


def _current_semester():
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            return get_current_semester(cur)
    finally:
        conn.close()


@login_required_role(ROLE_STUDENT)
def chatbot(request):
    """Assessment home: start, continue, or show the finished result."""
    semester = _current_semester()
    if semester is None:
        messages.error(request, 'No semester is active right now, so the assessment is closed.')
        return redirect('student_dashboard')

    result = _fetch_result(request.session['user_id'], semester)
    state = _load_state(request, semester)
    answered = len(state['answers'])
    next_number = _first_unanswered(state) or QUESTION_COUNT

    return render(request, 'student/chatbot_intro.html', {
        'semester': semester,
        'result': result,
        'answered': answered,
        'next_number': next_number,
        'status_url': safe_reverse('student_status'),
        'question_count': QUESTION_COUNT,
    })


@login_required_role(ROLE_STUDENT)
@require_http_methods(['GET', 'POST'])
def chatbot_question(request, number):
    if not 1 <= number <= QUESTION_COUNT:
        return redirect('chatbot')

    # Question 1 is the entry point: check once (not on every page) that this
    # semester's assessment has not been submitted already.
    if number == 1 and request.method == 'GET':
        semester = _current_semester()
        if semester is None or _fetch_result(request.session['user_id'], semester):
            return redirect('chatbot')
        state = _load_state(request, semester)
        _save_state(request, state)
    else:
        state = request.session.get(ASSESSMENT_KEY)
        if not state:
            return redirect('chatbot')

    # No skipping ahead: you may open any answered question or the next one.
    allowed_up_to = _first_unanswered(state) or QUESTION_COUNT
    if number > allowed_up_to:
        return redirect('chatbot_question', number=allowed_up_to)

    question = QUESTIONS[number - 1]
    key = str(number)

    if request.method == 'POST':
        action = request.POST.get('action', 'next')
        raw = request.POST.get('answer', '')
        chosen = None
        if raw.isdigit() and int(raw) in question['valid_values']:
            chosen = int(raw)
            state['answers'][key] = chosen
            _save_state(request, state)

        if action == 'prev':
            if number == 1:
                return redirect('chatbot')
            return redirect('chatbot_question', number=number - 1)

        if key not in state['answers']:
            messages.error(request, 'Please choose an answer to continue.')
        elif number < QUESTION_COUNT:
            return redirect('chatbot_question', number=number + 1)
        else:
            return _finish(request, state)

    previous = None
    if number > 1 and str(number - 1) in state['answers']:
        prev_q = QUESTIONS[number - 2]
        prev_value = state['answers'][str(number - 1)]
        previous = {
            'number': prev_q['number'],
            'text': prev_q['text'],
            'answer': dict(prev_q['options'])[prev_value],
            'value': prev_value,
        }

    return render(request, 'student/chatbot_question.html', {
        'question': question,
        'selected': state['answers'].get(key),
        'percent': round(number / QUESTION_COUNT * 100),
        'previous': previous,
        'is_last': number == QUESTION_COUNT,
        'question_count': QUESTION_COUNT,
    })


def _finish(request, state):
    """All 26 answered: classify with the SVM, save once, clear the session copy."""
    user_id = request.session['user_id']
    answers = [state['answers'].get(str(n)) for n in range(1, QUESTION_COUNT + 1)]
    if None in answers:
        return redirect('chatbot_question', number=_first_unanswered(state))

    try:
        status = ml.predict(answers)
    except Exception:
        logger.exception('Assessment prediction failed')
        messages.error(request, 'We could not process your answers just now. Please press Finish again.')
        return redirect('chatbot_question', number=QUESTION_COUNT)

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            semester = get_current_semester(cur)
            if semester != state['semester']:
                request.session.pop(ASSESSMENT_KEY, None)
                messages.error(request, 'A new semester has started. Please take the assessment again.')
                return redirect('chatbot')

            columns = ', '.join(QUESTION_COLS)
            placeholders = ', '.join(['%s'] * QUESTION_COUNT)
            cur.execute(
                f"INSERT INTO questionnaire_responses "     # column names come from a constant, never from input
                f"(student_id, semester, {columns}, final_status) "
                f"VALUES (%s, %s, {placeholders}, %s) "
                f"ON CONFLICT (student_id, semester) DO NOTHING RETURNING id",
                (user_id, semester, *answers, status),
            )
            saved = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    request.session.pop(ASSESSMENT_KEY, None)
    if saved:
        messages.success(request, 'Assessment complete. Thank you for answering all 26 questions.')
    else:
        messages.info(request, 'You had already completed this semester’s assessment.')
    return redirect('chatbot')