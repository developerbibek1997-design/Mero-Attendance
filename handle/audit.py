"""Request-aware helpers for the append-only member history ledger."""

from contextvars import ContextVar


_current_user = ContextVar('member_audit_user', default=None)


def get_audit_user():
    user = _current_user.get()
    return user if getattr(user, 'is_authenticated', False) else None


class MemberAuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _current_user.set(getattr(request, 'user', None))
        try:
            return self.get_response(request)
        finally:
            _current_user.reset(token)
