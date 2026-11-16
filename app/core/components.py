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