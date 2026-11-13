"""
Project-wide constants (single source of truth).

The 26-question bank (QUESTIONS, QUESTION_COLS) is added to this file in
Sprint 2. Role routing and navigation live here so that views, templates
and the navbar never hard-code them.
"""

VALID_DEPARTMENTS = frozenset({'CSE', 'EEE', 'ENG', 'ECO', 'BBA'})

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