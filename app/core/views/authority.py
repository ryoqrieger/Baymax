from django.shortcuts import render

from core.components import ROLE_AUTHORITY
from core.views.auth import login_required_role


@login_required_role(ROLE_AUTHORITY)
def dashboard(request):
    """Placeholder dashboard — replaced by the full portal in a later sprint."""
    return render(request, 'authority/dashboard.html')