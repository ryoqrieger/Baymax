"""
Core URL routes. Routes are added sprint by sprint:
Sprint 1 auth, Sprint 2 student, Sprint 4 professional,
Sprint 5 authority, Sprint 6 admin.
"""
from django.conf import settings
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = []

if settings.DEBUG:
    # TEMPORARY (Sprint 0): visual check of the design system.
    # Delete this block and templates/_design_check.html after you approve it.
    urlpatterns += [
        path('design-check/', TemplateView.as_view(template_name='_design_check.html'), name='design_check'),
    ]