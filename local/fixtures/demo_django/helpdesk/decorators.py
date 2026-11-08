from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def role_required(role):
    """Only users with this role (support operators, ...)."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role != role:
                return HttpResponseForbidden()
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
