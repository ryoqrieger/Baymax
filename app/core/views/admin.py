from django.shortcuts import render

from core.components import ROLE_ADMIN
from core.views.auth import login_required_role


@login_required_role(ROLE_ADMIN)
def dashboard(request):
    """Placeholder dashboard — replaced by the full portal in a later sprint."""
    return render(request, 'admin/dashboard.html')