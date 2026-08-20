"""Role-aware staff portal navigation.

This is the single policy used by the staff, teacher and student sidebars.
Organisation features decide which modules exist; staff permissions decide
which organisation-wide tools a staff member may use. Student self-service
links deliberately do not reuse staff-management permissions.
"""

from collections import OrderedDict

from django.urls import NoReverseMatch, reverse

from school.features import has_feature, has_perm


ROLE_LABELS = {
    'student': 'Student Portal',
    'teacher': 'Teacher Workspace',
    'driver': 'Driver Workspace',
    'staff': 'Staff Workspace',
}


def _portal_role(user, org, member):
    if member.member_type in ('student', 'trainee'):
        return 'student'
    if member.member_type == 'teacher':
        return 'teacher'
    if member.member_type == 'driver':
        return 'driver'
    if has_feature(org, 'academic_management'):
        from handle.models import SubjectTeacherAssignment

        if SubjectTeacherAssignment.objects.filter(
            org=org, teacher=user, status='active',
        ).exists():
            return 'teacher'
    return 'staff'


def build_portal_navigation(user, org, dynamic_items=None):
    """Return visible sidebar sections for one authenticated staff account."""
    profile = getattr(user, 'staff', None)
    member = getattr(profile, 'member', None)
    if org is None or member is None:
        return [], 'staff', ROLE_LABELS['staff']

    role = _portal_role(user, org, member)
    sections = OrderedDict()

    def add(
        section_key, section_label, section_icon,
        label, url_name=None, icon='fa-circle', *,
        feature=None, permission=None, url=None, match='', exact=False,
    ):
        if feature and not has_feature(org, feature):
            return
        if permission and not has_perm(user, permission):
            return
        if not url:
            try:
                url = reverse(url_name)
            except NoReverseMatch:
                return
        bucket = sections.setdefault(section_key, {
            'key': section_key,
            'label': section_label,
            'icon': section_icon,
            'links': [],
        })
        bucket['links'].append({
            'label': label,
            'url': url,
            'icon': icon,
            'match': match or url,
            'exact': exact,
            'feature': feature or '',
        })

    add(
        'overview', 'Overview', 'fa-grid-2',
        'Dashboard', 'staff:dashboard', 'fa-house', exact=True,
    )
    add(
        'overview', 'Overview', 'fa-grid-2', 'Notification Centre',
        'handle:notifications', 'fa-bell', match='/handle/notifications/',
    )

    if role == 'student':
        for label, url_name, icon in (
            ('My Class Routine', 'staff:student_routine', 'fa-calendar-week'),
            ('Homework', 'staff:student_homework', 'fa-book-open'),
            ('Assignments', 'staff:student_assignments', 'fa-file-pen'),
            ('Course Materials', 'staff:student_course_materials', 'fa-folder-open'),
            ('Teaching Logs', 'staff:student_teaching_logs', 'fa-chalkboard-user'),
            ('Subject Attendance', 'staff:student_subject_attendance', 'fa-user-check'),
        ):
            add(
                'learning', 'Learning', 'fa-graduation-cap',
                label, url_name, icon, feature='academic_management',
            )

        add(
            'performance', 'Performance & Fees', 'fa-chart-line',
            'My Results', 'staff:student_results', 'fa-award', feature='results',
        )
        add(
            'performance', 'Performance & Fees', 'fa-chart-line',
            'My Bills', 'staff:student_bills', 'fa-file-invoice-dollar',
            feature='billing',
        )
        add(
            'records', 'Attendance & Requests', 'fa-fingerprint',
            'My Attendance', 'staff:my_attendance', 'fa-calendar-check',
        )
        add(
            'records', 'Attendance & Requests', 'fa-fingerprint',
            'Absence Gaps', 'staff:student_gaps', 'fa-user-clock',
        )
        add(
            'records', 'Attendance & Requests', 'fa-fingerprint',
            'Scan QR Attendance', 'staff:qr_attendance', 'fa-qrcode',
            feature='qr_attendance',
        )
        add(
            'records', 'Attendance & Requests', 'fa-fingerprint',
            'Leave Requests', 'staff:apply_leave', 'fa-calendar-plus',
            feature='leave',
        )
        add(
            'records', 'Attendance & Requests', 'fa-fingerprint',
            'My Tasks', 'staff:my_tasks', 'fa-list-check', feature='tasks',
        )
        add(
            'records', 'Attendance & Requests', 'fa-fingerprint',
            'Complaints', 'staff:student_complaint', 'fa-circle-exclamation',
            feature='complaints',
        )
        add(
            'community', 'Community', 'fa-people-group',
            'Notices', 'staff:notices', 'fa-bullhorn', feature='notices',
        )

    else:
        if role == 'teacher':
            for label, url_name, icon, feature in (
                ('Subject Attendance', 'staff:subject_teaching_log', 'fa-user-check', 'academic_management'),
                ('My Class Routine', 'staff:teacher_routine', 'fa-calendar-week', 'academic_management'),
                ('Homework', 'staff:teacher_homework', 'fa-book-open', 'academic_management'),
                ('Assignments', 'staff:teacher_assignments', 'fa-file-pen', 'academic_management'),
                ('Exams & Marks', 'staff:teacher_exams', 'fa-clipboard-check', 'results'),
                ('Attendance Report', 'staff:teacher_subject_attendance_report', 'fa-chart-column', 'academic_management'),
            ):
                add(
                    'teaching', 'Teaching Workspace', 'fa-chalkboard-user',
                    label, url_name, icon, feature=feature,
                )

        add(
            'my_work', 'My Work', 'fa-briefcase',
            'My Attendance', 'staff:my_attendance', 'fa-calendar-check',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'Scan QR Attendance', 'staff:qr_attendance', 'fa-qrcode',
            feature='qr_attendance', permission='can_scan_qr_attendance',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'My Payslips', 'staff:my_payslips', 'fa-money-check-dollar',
            feature='payroll', permission='can_view_own_payslip',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'Apply Leave', 'staff:apply_leave', 'fa-calendar-plus',
            feature='leave', permission='can_view_leave',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'My Tasks', 'staff:my_tasks', 'fa-list-check',
            feature='tasks', permission='can_view_tasks',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'My Timesheets', 'staff:timesheet_list', 'fa-clock',
            feature='timesheet', permission='can_view_timesheets',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'File Complaint', 'staff:student_complaint', 'fa-circle-exclamation',
            feature='complaints', permission='can_view_complaints',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'Notices', 'staff:notices', 'fa-bullhorn',
            feature='notices', permission='can_view_notices',
        )
        add(
            'my_work', 'My Work', 'fa-briefcase',
            'My Resignation', 'staff:my_resignation', 'fa-person-walking-arrow-right',
            feature='hrms',
        )

        # Academic administration.
        add(
            'academics', 'Academic Management', 'fa-school',
            'Courses', 'staff:course_list', 'fa-book',
            feature='courses', permission='can_view_courses',
        )
        add(
            'academics', 'Academic Management', 'fa-school',
            'Manage Courses', 'staff:manage_courses', 'fa-book-medical',
            feature='courses', permission='can_manage_courses',
        )
        add(
            'academics', 'Academic Management', 'fa-school',
            'Result Entry', 'staff:result_entry', 'fa-pen-to-square',
            feature='results', permission='can_publish_results',
        )
        add(
            'academics', 'Academic Management', 'fa-school',
            'Result Reports', 'staff:result_report', 'fa-chart-bar',
            feature='results', permission='can_view_result_report',
        )
        add(
            'academics', 'Academic Management', 'fa-school',
            'Class Reports', 'staff:report', 'fa-users-viewfinder',
            permission='can_view_reports',
        )

        # People and HR.
        add(
            'people', 'People & HR', 'fa-users',
            'View Members', 'handle:memberReport', 'fa-users',
            permission='can_view_members',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'Add Member', 'handle:addMember', 'fa-user-plus',
            permission='can_add_members',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'HR Module', 'staff:hrms', 'fa-id-card',
            feature='hrms', permission='can_view_hrms',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'Leave Approval', 'staff:leave_approval', 'fa-user-check',
            feature='leave', permission='can_approve_leave',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'Leave Report', 'staff:leave_report', 'fa-chart-simple',
            feature='leave', permission='can_view_leave_report',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'Payroll Report', 'staff:payroll_report', 'fa-file-invoice-dollar',
            feature='payroll', permission='can_view_payroll',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'Generate Payslip', 'staff:generate_payslip', 'fa-file-circle-plus',
            feature='payroll', permission='can_generate_payroll',
        )
        add(
            'people', 'People & HR', 'fa-users',
            'Payroll Settings', 'staff:payroll_settings', 'fa-sliders',
            feature='payroll', permission='can_manage_payroll_cfg',
        )

        # Operational modules.
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Task Dashboard', 'staff:task_dashboard', 'fa-list-check',
            feature='tasks', permission='can_manage_tasks',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Assign Task', 'staff:create_task', 'fa-square-plus',
            feature='tasks', permission='can_assign_tasks',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Task Report', 'staff:task_report', 'fa-chart-gantt',
            feature='tasks', permission='can_view_task_report',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Stock Dashboard', 'staff:stock_dashboard', 'fa-boxes-stacked',
            feature='stock', permission='can_view_stock',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Stock Items', 'staff:stock_items', 'fa-list',
            feature='stock', permission='can_view_stock',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Stock In', 'staff:stock_in', 'fa-arrow-down',
            feature='stock', permission='can_stock_in_out',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Stock Out', 'staff:stock_out', 'fa-arrow-up',
            feature='stock', permission='can_stock_in_out',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Branches', 'staff:branch_list', 'fa-code-branch',
            feature='branches', permission='can_view_branches',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Manage Branches', 'staff:manage_branches', 'fa-code-branch',
            feature='branches', permission='can_manage_branches',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Events', 'staff:event_list', 'fa-calendar-days',
            feature='events', permission='can_view_events',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Manage Events', 'staff:manage_events', 'fa-calendar-plus',
            feature='events', permission='can_manage_events',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Field Visits', 'staff:field_visit_list', 'fa-map-location-dot',
            feature='field_visits', permission='can_view_field_visits',
        )
        add(
            'operations', 'Operations', 'fa-diagram-project',
            'Send Location', 'staff:send_location', 'fa-location-arrow',
            feature='field_visits', permission='can_send_location',
        )
        if getattr(member, 'live_tracking_enabled', False):
            add(
                'operations', 'Operations', 'fa-diagram-project',
                'Live Tracking', 'staff:live_tracking', 'fa-route',
                feature='field_visits',
            )

        # Finance, billing and CRM.
        add(
            'business', 'Finance & Business', 'fa-wallet',
            'Create Bill', 'staff:create_bill', 'fa-file-circle-plus',
            feature='billing', permission='can_generate_bills',
        )
        add(
            'business', 'Finance & Business', 'fa-wallet',
            'Billing Dues', 'staff:billing_dues', 'fa-file-invoice-dollar',
            feature='billing', permission='can_view_dues',
        )
        add(
            'business', 'Finance & Business', 'fa-wallet',
            'Finance Dashboard', 'staff:finance_dashboard', 'fa-chart-pie',
            feature='finance', permission='can_view_finance',
        )
        add(
            'business', 'Finance & Business', 'fa-wallet',
            'Clients', 'staff:client_list', 'fa-building',
            feature='clients', permission='can_view_clients',
        )
        add(
            'business', 'Finance & Business', 'fa-wallet',
            'Manage Complaints', 'staff:complaint_list', 'fa-headset',
            feature='complaints', permission='can_manage_complaints',
        )
        add(
            'business', 'Finance & Business', 'fa-wallet',
            'Export Centre', 'staff:export_hub', 'fa-file-export',
            feature='bulk_export', permission='can_bulk_export',
        )

    # Explicitly delegated modules are available to any portal role, including
    # a student or teacher, only when an administrator grants the exact
    # operational permission. Nothing is exposed merely because the org owns
    # the feature.
    library_permissions = (
        'can_view_library', 'can_manage_library',
        'can_issue_books', 'can_return_books',
    )
    if any(has_perm(user, flag) for flag in library_permissions):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Library Dashboard', 'schooladmin:library_dashboard', 'fa-book-open-reader',
            feature='library',
        )
    if has_perm(user, 'can_manage_library'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Manage Library Catalog', 'schooladmin:library_books', 'fa-book',
            feature='library',
        )
    if has_perm(user, 'can_issue_books'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Issue Library Book', 'schooladmin:library_issue', 'fa-right-from-bracket',
            feature='library',
        )
    if has_perm(user, 'can_return_books'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Library Returns', 'schooladmin:library_issues', 'fa-right-to-bracket',
            feature='library',
        )

    if has_perm(user, 'can_view_purchases'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Purchases & Suppliers', 'schooladmin:purchase_list', 'fa-cart-arrow-down',
            feature='stock',
        )
    if has_perm(user, 'can_manage_purchases'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'New Purchase', 'schooladmin:add_purchase', 'fa-truck-ramp-box',
            feature='stock',
        )
    if has_perm(user, 'can_manage_purchase_returns'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Purchase Returns', 'schooladmin:purchase_return_list', 'fa-rotate-left',
            feature='stock',
        )
    if has_perm(user, 'can_view_sales'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Sales', 'schooladmin:sale_list', 'fa-cash-register',
            feature='stock',
        )
    if has_perm(user, 'can_manage_sales'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'New Sale', 'schooladmin:add_sale', 'fa-receipt',
            feature='stock',
        )
    if has_perm(user, 'can_manage_sales_returns'):
        add(
            'delegated', 'Assigned Modules', 'fa-user-shield',
            'Sales Returns', 'schooladmin:sales_return_list', 'fa-arrow-rotate-left',
            feature='stock',
        )

    for item in dynamic_items or []:
        add(
            'more', 'More Modules', 'fa-shapes',
            item['label'], icon=item.get('icon') or 'fa-puzzle-piece',
            url=item['url'], match=item['url'],
        )

    add(
        'account', 'Account', 'fa-user-gear',
        'My Profile', 'staff:profile', 'fa-user-circle',
    )
    add(
        'account', 'Account', 'fa-user-gear',
        'Change Password', 'handle:changePassword', 'fa-key',
    )
    add(
        'account', 'Account', 'fa-user-gear',
        'Log out', 'management:logout', 'fa-right-from-bracket',
    )
    return list(sections.values()), role, ROLE_LABELS[role]
