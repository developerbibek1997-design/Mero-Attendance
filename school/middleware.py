from django.shortcuts import redirect, render
from django.contrib.auth import logout
from django.contrib import messages


# Map URL prefixes (after schooladmin/) to feature keys.
# If the org doesn't have the feature, the URL is blocked with a 403 page.
_FEATURE_URL_MAP = {
    'finance/':             'finance',
    'stock/':               'stock',
    'billing/':             'billing',
    'events/':              'events',
    'results/':             'results',
    'courses/':             'courses',
    'complaints/':          'complaints',
    'notices/':             'notices',
    'hrms/resignations':    'hrms',
    'hrms/documents':       'hrms',
    'shifts/':              'hrms',
    'face/':                'face_attendance',
    'branches/':            'branches',
    'study-gap/':           'study_gap',
    'tasks/':               'tasks',
    'export/payslips':      'bulk_export',
    'export/stock':         'stock',
    'export/finance':       'finance',
    'export/leave':         'leave',
    'qr-attendance/':       'qr_attendance',
    'timesheets/':          'timesheet',
    'payroll/':             'payroll',
    'generate-payslip':     'payroll',
    'salaryReport':         'payroll',
    'salaryReportAll':      'payroll',
    'master-leave-report':  'leave',
    'log-leave':            'leave',
    'manage-leave-types':   'leave',
    'leaveReportView':      'leave',
    'id-card/':             'id_cards',
    'field-visits/':        'field_visits',
    'live-tracking/':       'field_visits',
    'clients/':             'clients',
}

# Staff-portal URL prefixes → feature keys
# These match the actual staff/ URL patterns defined in staff/urls.py
_STAFF_FEATURE_URL_MAP = {
    'staff/my-payslips':      'payroll',
    'staff/my-bills':         'billing',
    'staff/my-results':       'results',
    'staff/apply-leave':      'leave',
    'staff/my-complaint':     'complaints',
    'staff/notices':          'notices',
    'staff/tasks':            'tasks',
    'staff/teaching-log':     'academic_management',
    'staff/my-resignation':   'hrms',
    'staff/location-checkin': 'gps',
    'staff/wifi-checkin':     'wifi',
    'staff/qr-attendance':    'qr_attendance',
    'staff/timesheets':       'timesheet',
    'staff/send-location':    'field_visits',
    'staff/live-tracking':    'field_visits',
    'staff/clients':          'clients',

    # Delegated staff views (Phase 3)
    'staff/payroll-report':   'payroll',
    'staff/payroll-settings': 'payroll',
    'staff/generate-payslip': 'payroll',
    'staff/leave-approval':   'leave',
    'staff/leave-report':     'leave',
    'staff/hrms':             'hrms',
    'staff/courses':          'courses',
    'staff/results':          'results',
    'staff/stock':            'stock',
    'staff/branches':         'branches',
    'staff/events':           'events',
    'staff/field-visits':     'field_visits',
    'staff/billing':          'billing',
    'staff/finance':          'finance',
    'staff/tasks/create':     'tasks',
    'staff/tasks/dashboard':  'tasks',
    'staff/tasks/list':       'tasks',
    'staff/tasks/report':     'tasks',
    'staff/complaints/manage': 'complaints',
}

# Carefully delegated school-admin workflows. Staff/teacher/student accounts
# may enter only when an administrator explicitly grants one of the listed
# permissions; each target view still enforces its exact read/write permission.
_DELEGATED_SCHOOLADMIN_PATHS = {
    'schooladmin/library/': (
        'can_view_library', 'can_manage_library', 'can_issue_books', 'can_return_books',
    ),
    'schooladmin/export/library/': ('can_view_library',),
    'schooladmin/suppliers/': ('can_view_purchases', 'can_manage_purchases'),
    'schooladmin/purchases/': (
        'can_view_purchases', 'can_manage_purchases', 'can_manage_purchase_returns',
    ),
    'schooladmin/purchase-returns/': (
        'can_view_purchases', 'can_manage_purchase_returns',
    ),
    'schooladmin/sales/': (
        'can_view_sales', 'can_manage_sales', 'can_manage_sales_returns',
    ),
    'schooladmin/sales-returns/': ('can_view_sales', 'can_manage_sales_returns'),
}


class SecurityEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info.lstrip('/')

        # An anonymous session hitting a role-gated prefix must be sent to
        # login, not let through to the view — every one of these views
        # assumes an authenticated user with a `.schooladmin`/`.staff`
        # relation and crashes with an AttributeError on AnonymousUser
        # otherwise (this used to only apply once request.user.is_authenticated
        # was already True, silently skipping this check for logged-out visitors).
        # DRF authenticates Bearer tokens inside the view, after Django
        # middleware has run. Do not redirect anonymous-looking requests for
        # staff JSON endpoints here; their explicit IsAuthenticated +
        # JWTAuthentication policies must be allowed to return proper 401/403
        # JSON responses to mobile clients.
        jwt_api_path = path.startswith(('staff/api/', 'staff/api-'))
        if (
            not request.user.is_authenticated
            and not jwt_api_path
            and path.startswith(('superadmin/', 'schooladmin/', 'staff/', 'agent/'))
        ):
            return redirect('/')

        if request.user.is_authenticated:

            # --- A. SESSION DEVICE FINGERPRINT ---
            current_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
            session_agent = request.session.get('secure_device_signature')
            if not session_agent:
                request.session['secure_device_signature'] = current_agent
            elif session_agent != current_agent:
                logout(request)
                messages.error(request, "Security Alert: Session invalidated due to suspicious activity.")
                return redirect('/')

            # --- B. ROLE-BASED URL PROTECTION ---
            path = request.path_info.lstrip('/')
            user_type = str(getattr(request.user, 'user_type', ''))

            if path.startswith('superadmin/') and user_type != '1':
                messages.error(request, "Access Denied: Super Admin area only.")
                return redirect('/')

            if path.startswith('schooladmin/') and user_type not in ('1', '2'):
                delegated_permissions = next(
                    (
                        permissions
                        for prefix, permissions in _DELEGATED_SCHOOLADMIN_PATHS.items()
                        if path.startswith(prefix)
                    ),
                    None,
                )
                delegated_allowed = False
                if user_type == '3' and delegated_permissions:
                    from school.features import has_perm
                    delegated_allowed = any(
                        has_perm(request.user, permission)
                        for permission in delegated_permissions
                    )
                if not delegated_allowed:
                    messages.error(request, "Access Denied: Organization Admin area only.")
                    return redirect('/')

            if path.startswith('staff/') and user_type != '3':
                messages.error(request, "Access Denied: Staff portal only.")
                return redirect('/')

            if path.startswith('agent/') and user_type not in ('1', '4'):
                messages.error(request, "Access Denied: Agent portal only.")
                return redirect('/')

            # --- C. FEATURE-BASED URL PROTECTION ---
            # Only enforced for schooladmin (2) users; superadmin (1) bypasses.
            if user_type == '2':
                org = _get_org(request.user)
                if org:
                    # Check schooladmin/* feature-gated paths
                    if path.startswith('schooladmin/'):
                        sub = path[len('schooladmin/'):]
                        for prefix, feature_key in _FEATURE_URL_MAP.items():
                            if sub.startswith(prefix):
                                if not _org_has_feature(org, feature_key):
                                    return render(request, '403.html', {
                                        'reason': f"The '{feature_key}' module is not enabled for your organization.",
                                        'org': org,
                                    }, status=403)
                                break

            # Staff feature protection
            if user_type == '3':
                org = _get_org(request.user)
                if org:
                    for prefix, feature_key in _STAFF_FEATURE_URL_MAP.items():
                        if path.startswith(prefix):
                            if not _org_has_feature(org, feature_key):
                                return render(request, '403.html', {
                                    'reason': f"The '{feature_key}' module is not available.",
                                    'org': org,
                                }, status=403)
                            break

        response = self.get_response(request)
        return response


def _get_org(user):
    try:
        ut = str(getattr(user, 'user_type', ''))
        if ut == '2':
            return user.schooladmin.org
        if ut == '3':
            return user.staff.org
    except Exception:
        pass
    return None


def _org_has_feature(org, key):
    from school.features import has_feature, FEATURE_MAP
    if key not in FEATURE_MAP:
        return True   # unknown feature → allow (fail open for unregistered keys)
    return has_feature(org, key)
