"""Hand the browser a CSRF cookie on every API response.

The React app sends the cookie's value back as the X-CSRFToken header on
writes. Django only sets the cookie once something asks for the token, so
this middleware asks on every API request.
"""

from django.middleware.csrf import get_token


class EnsureCsrfCookie:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            get_token(request)
        return self.get_response(request)
