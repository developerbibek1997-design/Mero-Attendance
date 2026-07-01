"""
Decorators for feature and permission enforcement on views.

Usage:
    from school.decorators import feature_required, perm_required, org_admin_required

    @feature_required('payroll')
    def my_view(request): ...

    @perm_required('can_approve_leave')
    def approve_leave(request, id): ...

Works with both function-based and class-based views (use dispatch override for CBVs,
or apply via @method_decorator).
"""

from functools import wraps
from django.shortcuts import render, redirect
from django.contrib import messages
from school.features import get_org_for_user, has_feature, has_perm, get_staff_permissions


def _denied_response(request, reason="You don't have access to this feature."):
    """Return a clean 403 page."""
    return render(request, '403.html', {'reason': reason}, status=403)


def feature_required(feature_key: str):
    """
    Decorator: block view if the org doesn't have `feature_key` enabled.
    Superadmin always passes (they need to configure features).
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ut = getattr(request.user, 'user_type', '')
            if ut == '1':               # superadmin bypasses feature checks
                return view_func(request, *args, **kwargs)
            org = get_org_for_user(request.user)
            if not has_feature(org, feature_key):
                return _denied_response(
                    request,
                    f"The '{feature_key}' module is not enabled for your organization."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def perm_required(perm_key: str):
    """
    Decorator: block view if staff doesn't have `perm_key` permission.
    Schooladmin and superadmin always pass.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            ut = getattr(request.user, 'user_type', '')
            if ut in ('1', '2'):
                return view_func(request, *args, **kwargs)
            if not has_perm(request.user, perm_key):
                return _denied_response(
                    request,
                    "You don't have permission to access this page. Contact your administrator."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def org_admin_required(view_func):
    """Block non-admin users (staff user_type=3) from admin-only views."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        ut = getattr(request.user, 'user_type', '')
        if ut not in ('1', '2'):
            return _denied_response(request, "This page is only accessible to organization administrators.")
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Mixin for Class-Based Views
# ---------------------------------------------------------------------------

class FeatureRequiredMixin:
    """
    CBV mixin: set `required_feature = 'payroll'` on the view class.
    """
    required_feature = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_feature:
            ut = getattr(request.user, 'user_type', '')
            if ut != '1':
                org = get_org_for_user(request.user)
                if not has_feature(org, self.required_feature):
                    return _denied_response(
                        request,
                        f"The '{self.required_feature}' module is not enabled for your organization."
                    )
        return super().dispatch(request, *args, **kwargs)


class PermRequiredMixin:
    """
    CBV mixin: set `required_perm = 'can_view_payroll'` on the view class.
    """
    required_perm = None

    def dispatch(self, request, *args, **kwargs):
        if self.required_perm:
            ut = getattr(request.user, 'user_type', '')
            if ut not in ('1', '2'):
                if not has_perm(request.user, self.required_perm):
                    return _denied_response(
                        request,
                        "You don't have permission to access this page."
                    )
        return super().dispatch(request, *args, **kwargs)
