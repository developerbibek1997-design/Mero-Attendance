"""
Canonical permission registry — single source of truth for the categorized,
icon-labelled view of both organization-level features (school.features.FEATURE_MAP)
and staff-level permissions (handle.models.StaffPermission).

This module does NOT define new storage — every entry references an existing
Organization field (via FEATURE_MAP) or an existing StaffPermission boolean field.
It exists purely to drive the unified "Roles & Permissions" UI (and, in a later
phase, the superadmin feature-grid UI and dynamic sidebar) from one categorized
data structure instead of scattered per-page hardcoding.

Usage:
    from school.permissions import PERMISSION_REGISTRY, PRESET_DEFINITIONS, iter_staff_perms
"""

from school.features import FEATURE_MAP, ALWAYS_ON


PERMISSION_REGISTRY = [
    {
        'slug': 'attendance', 'label': 'Attendance', 'icon': 'fa-fingerprint',
        'org_features': [
            {'key': 'qr_attendance', 'label': 'Dynamic QR Attendance', 'icon': 'fa-qrcode'},
            {'key': 'biometric', 'label': 'Biometric / RFID Attendance', 'icon': 'fa-fingerprint'},
            {'key': 'qr', 'label': 'QR Code Attendance', 'icon': 'fa-qrcode'},
            {'key': 'gps', 'label': 'GPS Location Attendance', 'icon': 'fa-location-dot'},
            {'key': 'manual', 'label': 'Manual Attendance', 'icon': 'fa-pen'},
            {'key': 'nepali_cal', 'label': 'Nepali Calendar (BS)', 'icon': 'fa-calendar'},
            {'key': 'wifi', 'label': 'WiFi Attendance', 'icon': 'fa-wifi'},
            {'key': 'field_visits', 'label': 'Field Visits', 'icon': 'fa-map-location-dot'},
        ],
        'staff_perms': [
            {'flag': 'can_view_attendance', 'label': 'View Attendance', 'icon': 'fa-eye', 'requires': []},
            {'flag': 'can_add_attendance', 'label': 'Add Attendance', 'icon': 'fa-plus', 'requires': []},
            {'flag': 'can_edit_attendance', 'label': 'Edit Attendance', 'icon': 'fa-pen', 'requires': []},
            {'flag': 'can_export_attendance', 'label': 'Export Attendance', 'icon': 'fa-download', 'requires': []},
            {'flag': 'can_scan_qr_attendance', 'label': 'Scan QR Attendance', 'icon': 'fa-qrcode', 'requires': ['qr_attendance', 'qr']},
            {'flag': 'can_send_location', 'label': 'Send My Location', 'icon': 'fa-location-arrow', 'requires': ['field_visits']},
            {'flag': 'can_view_field_visits', 'label': 'View Field Visits', 'icon': 'fa-map', 'requires': ['field_visits']},
        ],
    },
    {
        'slug': 'hr', 'label': 'HR', 'icon': 'fa-id-card',
        'org_features': [
            {'key': 'hrms', 'label': 'HR Module', 'icon': 'fa-id-card'},
            {'key': 'payroll', 'label': 'Payroll & Payslips', 'icon': 'fa-money-bill'},
            {'key': 'leave', 'label': 'Leave Management', 'icon': 'fa-calendar-xmark'},
            {'key': 'timesheet', 'label': 'Timesheet Management', 'icon': 'fa-clock'},
            {'key': 'id_cards', 'label': 'ID Card Generation', 'icon': 'fa-id-badge'},
        ],
        'staff_perms': [
            {'flag': 'can_view_payroll', 'label': 'View Payroll', 'icon': 'fa-eye', 'requires': ['payroll']},
            {'flag': 'can_generate_payroll', 'label': 'Generate Payroll', 'icon': 'fa-file-invoice-dollar', 'requires': ['payroll']},
            {'flag': 'can_view_own_payslip', 'label': 'View Own Payslip', 'icon': 'fa-file-invoice', 'requires': ['payroll']},
            {'flag': 'can_manage_payroll_cfg', 'label': 'Manage Payroll Settings', 'icon': 'fa-sliders', 'requires': ['payroll']},
            {'flag': 'can_view_leave', 'label': 'View Leave', 'icon': 'fa-eye', 'requires': ['leave']},
            {'flag': 'can_request_leave', 'label': 'Apply for Leave', 'icon': 'fa-calendar-plus', 'requires': ['leave']},
            {'flag': 'can_approve_leave', 'label': 'Approve / Reject Leave', 'icon': 'fa-check', 'requires': ['leave']},
            {'flag': 'can_view_leave_report', 'label': 'View Leave Report', 'icon': 'fa-chart-bar', 'requires': ['leave']},
            {'flag': 'can_view_hrms', 'label': 'View HR Module', 'icon': 'fa-eye', 'requires': ['hrms']},
            {'flag': 'can_manage_hrms', 'label': 'Manage HR Module', 'icon': 'fa-sliders', 'requires': ['hrms']},
            {'flag': 'can_view_timesheets', 'label': 'View Timesheets', 'icon': 'fa-eye', 'requires': ['timesheet']},
            {'flag': 'can_submit_timesheets', 'label': 'Submit Timesheets', 'icon': 'fa-clock', 'requires': ['timesheet']},
        ],
    },
    {
        'slug': 'school', 'label': 'School', 'icon': 'fa-school',
        'org_features': [
            {'key': 'member_mgmt', 'label': 'Member / Staff Management', 'icon': 'fa-users', 'locked': True},
            {'key': 'student_mgmt', 'label': 'Student Management', 'icon': 'fa-user-graduate'},
            {'key': 'courses', 'label': 'Course Management', 'icon': 'fa-book'},
            {'key': 'results', 'label': 'Results & Exams', 'icon': 'fa-graduation-cap'},
            {'key': 'events', 'label': 'Events', 'icon': 'fa-calendar-days'},
            {'key': 'complaints', 'label': 'Complaints & Requests', 'icon': 'fa-triangle-exclamation'},
            {'key': 'notices', 'label': 'Notice Board / Announcements', 'icon': 'fa-bullhorn'},
            {'key': 'branches', 'label': 'Branch Management', 'icon': 'fa-code-branch'},
            {'key': 'clients', 'label': 'Client Follow-Up (CRM)', 'icon': 'fa-building'},
        ],
        'staff_perms': [
            {'flag': 'can_view_members', 'label': 'View Members', 'icon': 'fa-eye', 'requires': []},
            {'flag': 'can_add_members', 'label': 'Add Members', 'icon': 'fa-plus', 'requires': []},
            {'flag': 'can_edit_members', 'label': 'Edit Members', 'icon': 'fa-pen', 'requires': []},
            {'flag': 'can_delete_members', 'label': 'Delete Members', 'icon': 'fa-trash', 'requires': []},
            {'flag': 'can_view_courses', 'label': 'View Courses', 'icon': 'fa-eye', 'requires': ['courses']},
            {'flag': 'can_manage_courses', 'label': 'Manage Courses', 'icon': 'fa-sliders', 'requires': ['courses']},
            {'flag': 'can_publish_results', 'label': 'Publish Results', 'icon': 'fa-graduation-cap', 'requires': ['results']},
            {'flag': 'can_view_result_report', 'label': 'View Result Report', 'icon': 'fa-chart-bar', 'requires': ['results']},
            {'flag': 'can_view_events', 'label': 'View Events', 'icon': 'fa-eye', 'requires': ['events']},
            {'flag': 'can_manage_events', 'label': 'Manage Events', 'icon': 'fa-sliders', 'requires': ['events']},
            {'flag': 'can_view_complaints', 'label': 'View Complaints', 'icon': 'fa-eye', 'requires': ['complaints']},
            {'flag': 'can_manage_complaints', 'label': 'Manage Complaints', 'icon': 'fa-sliders', 'requires': ['complaints']},
            {'flag': 'can_view_notices', 'label': 'View Notices', 'icon': 'fa-eye', 'requires': ['notices']},
            {'flag': 'can_manage_notices', 'label': 'Manage Notices', 'icon': 'fa-sliders', 'requires': ['notices']},
            {'flag': 'can_view_branches', 'label': 'View Branches', 'icon': 'fa-eye', 'requires': ['branches']},
            {'flag': 'can_manage_branches', 'label': 'Manage Branches', 'icon': 'fa-sliders', 'requires': ['branches']},
            {'flag': 'can_view_clients', 'label': 'View Clients', 'icon': 'fa-eye', 'requires': ['clients']},
            {'flag': 'can_manage_clients', 'label': 'Manage Clients', 'icon': 'fa-sliders', 'requires': ['clients']},
        ],
    },
    {
        'slug': 'finance', 'label': 'Finance & Billing', 'icon': 'fa-money-bill-wave',
        'org_features': [
            {'key': 'billing', 'label': 'Billing & Invoices', 'icon': 'fa-file-invoice-dollar'},
            {'key': 'finance', 'label': 'Finance — Income & Expense', 'icon': 'fa-money-bill-wave'},
            {'key': 'stock', 'label': 'Stock / Inventory', 'icon': 'fa-boxes-stacked'},
        ],
        'staff_perms': [
            {'flag': 'can_view_billing', 'label': 'View Billing', 'icon': 'fa-eye', 'requires': ['billing']},
            {'flag': 'can_generate_bills', 'label': 'Generate Bills', 'icon': 'fa-file-invoice-dollar', 'requires': ['billing']},
            {'flag': 'can_record_payment', 'label': 'Record Payment', 'icon': 'fa-money-check', 'requires': ['billing']},
            {'flag': 'can_view_dues', 'label': 'View Dues', 'icon': 'fa-eye', 'requires': ['billing']},
            {'flag': 'can_export_billing', 'label': 'Export Billing', 'icon': 'fa-download', 'requires': ['billing']},
            {'flag': 'can_view_finance', 'label': 'View Finance', 'icon': 'fa-eye', 'requires': ['finance']},
            {'flag': 'can_manage_finance', 'label': 'Manage Finance', 'icon': 'fa-sliders', 'requires': ['finance']},
            {'flag': 'can_view_stock', 'label': 'View Stock', 'icon': 'fa-eye', 'requires': ['stock']},
            {'flag': 'can_add_stock', 'label': 'Add Stock', 'icon': 'fa-plus', 'requires': ['stock']},
            {'flag': 'can_edit_stock', 'label': 'Edit Stock', 'icon': 'fa-pen', 'requires': ['stock']},
            {'flag': 'can_delete_stock', 'label': 'Delete Stock', 'icon': 'fa-trash', 'requires': ['stock']},
            {'flag': 'can_stock_in_out', 'label': 'Stock In / Out', 'icon': 'fa-right-left', 'requires': ['stock']},
            {'flag': 'can_view_purchases', 'label': 'View Purchases & Suppliers', 'icon': 'fa-cart-arrow-down', 'requires': ['stock']},
            {'flag': 'can_manage_purchases', 'label': 'Create & Receive Purchases', 'icon': 'fa-truck-ramp-box', 'requires': ['stock']},
            {'flag': 'can_manage_purchase_returns', 'label': 'Manage Purchase Returns', 'icon': 'fa-rotate-left', 'requires': ['stock']},
            {'flag': 'can_view_sales', 'label': 'View Sales', 'icon': 'fa-cash-register', 'requires': ['stock']},
            {'flag': 'can_manage_sales', 'label': 'Create & Complete Sales', 'icon': 'fa-receipt', 'requires': ['stock']},
            {'flag': 'can_manage_sales_returns', 'label': 'Manage Sales Returns', 'icon': 'fa-arrow-rotate-left', 'requires': ['stock']},
        ],
    },
    {
        'slug': 'library', 'label': 'Library', 'icon': 'fa-book-open-reader',
        # Library is a dynamic paid feature. Its four permissions are attached
        # to this category by RolesPermissionsEditView when enabled for an org.
        'org_features': [],
        'staff_perms': [],
    },
    {
        'slug': 'tasks', 'label': 'Tasks', 'icon': 'fa-list-check',
        'org_features': [
            {'key': 'tasks', 'label': 'Task Management', 'icon': 'fa-list-check'},
            {'key': 'study_gap', 'label': 'Study Gap / Teaching Log', 'icon': 'fa-chalkboard'},
        ],
        'staff_perms': [
            {'flag': 'can_view_tasks', 'label': 'View Tasks', 'icon': 'fa-eye', 'requires': ['tasks']},
            {'flag': 'can_assign_tasks', 'label': 'Assign Tasks', 'icon': 'fa-share', 'requires': ['tasks']},
            {'flag': 'can_manage_tasks', 'label': 'Manage Tasks', 'icon': 'fa-sliders', 'requires': ['tasks']},
            {'flag': 'can_view_task_report', 'label': 'View Task Report', 'icon': 'fa-chart-bar', 'requires': ['tasks']},
        ],
    },
    {
        'slug': 'reports', 'label': 'Reports', 'icon': 'fa-chart-bar',
        'org_features': [
            {'key': 'bulk_export', 'label': 'Bulk Data Export', 'icon': 'fa-file-export'},
            {'key': 'notifications', 'label': 'Notifications / SMS', 'icon': 'fa-bell'},
        ],
        'staff_perms': [
            {'flag': 'can_view_reports', 'label': 'View Reports', 'icon': 'fa-eye', 'requires': []},
            {'flag': 'can_export_reports', 'label': 'Export Reports', 'icon': 'fa-download', 'requires': []},
            {'flag': 'can_bulk_export', 'label': 'Bulk Export', 'icon': 'fa-file-export', 'requires': ['bulk_export']},
        ],
    },
]


def is_perm_visible(org, perm):
    """A staff permission is only relevant if the org feature(s) it depends on
    are actually enabled. An empty `requires` list means the permission is core
    (e.g. viewing your own attendance/member records) and is always visible."""
    from school.features import has_feature
    requires = perm.get('requires')
    if not requires:
        return True
    return any(has_feature(org, key) for key in requires)


def get_registry():
    """Return the canonical categorized permission registry."""
    return PERMISSION_REGISTRY


def iter_org_features():
    """Flatten the registry into (category_slug, category_label, feature_entry) tuples."""
    for cat in PERMISSION_REGISTRY:
        for feat in cat['org_features']:
            yield cat['slug'], cat['label'], feat


def iter_staff_perms():
    """Flatten the registry into (category_slug, category_label, perm_entry) tuples."""
    for cat in PERMISSION_REGISTRY:
        for perm in cat['staff_perms']:
            yield cat['slug'], cat['label'], perm


def all_staff_perm_flags():
    """Return a flat list of every StaffPermission flag name in the registry."""
    return [perm['flag'] for _, _, perm in iter_staff_perms()]


# ---------------------------------------------------------------------------
# Role presets — map member.privilege (handle.models.PRIVILEGE_LEVEL_CHOICES)
# to a set of StaffPermission flags to bulk-check. Purely a UX convenience for
# the "Roles & Permissions" edit page; never consulted by access-control code.
# ---------------------------------------------------------------------------

_SELF_ONLY = {
    'can_view_attendance', 'can_view_leave', 'can_request_leave',
    'can_view_tasks', 'can_view_own_payslip', 'can_view_events',
    'can_view_complaints', 'can_scan_qr_attendance', 'can_view_notices',
    'can_view_timesheets', 'can_submit_timesheets', 'can_send_location',
}

_CLASS_LEVEL = _SELF_ONLY | {
    'can_view_members', 'can_view_courses', 'can_view_result_report',
    'can_add_attendance', 'can_edit_attendance', 'can_view_field_visits',
}

_BRANCH_LEVEL = _CLASS_LEVEL | {
    'can_view_branches', 'can_view_billing', 'can_view_dues', 'can_view_stock',
    'can_view_clients', 'can_export_attendance', 'can_view_reports',
    'can_view_purchases', 'can_view_sales',
}

_ORG_LEVEL = _BRANCH_LEVEL | {
    'can_view_finance', 'can_view_hrms', 'can_view_payroll', 'can_view_leave_report',
    'can_export_reports', 'can_bulk_export', 'can_export_billing',
    'can_manage_clients', 'can_view_task_report', 'can_manage_purchases',
    'can_manage_purchase_returns', 'can_manage_sales', 'can_manage_sales_returns',
}

_FULL_ADMIN = set(all_staff_perm_flags())

PRESET_DEFINITIONS = {
    1: _SELF_ONLY,     # Self Only — view own data
    2: _CLASS_LEVEL,   # Class Level — view class data
    3: _BRANCH_LEVEL,  # Branch Level — view branch data
    4: _ORG_LEVEL,      # Org Level — view finance & HR data
    5: _FULL_ADMIN,     # Full Admin — all access
}
