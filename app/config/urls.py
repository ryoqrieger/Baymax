from django.urls import include, path

urlpatterns = [
    path('accounts/', include('allauth.urls')),  # Google OAuth handshake only
    path('', include('core.urls')),
]