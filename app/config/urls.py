from django.urls import include, path

urlpatterns = [
    # Only the Google handshake routes are exposed (not allauth's own
    # login / signup pages): /accounts/google/login/ and its callback.
    path('accounts/', include('allauth.socialaccount.providers.google.urls')),
    path('', include('core.urls')),
]