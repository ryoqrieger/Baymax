"""Student portal views. Sprint 2: dashboard, assessment, status, help, events, profile."""
import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core import ml
from core.components import (
    QUESTION_COLS,
    QUESTION_COUNT,
    QUESTIONS,
    ROLE_STUDENT,
)
from core.db import connect_db, get_current_semester
from core.utils import safe_reverse
from core.views.auth import login_required_role

logger = logging.getLogger(__name__)

ASSESSMENT_KEY = 'assessment'   # session: {'semester': 'Fall 2026', 'answers': {'1': 2, ...}}


@login_required_role(ROLE_STUDENT)
def dashboard(request):
    """Placeholder dashboard — replaced by the full dashboard in Sprint 2"""
    return render(request, 'student/dashboard.html')


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