"""
Core URL routes. Routes are added sprint by sprint:
Sprint 1 auth, Sprint 2 student, Sprint 4 professional,
Sprint 5 authority, Sprint 6 admin.
"""
from django.urls import path

from core.components import ROLE_ADMIN, ROLE_AUTHORITY, ROLE_PROFESSIONAL, ROLE_STUDENT
from core.views import admin, auth, authority, professional, student

urlpatterns = [
    # ── Auth (all roles) ──
    path('', auth.landing, name='landing'),
    path('login/', auth.login_view, {'portal_role': ROLE_STUDENT}, name='login'),
    path('professional/login/', auth.login_view, {'portal_role': ROLE_PROFESSIONAL}, name='professional_login'),
    path('authority/login/', auth.login_view, {'portal_role': ROLE_AUTHORITY}, name='authority_login'),
    path('admin/login/', auth.login_view, {'portal_role': ROLE_ADMIN}, name='admin_login'),
    path('logout/', auth.logout_view, name='logout'),
    path('register/', auth.register, name='register'),
    path('register/verify/', auth.register_verify, name='register_verify'),
    path('register/resend/', auth.register_resend, name='register_resend'),
    path('register/cancel/', auth.register_cancel, name='register_cancel'),
    path('auth/google/', auth.google_start, name='google_start'),
    path('auth/google/complete/', auth.google_complete, name='google_complete'),
    path('account/password/', auth.change_password, name='change_password'),

    # ── Dashboards (placeholders until their sprint) ──
    path('student/dashboard/', student.dashboard, name='student_dashboard'),
    # ── Student portal ──
    path('student/help/', student.help_page, name='student_help'),
    path('student/help/request/<int:professional_id>/', student.help_request, name='student_help_request'),
    path('student/events/', student.events_page, name='student_events'),
    path('student/events/<int:event_id>/rsvp/', student.event_rsvp, name='student_event_rsvp'),
    path('student/status/', student.status, name='student_status'),
    path('student/profile/', student.profile, name='student_profile'),
    path('student/assessment/', student.chatbot, name='chatbot'),
    path('student/assessment/q/<int:number>/', student.chatbot_question, name='chatbot_question'),

    path('professional/dashboard/', professional.dashboard, name='professional_dashboard'),
    path('professional/appointments/', professional.appointments, name='professional_appointments'),
    path('professional/stats/', professional.stats, name='professional_stats'),
    path('professional/appointments/<int:appointment_id>/', professional.appointment_detail, name='professional_appointment'),
    path('professional/appointments/<int:appointment_id>/accept/', professional.appointment_accept, name='professional_appointment_accept'),
    path('professional/appointments/<int:appointment_id>/decline/', professional.appointment_decline, name='professional_appointment_decline'),
    path('professional/appointments/<int:appointment_id>/release/', professional.appointment_release, name='professional_appointment_release'),
    path('authority/dashboard/', authority.dashboard, name='authority_dashboard'),
    path('admin/dashboard/', admin.dashboard, name='admin_dashboard'),
]