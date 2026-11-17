"""
Project-wide constants (single source of truth).

The 26-question bank (QUESTIONS, QUESTION_COLS) is added to this file in
Sprint 2. Role routing and navigation live here so that views, templates
and the navbar never hard-code them.
"""

# Display order for dropdowns; VALID_DEPARTMENTS is the set used for validation.
DEPARTMENT_CHOICES = ('CSE', 'EEE', 'BBA', 'ENG', 'ECO')
VALID_DEPARTMENTS = frozenset(DEPARTMENT_CHOICES)

# Session value for each role (matches users.role in the database).
ROLE_STUDENT = 'student'
ROLE_PROFESSIONAL = 'professional'
ROLE_AUTHORITY = 'authority'
ROLE_ADMIN = 'admin_it'

ROLE_LABELS = {
    ROLE_STUDENT: 'Student',
    ROLE_PROFESSIONAL: 'Mental Health Professional',
    ROLE_AUTHORITY: 'University Authority',
    ROLE_ADMIN: 'Admin IT',
}

# URL *names* — each is defined in the sprint that builds that portal.
ROLE_DASHBOARD = {
    ROLE_STUDENT: 'student_dashboard',
    ROLE_PROFESSIONAL: 'professional_dashboard',
    ROLE_AUTHORITY: 'authority_dashboard',
    ROLE_ADMIN: 'admin_dashboard',
}

# CSS class on the page wrapper for each role (see layout.css).
# Each role signs in on its own page (URL names, see core/urls.py).
ROLE_LOGIN = {
    ROLE_STUDENT: 'login',
    ROLE_PROFESSIONAL: 'professional_login',
    ROLE_AUTHORITY: 'authority_login',
    ROLE_ADMIN: 'admin_login',
}

# Wording on each role's sign-in page.
ROLE_LOGIN_TEXT = {
    ROLE_STUDENT: ('Student sign in', 'Sign in to your Baymax student account'),
    ROLE_PROFESSIONAL: ('Professional sign in', 'Mental health professionals sign in here'),
    ROLE_AUTHORITY: ('Authority sign in', 'University authorities sign in here'),
    ROLE_ADMIN: ('Admin IT sign in', 'Admin IT staff sign in here'),
}

ROLE_TINT = {
    ROLE_STUDENT: 'tint-student',
    ROLE_PROFESSIONAL: 'tint-professional',
    ROLE_AUTHORITY: 'tint-authority',
    ROLE_ADMIN: 'tint-admin',
}

# Navbar: (label, url name). A link whose URL name does not exist yet
# (portal not built) is simply left out of the navbar.
ROLE_NAV = {
    ROLE_STUDENT: [
        ('Dashboard', 'student_dashboard'),
        ('Assessment', 'chatbot'),
        ('Status', 'student_status'),
        ('Events', 'student_events'),
        ('Help', 'student_help'),
        ('Profile', 'student_profile'),
    ],
    ROLE_PROFESSIONAL: [
        ('Dashboard', 'professional_dashboard'),
        ('Appointments', 'professional_appointments'),
        ('Stats', 'professional_stats'),
    ],
    ROLE_AUTHORITY: [
        ('Dashboard', 'authority_dashboard'),
        ('Stats', 'authority_stats'),
        ('Events', 'authority_events'),
    ],
    ROLE_ADMIN: [
        ('Dashboard', 'admin_dashboard'),
        ('Users', 'admin_users'),
        ('Appointments', 'admin_appointments'),
        ('Events', 'admin_events'),
        ('Semester', 'admin_semester'),
    ],
}

ALL_ROLES = (ROLE_STUDENT, ROLE_PROFESSIONAL, ROLE_AUTHORITY, ROLE_ADMIN)

# ── Authentication limits ─────────────────────────────────────────────────────
LOGIN_MAX_ATTEMPTS = 5            # failed logins allowed ...
LOGIN_WINDOW_SECONDS = 15 * 60    # ... within this window, then temporary lockout
OTP_TTL_SECONDS = 10 * 60         # registration OTP is valid for 10 minutes
OTP_RESEND_SECONDS = 5 * 60       # a new OTP can be requested every 5 minutes
OTP_MAX_ATTEMPTS = 5              # wrong codes allowed before a new code is required
EMAIL_SEND_TIMEOUT_SECONDS = 10   # give up on the mail server after this long

# ── Google sign-in ────────────────────────────────────────────────────────────
GOOGLE_PROFILE_KEY = 'google_profile'       # session key holding the verified Google identity
GOOGLE_PROFILE_TTL_SECONDS = 15 * 60        # finish the Google sign-up form within 15 minutes


# ── The 26-question assessment ────────────────────────────────────────────────
# Wording and answer labels are copied from the survey the SVM was trained on
# (mhp_dataset.csv). Each answer's NUMBER is what is stored and sent to the model.
SCALE_PSS, SCALE_GAD, SCALE_PHQ = 'PSS-10', 'GAD-7', 'PHQ-9'
SCALE_TITLES = {
    SCALE_PSS: 'Stress scale',
    SCALE_GAD: 'Anxiety scale',
    SCALE_PHQ: 'Depression scale',
}

OPTIONS_PSS = ((0, 'Never'), (1, 'Almost Never'), (2, 'Sometimes'), (3, 'Fairly Often'), (4, 'Very Often'))
OPTIONS_GAD1 = ((0, 'Not at all'), (1, 'Several days (less than 15 days)'),
                (2, 'More than half the semester'), (3, 'Nearly every day'))
OPTIONS_DAYS = ((0, 'Not at all'), (1, 'Several days'), (2, 'More than half the days'), (3, 'Nearly every day'))

_QUESTION_TEXTS = (
    'In a semester, how often have you felt upset due to something that happened in your academic affairs?',
    'In a semester, how often you felt as if you were unable to control important things in your academic affairs?',
    'In a semester, how often you felt nervous and stressed because of academic pressure?',
    'In a semester, how often you felt as if you could not cope with all the mandatory academic activities? (e.g, assignments, quiz, exams)',
    'In a semester, how often you felt confident about your ability to handle your academic / university problems?',
    'In a semester, how often you felt as if things in your academic life is going on your way?',
    'In a semester, how often are you able to control irritations in your academic / university affairs?',
    'In a semester, how often you felt as if your academic performance was on top?',
    'In a semester, how often you got angered due to bad performance or low grades that is beyond your control?',
    'In a semester, how often you felt as if academic difficulties are piling up so high that you could not overcome them?',
    'In a semester, how often you felt nervous, anxious or on edge due to academic pressure?',
    'In a semester, how often have you been unable to stop worrying about your academic affairs?',
    'In a semester, how often have you had trouble relaxing due to academic pressure?',
    'In a semester, how often have you been easily annoyed or irritated because of academic pressure?',
    'In a semester, how often have you worried too much about academic affairs?',
    'In a semester, how often have you been so restless due to academic pressure that it is hard to sit still?',
    'In a semester, how often have you felt afraid, as if something awful might happen?',
    'In a semester, how often have you had little interest or pleasure in doing things?',
    'In a semester, how often have you been feeling down, depressed or hopeless?',
    'In a semester, how often have you had trouble falling or staying asleep, or sleeping too much?',
    'In a semester, how often have you been feeling tired or having little energy?',
    'In a semester, how often have you had poor appetite or overeating?',
    'In a semester, how often have you been feeling bad about yourself - or that you are a failure or have let yourself or your family down?',
    'In a semester, how often have you been having trouble concentrating on things, such as reading the books or watching television?',
    "In a semester, how often have you moved or spoke too slowly for other people to notice? Or you've been moving a lot more than usual because you've been restless?",
    'In a semester, how often have you had thoughts that you would be better off dead, or of hurting yourself?',
)

QUESTION_COLS = (
    tuple(f'pss{i}' for i in range(1, 11))
    + tuple(f'gad{i}' for i in range(1, 8))
    + tuple(f'phq{i}' for i in range(1, 10))
)


def _build_questions():
    questions = []
    for index, (column, text) in enumerate(zip(QUESTION_COLS, _QUESTION_TEXTS), start=1):
        if column.startswith('pss'):
            scale, options = SCALE_PSS, OPTIONS_PSS
        elif column == 'gad1':
            scale, options = SCALE_GAD, OPTIONS_GAD1
        else:
            scale, options = (SCALE_GAD if column.startswith('gad') else SCALE_PHQ), OPTIONS_DAYS
        questions.append({
            'number': index,
            'column': column,
            'scale': scale,
            'scale_title': SCALE_TITLES[scale],
            'text': text,
            'options': options,
            'valid_values': frozenset(value for value, _ in options),
        })
    return tuple(questions)


QUESTIONS = _build_questions()
QUESTION_COUNT = len(QUESTIONS)          # 26
SELF_HARM_COLUMN = 'phq9'                # any answer above 0 shows the support note
STATUS_STABLE, STATUS_CHALLENGED, STATUS_CRITICAL = 'Stable', 'Challenged', 'Critical'


# ── What each status means (shown on the status page and dashboard) ───────────
# Built-in wording. It is the permanent fallback; the AI-written description
# (Sprint 3) replaces `summary` on the status page when it is available.
STATUS_CONTENT = {
    STATUS_STABLE: {
        'icon': '✅',
        'headline': "You're doing well!",
        'short': "You're managing stress well this semester.",
        'summary': ('Your answers across the stress, anxiety and mood scales point to low levels of '
                    'distress this semester.'),
        'tip': 'Keep up the habits that work for you: regular sleep, movement, and time with people you trust.',
    },
    STATUS_CHALLENGED: {
        'icon': '⚠️',
        'headline': 'This semester is weighing on you',
        'short': "You're carrying some stress. Support is available.",
        'summary': ('Your answers point to a noticeable level of stress, worry or low mood. '
                    'This is common among students, and it is worth paying attention to.'),
        'tip': 'Small steps help: talk to someone you trust, plan short breaks, and consider joining a campus event or speaking with a counselor.',
    },
    STATUS_CRITICAL: {
        'icon': '🆘',
        'headline': 'Please reach out for support',
        'short': 'Your answers suggest you are struggling. Please reach out.',
        'summary': ('Your answers point to a high level of stress, anxiety or low mood. '
                    'You do not have to handle this alone, and talking to a professional can really help.'),
        'tip': 'We recommend requesting an appointment with a mental health professional as soon as you can.',
    },
}