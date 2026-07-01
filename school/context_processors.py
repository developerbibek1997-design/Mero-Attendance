"""
Context processor: inject org, features, and staff_perms into every template.

Template usage:
    {% if features.payroll %}   → feature enabled for this org
    {% if staff_perms.can_view_payroll %}  → this user has the permission
    {{ org.name }}              → current organization
"""

from school.features import get_org_for_user, OrgFeatures, get_staff_permissions


def org_and_features(request):
    if not request.user.is_authenticated:
        return {}

    org = get_org_for_user(request.user)

    # Superadmin browsing a specific org (passed via session by superadmin views)
    if org is None and request.user.user_type == '1':
        org_id = request.session.get('viewed_org_id')
        if org_id:
            try:
                from management.models import Organization
                org = Organization.objects.get(pk=org_id)
            except Exception:
                org = None

    features = OrgFeatures(org)
    staff_perms = get_staff_permissions(request.user)

    return {
        'org': org,
        'features': features,
        'staff_perms': staff_perms,
        # Keep backward compat: old templates use `org.feature_payroll` directly
        # (org is already injected above; no extra work needed)
    }
