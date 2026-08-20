"""
Context processor: inject org, features, and staff_perms into every template.

Template usage:
    {% if features.payroll %}   → feature enabled for this org
    {% if staff_perms.can_view_payroll %}  → this user has the permission
    {{ org.name }}              → current organization
"""

from school.features import get_org_for_user, OrgFeatures, get_staff_permissions, has_perm, has_feature
from school.breadcrumbs import build_breadcrumbs
from school.terminology import get_terms


class _OneShotMessages:
    """Expose Django messages to the first renderer only.

    ``dashboard.html`` now owns message rendering. A number of older child
    templates still contain local message loops; making this iterable
    one-shot prevents the same message from appearing twice without breaking
    standalone legacy templates that do not use the dashboard base.
    """

    def __init__(self, storage):
        self.storage = storage
        self.consumed = False

    def __iter__(self):
        if self.consumed:
            return iter(())
        self.consumed = True
        return iter(self.storage)

    def __len__(self):
        return 0 if self.consumed else len(self.storage)

    def __bool__(self):
        return not self.consumed and bool(self.storage)


def _dynamic_features_for_sidebar(user, org):
    """
    Enabled dynamic (superadmin-defined) features the current user can see —
    additive to the hand-written nav for the 31 legacy features. Admin/superadmin
    see every enabled feature; staff only see ones with at least one granted
    permission (or with no permissions defined at all, i.e. purely informational).
    """
    ut = getattr(user, 'user_type', '')
    if org is None or ut not in ('2', '3'):
        return []
    from django.urls import reverse
    from handle.models import DynamicFeature
    is_admin = ut == '2'
    url_name = 'schooladmin:dynamic_feature' if is_admin else 'staff:dynamic_feature'
    items = []
    # Keys with their own dedicated nav block + views (not the generic
    # placeholder page) are excluded here so they don't show up twice.
    # Admin has dedicated management screens for all three modules. Staff has
    # a dedicated academic workspace, while Library/Accounting still use the
    # permission-aware generic module landing page until delegated staff
    # screens are configured.
    DEDICATED_UI_KEYS = (
        {'library', 'accounting', 'academic_management'}
        if is_admin else {'academic_management'}
    )
    features = DynamicFeature.objects.filter(
        is_active=True, org_grants__org=org, org_grants__enabled=True
    ).exclude(key__in=DEDICATED_UI_KEYS).prefetch_related('permissions').distinct()
    for feature in features:
        if not is_admin:
            flags = [p.flag for p in feature.permissions.all()]
            if flags and not any(has_perm(user, f) for f in flags):
                continue
        try:
            url = reverse(url_name, kwargs={'feature_key': feature.key})
        except Exception:
            continue
        items.append({'key': feature.key, 'label': feature.label, 'icon': feature.icon or 'fa-puzzle-piece', 'url': url})
    return items


def _notification_bell(user, org, refresh_task_reminders=False):
    """Latest tenant-safe notifications for admin, staff, teacher or student."""
    if getattr(user, 'user_type', '') not in ('2', '3') or org is None:
        return [], 0
    from handle.notifications import ensure_task_reminders, notifications_for_user

    if (
        refresh_task_reminders
        and getattr(user, 'user_type', '') == '3'
        and has_feature(org, 'tasks')
    ):
        ensure_task_reminders(user, org)
    qs = notifications_for_user(user, org).order_by('-created_at')
    return list(qs[:8]), qs.filter(is_read=False).count()


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
    breadcrumbs = build_breadcrumbs(request)

    # The "intelligent" back button: link to the parent crumb (second-to-last)
    # when it has a URL — this is the correct parent page for wherever the
    # user currently is, derived from the same map that drives the breadcrumb
    # trail. Pages with no known parent (or only a Dashboard root) fall back
    # to browser history in the template instead.
    back_url = None
    if len(breadcrumbs) > 1 and breadcrumbs[-2].get('url'):
        back_url = breadcrumbs[-2]['url']

    from django.conf import settings as _settings

    view_name = (
        request.resolver_match.view_name
        if getattr(request, 'resolver_match', None) else ''
    )
    dash_notifications, dash_unread_notifications = _notification_bell(
        request.user,
        org,
        refresh_task_reminders=view_name in {
            'staff:dashboard', 'staff:my_tasks', 'handle:notifications',
        },
    )
    from django.contrib.messages import get_messages
    from django.urls import reverse

    if request.user.user_type == '2':
        dashboard_home_url = reverse('schooladmin:dashboard')
    elif request.user.user_type == '3':
        dashboard_home_url = reverse('staff:dashboard')
    else:
        dashboard_home_url = '/'

    dynamic_features = _dynamic_features_for_sidebar(request.user, org)
    portal_navigation = []
    portal_role = ''
    portal_role_label = ''
    if request.user.user_type == '3':
        from school.navigation import build_portal_navigation

        portal_navigation, portal_role, portal_role_label = build_portal_navigation(
            request.user,
            org,
            dynamic_items=dynamic_features,
        )

    return {
        # This processor runs after Django's default messages processor and
        # intentionally replaces its template value with a one-shot wrapper.
        'messages': _OneShotMessages(get_messages(request)),
        'org': org,
        'features': features,
        'terms': get_terms(org),
        'staff_perms': staff_perms,
        'breadcrumbs': breadcrumbs,
        'back_url': back_url,
        'dynamic_features': dynamic_features,
        'portal_navigation': portal_navigation,
        'portal_role': portal_role,
        'portal_role_label': portal_role_label,
        'dash_notifications': dash_notifications,
        'dash_unread_notifications': dash_unread_notifications,
        'dashboard_home_url': dashboard_home_url,
        'play_store_url': getattr(_settings, 'PLAY_STORE_URL', ''),
        'app_store_url': getattr(_settings, 'APP_STORE_URL', ''),
        'web_dashboard_url': getattr(_settings, 'WEB_DASHBOARD_URL', ''),
        # Keep backward compat: old templates use `org.feature_payroll` directly
        # (org is already injected above; no extra work needed)
    }
