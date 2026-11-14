"""
Core URL routes. Routes are added sprint by sprint:
Sprint 1 auth, Sprint 2 student, Sprint 4 professional,
Sprint 5 authority, Sprint 6 admin.
"""
from django.urls import path

from core.views import admin, auth, authority, professional, student

urlpatterns = [
    # ── Auth (all roles) ──
    path('', auth.index, name='landing'),
    path('login/', auth.login_view, name='login'),
    path('logout/', auth.logout_view, name='logout'),
    path('account/password/', auth.change_password, name='change_password'),

    # ── Dashboards (placeholders until their sprint) ──
    path('student/dashboard/', student.dashboard, name='student_dashboard'),
    path('professional/dashboard/', professional.dashboard, name='professional_dashboard'),
    path('authority/dashboard/', authority.dashboard, name='authority_dashboard'),
    path('admin/dashboard/', admin.dashboard, name='admin_dashboard'),
]