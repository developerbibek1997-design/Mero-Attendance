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
    'hrms/resignations':    'hrms',
    'hrms/documents':       'hrms',
    'branches/':            'branches',
    'study-gap/':           'study_gap',
    'tasks/':               'tasks',
    'export/payslips':      'bulk_export',
    'export/stock':         'stock',
    'export/finance':       'finance',
    'export/leave':         'leave',
    'payroll/':             'payroll',
    'generate-payslip':     'payroll',
    'salaryReport':         'payroll',
    'salaryReportAll':      'payroll',
    'master-leave-report':  'leave',
    'log-leave':            'leave',
    'manage-leave-types':   'leave',
    'leaveReportView':      'leave',
}

# Staff-portal URL prefixes → feature keys
# These match the actual staff/ URL patterns defined in staff/urls.py
_STAFF_FEATURE_URL_MAP = {
    'staff/my-payslips':      'payroll',
    'staff/my-bills':         'billing',
    'staff/my-results':       'results',
    'staff/apply-leave':      'leave',
    'staff/my-complaint':     'complaints',
    'staff/tasks':            'tasks',
    'staff/teaching-log':     'study_gap',
    'staff/my-resignation':   'hrms',
    'staff/location-checkin': 'gps',
    'staff/wifi-checkin':     'wifi',
}


class SecurityEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
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
                messages.error(request, "Access Denied: Organization Admin area only.")
                return redirect('/')

            if path.startswith('staff/') and user_type != '3':
                messages.error(request, "Access Denied: Staff portal only.")
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


_FEATURE_FIELD_MAP = {
    'finance':      'feature_finance',
    'billing':      'feature_billing',
    'stock':        'feature_stock',
    'tasks':        'feature_tasks',
    'results':      'feature_results',
    'hrms':         'feature_hrms',
    'payroll':      'feature_payroll',
    'complaints':   'feature_complaints',
    'events':       'feature_events',
    'branches':     'feature_branches',
    'leave':        'feature_leave',
    'study_gap':    'feature_study_gap',
    'bulk_export':  'feature_bulk_export',
    'courses':      'feature_courses',
    'student_mgmt': 'feature_student_mgmt',
    'gps':          'location_based',
    'wifi':         'mutifeature_enable',
}


def _org_has_feature(org, key):
    field = _FEATURE_FIELD_MAP.get(key)
    if not field:
        return True   # unknown feature → allow (fail open for unregistered keys)
    return bool(getattr(org, field, False))
