from django.shortcuts import render

from core.components import ROLE_STUDENT
from core.views.auth import login_required_role


@login_required_role(ROLE_STUDENT)
def dashboard(request):
    """Placeholder dashboard — replaced by the full portal in a later sprint."""
    return render(request, 'student/dashboard.html')