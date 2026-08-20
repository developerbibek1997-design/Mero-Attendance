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
    'qr_attendance': 'enable_qr_attendance',
    'timesheet':     'feature_timesheet',
    'id_cards':      'feature_id_cards',
    'field_visits':  'feature_field_visits',
    'clients':       'feature_clients',
    'face_attendance': 'feature_face_attendance',
    'notices':       'feature_notices',
    # Attendance sub-types (stored as dedicated org fields)
    'biometric':     'rfid_based',
    'qr':            'qr_based',
    'gps':           'location_based',
    'manual':        'manual_attendance',
    'nepali_cal':    'nepali_date',
    'wifi':          'mutifeature_enable',
}

# Reverse lookup: Organization field name -> short feature key
FIELD_TO_KEY_MAP = {v: k for k, v in FEATURE_MAP.items()}

# Human-readable labels for each feature key, used on superadmin's allowlist grids
FEATURE_KEY_LABELS = {
    'finance': 'Finance — Income & Expense', 'billing': 'Billing & Invoices',
    'stock': 'Stock / Inventory', 'tasks': 'Task Management',
    'results': 'Results & Exams', 'hrms': 'HR Module',
    'payroll': 'Payroll & Payslips', 'complaints': 'Complaints & Requests',
    'events': 'Events', 'branches': 'Branch Management',
    'leave': 'Leave Management', 'study_gap': 'Study Gap / Teaching Log',
    'bulk_export': 'Bulk Data Export', 'notifications': 'Notifications / SMS',
    'courses': 'Course Management', 'student_mgmt': 'Student Management',
    'member_mgmt': 'Member / Staff Management', 'qr_attendance': 'Dynamic QR Attendance',
    'timesheet': 'Timesheet Management', 'id_cards': 'ID Cards & Certificates',
    'field_visits': 'Field Visit / Location Sharing', 'clients': 'Client Follow-Up (CRM)',
    'face_attendance': 'Face Attendance', 'notices': 'Notice Board / Announcements',
    'biometric': 'Biometric / RFID Attendance', 'qr': 'QR Code Attendance',
    'gps': 'GPS Location Attendance', 'manual': 'Manual Attendance',
    'nepali_cal': 'Nepali Calendar (BS)', 'wifi': 'WiFi / Multi-Feature Attendance',
}

# Features that are always available regardless of flags (core)
ALWAYS_ON = {'attendance', 'member_mgmt'}

# ---------------------------------------------------------------------------
# Pricing / plan tiers
# ---------------------------------------------------------------------------
# The app's core promise: all ATTENDANCE methods + PAYROLL + LEAVE are free for
# every organization. Every other module is a paid add-on and stays locked until
# the platform (superadmin) provides it on the org's allowlist.
FREE_FEATURES = {
    'payroll', 'leave', 'member_mgmt',
    'biometric', 'qr', 'gps', 'manual', 'wifi', 'nepali_cal', 'qr_attendance',
}

# Annual price (in Rs) for a paid feature.
STANDARD_FEATURE_PRICE = 3000


def is_free(feature_key: str) -> bool:
    return feature_key in FREE_FEATURES


def feature_price(feature_key: str):
    """Annual price in Rs for a feature key (0 for free features).

    Dynamic features may set their own `DynamicFeature.price`, overriding the
    flat STANDARD_FEATURE_PRICE — used e.g. for Library (Rs 5000/yr).
    """
    try:
        from management.models import FeaturePrice
        configured_price = FeaturePrice.objects.filter(
            feature_key=feature_key
        ).values_list("annual_price", flat=True).first()
        if configured_price is not None:
            return configured_price
    except Exception:
        pass
    if feature_key in FREE_FEATURES:
        return 0
    if feature_key not in FEATURE_MAP:
        try:
            from handle.models import DynamicFeature
            feature = DynamicFeature.objects.filter(key=feature_key).first()
            if feature and feature.price is not None:
                return feature.price
        except Exception:
            pass
    return STANDARD_FEATURE_PRICE


def is_feature_allowed(org, feature_key: str) -> bool:
    """
    Check if `feature_key` is available to the org.
    Free features are always available. Paid features require the superadmin-granted
    allowlist (org.allowed_features).
    """
    if feature_key in FREE_FEATURES:
        return True
    if org is None:
        return True
    allowed = getattr(org, 'allowed_features', None)
    return allowed is None or feature_key in allowed


def has_feature(org, feature_key: str) -> bool:
    """Check if `feature_key` is enabled for `org`. Always returns True for core features."""
    if feature_key in ALWAYS_ON:
        return True
    if org is None:
        return False
    field = FEATURE_MAP.get(feature_key)
    if field is None:
        # Not a legacy feature key — fall through to the superadmin-defined
        # dynamic feature registry (school/models DynamicFeature/OrganizationFeatureGrant).
        return _dynamic_has_feature(org, feature_key)
    if not is_feature_allowed(org, feature_key):
        return False
    return bool(getattr(org, field, False))


# ---------------------------------------------------------------------------
# Dynamic (database-driven) features — additive layer on top of FEATURE_MAP.
# Adding a brand new feature never needs a migration: a superadmin creates a
# DynamicFeature row and grants it per-org via OrganizationFeatureGrant.
# ---------------------------------------------------------------------------

_DYN_FEATURE_CACHE_TTL = 60
_DYN_PERM_CACHE_TTL = 60


def _dyn_feature_cache_key(org_id):
    return f"dynfeat:org:{org_id}"


def _dyn_perm_cache_key(member_id):
    return f"dynperm:member:{member_id}"


def _get_org_dynamic_feature_map(org):
    """Return {feature_key: enabled_bool} for all active dynamic features of this org, cached."""
    cache_key = _dyn_feature_cache_key(org.id)
    grants = cache.get(cache_key)
    if grants is None:
        from handle.models import OrganizationFeatureGrant
        grants = {
            key: enabled
            for key, enabled in OrganizationFeatureGrant.objects.filter(
                org=org, feature__is_active=True
            ).values_list('feature__key', 'enabled')
        }
        cache.set(cache_key, grants, _DYN_FEATURE_CACHE_TTL)
    return grants


def _dynamic_has_feature(org, feature_key: str) -> bool:
    if org is None:
        return False
    grants = _get_org_dynamic_feature_map(org)
    if not grants.get(feature_key, False):
        return False
    # Honor declared dependencies (other legacy or dynamic keys this feature requires).
    from handle.models import DynamicFeature
    try:
        requires = DynamicFeature.objects.filter(key=feature_key, is_active=True).values_list('requires', flat=True).first()
    except Exception:
        requires = None
    if requires:
        return any(has_feature(org, req_key) for req_key in requires)
    return True


def invalidate_org_feature_cache(org_id):
    """Call after saving OrganizationFeatureGrant rows so changes are visible immediately."""
    cache.delete(_dyn_feature_cache_key(org_id))


def invalidate_member_perm_cache(member_id):
    """Call after saving StaffPermissionGrant rows so changes are visible immediately."""
    cache.delete(_dyn_perm_cache_key(member_id))


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
            'can_view_complaints', 'can_scan_qr_attendance',
            'can_view_timesheets', 'can_submit_timesheets',
            'can_send_location',
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
    if perm_key not in _LEGACY_STAFF_PERM_FLAGS:
        return _dynamic_has_perm(user, perm_key)
    perms = get_staff_permissions(user)
    return bool(getattr(perms, perm_key, False))


def _legacy_staff_perm_flags():
    from handle.models import StaffPermission
    return {f.name for f in StaffPermission._meta.get_fields() if getattr(f, 'name', '').startswith('can_')}


class _LazyFlagSet:
    """Resolves the legacy StaffPermission boolean field names on first use (avoids app-loading-order issues)."""
    _cached = None

    def __contains__(self, item):
        if _LazyFlagSet._cached is None:
            _LazyFlagSet._cached = _legacy_staff_perm_flags()
        return item in _LazyFlagSet._cached


_LEGACY_STAFF_PERM_FLAGS = _LazyFlagSet()


def _dynamic_has_perm(user, perm_key: str) -> bool:
    ut = getattr(user, 'user_type', '')
    if ut != '3':
        return False
    try:
        member = user.staff.member
    except Exception:
        return False
    cache_key = _dyn_perm_cache_key(member.id)
    grants = cache.get(cache_key)
    if grants is None:
        from handle.models import StaffPermissionGrant
        grants = {
            flag: granted
            for flag, granted in StaffPermissionGrant.objects.filter(
                member=member, permission__feature__is_active=True
            ).values_list('permission__flag', 'granted')
        }
        cache.set(cache_key, grants, _DYN_PERM_CACHE_TTL)
    if not grants.get(perm_key, False):
        return False
    # A permission only counts if its parent feature is still enabled for the org —
    # mirrors is_perm_visible()'s "requires" semantics for the legacy registry.
    from handle.models import DynamicPermission
    feature_key = DynamicPermission.objects.filter(flag=perm_key).values_list('feature__key', flat=True).first()
    return has_feature(member.org, feature_key) if feature_key else False


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
