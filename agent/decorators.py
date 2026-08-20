from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden
from django.contrib import messages


def agent_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('management:homepage')
        if request.user.user_type != "4":
            return HttpResponseForbidden("Access denied. Agent account required.")
        try:
            agent = request.user.agent_profile
        except Exception:
            return HttpResponseForbidden("Agent profile not found.")
        if agent.status == 'suspended':
            messages.error(request, "Your agent account has been suspended. Please contact support.")
            return redirect('management:homepage')
        return view_func(request, *args, **kwargs)
    return wrapper


def get_agent_profile(request):
    try:
        return request.user.agent_profile
    except Exception:
        return None


def check_agent_org_ownership(agent, org_id):
    """Return organization only if it belongs to this agent, else None."""
    from management.models import Organization
    try:
        return agent.organizations.get(id=org_id)
    except Organization.DoesNotExist:
        return None
