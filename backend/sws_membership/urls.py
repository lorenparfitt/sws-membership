"""URL wiring only: the JSON API, the health check and Django's admin."""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from sws_membership.api import api


def health(request):
    """Liveness endpoint used by the container host and the test suite."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health", health),
    path("api/", api.urls),
    path("django-admin/", admin.site.urls),
]
