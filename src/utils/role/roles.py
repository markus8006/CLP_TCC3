from functools import wraps
from flask import abort, flash
from flask_login import current_user

def role_required(min_role):
    def wrapper(fn):
        @wraps(fn)
        def decorator_view(*args, **kwargs):
            if not current_user.has_permission(min_role):
                flash(f"O usuario {current_user} não tem permissão suficiente")
                abort(403)
            return fn(*args, **kwargs)
        return decorator_view
    return wrapper