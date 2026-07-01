"""
Central feature flag and permission utilities.

Usage in views:
    from school.features import has_feature, has_perm, get_org_for_user

Usage in templates (via context processor):
    {{ features.payroll }}      → True/False
    {{ staff_perms.can_view_payroll }}  → True/False

Usage as decorator:
    from school.decorators import feature_required, perm_required
"""

from django.core.cache import cache


# ---------------------------------------------------------------------------
# Org resolution
# ---------------------------------------------------------------------------

def get_org_for_user(user):
    """Return the Organization for any authenticated user type."""
    if not user or not user.is_authenticated:
        return None
    ut = getattr(user, 'user_type', '')
    try:
        if ut == '2':
            return user.schooladmin.org
        if ut == '3':
            return user.staff.org
        if ut == '1':
            # superadmin has no fixed org; caller must provide org explicitly
            return None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Feature checks
# ---------------------------------------------------------------------------

# Maps short key → Organization field name
FEATURE_MAP = {
    'finance':       'feature_finance',
    'billing':       'feature_billing',
    'stock':         'feature_stock',
    'tasks':         'feature_tasks',
    'results':       'feature_results',
    'hrms':          'feature_hrms',
    'payroll':       'feature_payroll',
    'complaints':    'feature_complaints',
    'events':        'feature_events',
    'branches':      'feature_branches',
    'leave':         'feature_leave',
    'study_gap':     'feature_study_gap',
    'bulk_export':   'feature_bulk_export',
    'notifications': 'feature_notifications',
    'courses':       'feature_courses',
    'student_mgmt':  'feature_student_mgmt',
    'member_mgmt':   'feature_member_mgmt',
    # Attendance sub-types (stored as dedicated org fields)
    'biometric':     'rfid_based',
    'qr':            'qr_based',
    'gps':           'location_based',
    'manual':        'manual_attendance',
    'nepali_cal':    'nepali_date',
}

# Features that are always available regardless of flags (core)
ALWAYS_ON = {'attendance', 'member_mgmt'}


def has_feature(org, feature_key: str) -> bool:
    """Check if `feature_key` is enabled for `org`. Always returns True for core features."""
    if feature_key in ALWAYS_ON:
        return True
    if org is None:
        return False
    field = FEATURE_MAP.get(feature_key)
    if field is None:
        return False
    return bool(getattr(org, field, False))


class OrgFeatures:
    """
    Dict-like wrapper around an Organization instance.
    Allows ``{{ features.payroll }}`` in templates.
    """
    def __init__(self, org):
        self._org = org

    def __getattr__(self, key):
        if key.startswith('_'):
            raise AttributeError(key)
        return has_feature(self._org, key)

    def __bool__(self):
        return self._org is not None

    # Allow {% if features.payroll %} to work naturally
    def get(self, key, default=False):
        return has_feature(self._org, key) if self._org else default


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------

class _NullPermissions:
    """Returned when no StaffPermission row exists. All perms False except safe defaults."""
    def __getattr__(self, name):
        # Safe defaults for basic staff visibility
        _true_by_default = {
            'can_view_attendance', 'can_view_leave', 'can_request_leave',
            'can_view_tasks', 'can_view_own_payslip', 'can_view_events',
            'can_view_complaints',
        }
        if name in _true_by_default:
            return True
        return False


_null_perms = _NullPermissions()


def get_staff_permissions(user):
    """
    Return StaffPermission for a staff user, or a safe null object.
    For schooladmin/superadmin returns a full-access sentinel.
    """
    ut = getattr(user, 'user_type', '')
    if ut in ('1', '2'):
        return _AdminPermissions()
    try:
        from handle.models import StaffPermission
        return user.staff.member.staff_permission
    except Exception:
        return _null_perms


class _AdminPermissions:
    """Schooladmin/superadmin always has all permissions."""
    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return True


def has_perm(user, perm_key: str) -> bool:
    """Check if user has a specific staff permission."""
    ut = getattr(user, 'user_type', '')
    if ut in ('1', '2'):
        return True
    perms = get_staff_permissions(user)
    return bool(getattr(perms, perm_key, False))


# ---------------------------------------------------------------------------
# Dependency map — disabling a parent hides children
# ---------------------------------------------------------------------------

FEATURE_DEPENDENCIES = {
    'payroll':    ['results'],          # payroll doesn't depend on results, but…
    'results':    ['courses'],          # results require courses
    'billing':    ['student_mgmt'],     # billing requires student mgmt
    'branches':   [],
}


def get_effective_features(org) -> dict:
    """
    Return a dict of {feature_key: bool} respecting dependency rules.
    If a parent is disabled, children are also treated as disabled.
    """
    result = {}
    for key in FEATURE_MAP:
        result[key] = has_feature(org, key)

    # Apply dependencies
    if not result.get('courses'):
        result['results'] = False
    if not result.get('student_mgmt'):
        result['billing'] = False

    return result


# ---------------------------------------------------------------------------
# Menu building
# ---------------------------------------------------------------------------

def get_menu_items(user, org):
    """
    Return ordered list of menu section dicts for the sidebar.
    Each item: {'label': str, 'url_name': str, 'icon': str, 'feature': str|None}
    """
    f = OrgFeatures(org)
    ut = getattr(user, 'user_type', '')
    is_admin = ut in ('1', '2')
    perms = get_staff_permissions(user)

    items = []

    # Core — always shown
    items.append({'section': 'Core', 'links': [
        {'label': 'Dashboard',   'icon': 'fa-gauge',      'url': 'dashboard',   'feature': None},
        {'label': 'Attendance',  'icon': 'fa-fingerprint','url': 'allRecord',   'feature': None},
        {'label': 'Members',     'icon': 'fa-users',      'url': 'getMember',   'feature': None},
    ]})

    if f.payroll and (is_admin or perms.can_view_payroll):
        items.append({'label': 'Payroll', 'icon': 'fa-money-bill', 'feature': 'payroll'})

    if f.leave and (is_admin or perms.can_view_leave):
        items.append({'label': 'Leave', 'icon': 'fa-calendar-xmark', 'feature': 'leave'})

    if f.hrms and (is_admin or perms.can_view_hrms):
        items.append({'label': 'HRMS', 'icon': 'fa-id-card', 'feature': 'hrms'})

    return items
