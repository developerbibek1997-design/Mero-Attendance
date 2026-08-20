"""
Breadcrumb trail builder: `{{ breadcrumbs }}` is injected into every template
via school.context_processors.org_and_features (see BREADCRUMB_MAP usage
below and the `breadcrumbs` context processor).

Each crumb is a dict: {'label': str, 'url': str_or_None}. The last crumb
always has url=None (it's the current page).

BREADCRUMB_MAP keys are `namespace:url_name` (e.g. 'schooladmin:bill_list').
Each value is the list of crumbs to show *after* the role's Dashboard root,
as (label, url_name_or_None) pairs — url_name is looked up in the same
namespace and reverse()'d; use None for a crumb that shouldn't be a link
(e.g. the current page, or a page that needs URL args we don't have here).

Pages not listed fall back to a single humanized crumb built from the
url_name, so every page still gets *some* breadcrumb trail without needing
a template-by-template edit.
"""

import re


# (label, url_name-or-None-for-no-link) after the role's Dashboard root
BREADCRUMB_MAP = {
    # ── Schooladmin (user_type '2') ─────────────────────────────────────
    'schooladmin:dashboard': [],
    'handle:addMember': [('Add Member', None)],
    'schooladmin:student_list': [('Student Management', None)],
    'handle:addClassification': [('Add Classification', None)],
    'handle:addDevice': [('Add Devices', None)],
    'handle:operations': [('Operations', None)],

    'schooladmin:dailyReport': [('Attendance & Reports', None), ('Daily Report', None)],
    'schooladmin:gapReport': [('Attendance & Reports', None), ('Gap Report', None)],
    'handle:memberReport': [('Attendance & Reports', None), ('Member Report', None)],

    'schooladmin:analytics': [('Analytics', None)],
    'schooladmin:playslip': [('Salary & Payslip', None)],
    'schooladmin:payroll_settings': [('Payroll Settings', None)],
    'schooladmin:admin_wifi_manage': [('Manage Office WiFi', None)],
    'schooladmin:qr_attendance': [('QR Attendance', None)],
    'schooladmin:absence_correction': [('Absence Correction', None)],

    'schooladmin:leaveReportView': [('HRMS & Leave Engine', 'schooladmin:leaveReportView'), ('Leave Requests', None)],
    'schooladmin:log_leave': [('HRMS & Leave Engine', 'schooladmin:leaveReportView'), ('Log Member Leave', None)],
    'schooladmin:manage_leave_types': [('HRMS & Leave Engine', 'schooladmin:leaveReportView'), ('Leave Policies', None)],
    'schooladmin:master_leave_report': [('HRMS & Leave Engine', 'schooladmin:leaveReportView'), ('Leave Balance Report', None)],

    'schooladmin:resignation_list': [('Resignations & Documents', 'schooladmin:resignation_list'), ('Resignations', None)],
    'schooladmin:document_list': [('Resignations & Documents', 'schooladmin:resignation_list'), ('Staff Documents', None)],

    'schooladmin:finance_dashboard': [('Finance', 'schooladmin:finance_dashboard'), ('Finance Dashboard', None)],
    'schooladmin:income_list': [('Finance', 'schooladmin:finance_dashboard'), ('Income', None)],
    'schooladmin:expense_list': [('Finance', 'schooladmin:finance_dashboard'), ('Expenses', None)],
    'schooladmin:finance_categories': [('Finance', 'schooladmin:finance_dashboard'), ('Finance Categories', None)],

    'schooladmin:stock_dashboard': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Stock Dashboard', None)],
    'schooladmin:stock_items': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Stock Items', None)],
    'schooladmin:stock_movements': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Movement History', None)],

    'schooladmin:event_list': [('Events', None)],
    'schooladmin:course_list': [('Academic', 'schooladmin:course_list'), ('Courses', None)],
    'schooladmin:study_gap_list': [('Study Gaps', None)],

    'schooladmin:subject_list': [('Results', 'schooladmin:subject_list'), ('Subjects & Results', None)],
    'schooladmin:bulk_result_send': [('Results', 'schooladmin:subject_list'), ('Bulk Result Send', None)],

    'schooladmin:complaint_list': [('Complaints', None)],
    'schooladmin:notice_list': [('Notice Board', None)],
    'schooladmin:notice_create': [('Notice Board', 'schooladmin:notice_list'), ('New Notice', None)],
    'schooladmin:notice_detail': [('Notice Board', 'schooladmin:notice_list'), ('Notice Detail', None)],
    'schooladmin:notice_edit': [('Notice Board', 'schooladmin:notice_list'), ('Edit Notice', None)],
    'staff:notices': [('Notices', None)],

    'schooladmin:bill_list': [('Billing', 'schooladmin:bill_list'), ('Bills & Invoices', None)],
    'schooladmin:create_bill': [('Billing', 'schooladmin:bill_list'), ('Create Bill', None)],
    'schooladmin:bulk_bill_generate': [('Billing', 'schooladmin:bill_list'), ('Bulk Generate', None)],
    'schooladmin:bulk_bill_send': [('Billing', 'schooladmin:bill_list'), ('Bulk Bill Send', None)],
    'schooladmin:bill_detail': [('Billing', 'schooladmin:bill_list'), ('Bill Detail', None)],

    'schooladmin:bulk_payslip': [('Payroll Tools', None), ('Bulk Payslip', None)],
    'schooladmin:advance_salary': [('Payroll Tools', None), ('Advance Salary', None)],

    'schooladmin:branch_list': [('Configuration', None), ('Branches', None)],
    'schooladmin:privilege_manage': [('Configuration', None), ('Privilege Levels', None)],
    'schooladmin:staff_permissions': [('Configuration', None), ('Staff Permissions', None)],
    'schooladmin:org_features': [('Configuration', None), ('Feature Settings', None)],
    'schooladmin:orgDetail': [('Configuration', None), ('Organization Profile', None)],

    'schooladmin:task_dashboard': [('Task Management', 'schooladmin:task_dashboard'), ('Task Dashboard', None)],
    'schooladmin:create_task': [('Task Management', 'schooladmin:task_dashboard'), ('Create Task', None)],
    'schooladmin:task_list': [('Task Management', 'schooladmin:task_dashboard'), ('All Tasks', None)],
    'schooladmin:task_report': [('Task Management', 'schooladmin:task_dashboard'), ('Task Report', None)],

    'schooladmin:timesheet_list': [('Timesheets', None)],
    'schooladmin:calendar': [('Calendar', None)],
    'schooladmin:appointments': [('Tools', None), ('Appointments', None)],
    'schooladmin:form_builder': [('Tools', None), ('Form Builder', None)],
    'schooladmin:export_hub': [('Data & Backup', None), ('Export / Backup', None)],
    'schooladmin:email_logs': [('Data & Backup', None), ('Email Logs', None)],

    'schooladmin:idcard_generate': [('ID Cards', 'schooladmin:idcard_generate'), ('Generate ID Cards', None)],
    'schooladmin:idcard_settings': [('ID Cards', 'schooladmin:idcard_generate'), ('Card Design Settings', None)],
    'schooladmin:certificate_generate': [('Document Studio', None), ('Generate Certificates', None)],
    'schooladmin:certificate_settings': [('Document Studio', 'schooladmin:certificate_generate'), ('Certificate Designer', None)],

    # ── Payroll (added) ──────────────────────────────────────────────
    'schooladmin:payslip_list': [('Payroll Tools', None), ('Payslip List', None)],
    'schooladmin:payslip_detail': [('Payroll Tools', None), ('Payslip Detail', None)],

    # ── Roles & Permissions (added) ──────────────────────────────────
    'schooladmin:roles_permissions_list': [('Configuration', None), ('Roles & Permissions', None)],
    'schooladmin:roles_permissions_edit': [('Configuration', None), ('Roles & Permissions', None)],

    # ── Students (added) ─────────────────────────────────────────────
    'schooladmin:student_add': [('Student Management', 'schooladmin:student_list'), ('Add Student', None)],
    'schooladmin:student_edit': [('Student Management', 'schooladmin:student_list'), ('Edit Student', None)],
    'schooladmin:student_profile': [('Student Management', 'schooladmin:student_list'), ('Student Profile', None)],
    'schooladmin:member_profile': [('Attendance & Reports', 'handle:memberReport'), ('Member Profile', None)],
    'schooladmin:classification_detail': [('School Structure', None), ('Classification Detail', None)],

    # ── HRMS & Resignations (added) ──────────────────────────────────
    'schooladmin:add_resignation': [('Resignations & Documents', 'schooladmin:resignation_list'), ('Add Resignation', None)],
    'schooladmin:update_resignation': [('Resignations & Documents', 'schooladmin:resignation_list'), ('Update Resignation', None)],
    'schooladmin:update_resignation_email': [('Resignations & Documents', 'schooladmin:resignation_list'), ('Update Resignation', None)],
    'schooladmin:upload_document': [('Resignations & Documents', 'schooladmin:resignation_list'), ('Upload Document', None)],
    'schooladmin:leave_status_email': [('HRMS & Leave Engine', 'schooladmin:leaveReportView'), ('Leave Status', None)],

    # ── Academic / Courses / Results (added) ─────────────────────────
    'schooladmin:add_course': [('Academic', 'schooladmin:course_list'), ('Add Course', None)],
    'schooladmin:course_attendance': [('Academic', 'schooladmin:course_list'), ('Course Attendance', None)],
    'schooladmin:result_entry': [('Results', 'schooladmin:subject_list'), ('Result Entry', None)],
    'schooladmin:result_report': [('Results', 'schooladmin:subject_list'), ('Result Report', None)],
    'schooladmin:result_publish_summary': [('Results', 'schooladmin:subject_list'), ('Publish Results', None)],
    'schooladmin:publish_exam': [('Results', 'schooladmin:subject_list'), ('Publish Exam', None)],
    'schooladmin:exam_terms': [('Results', 'schooladmin:subject_list'), ('Exam Terms', None)],
    'schooladmin:marksheet': [('Results', 'schooladmin:subject_list'), ('Marksheet', None)],

    # ── Events (added) ────────────────────────────────────────────────
    'schooladmin:add_event': [('Events', 'schooladmin:event_list'), ('Add Event', None)],
    'schooladmin:event_detail': [('Events', 'schooladmin:event_list'), ('Event Detail', None)],

    # ── Stock (added) ─────────────────────────────────────────────────
    'schooladmin:add_stock_item': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Add Stock Item', None)],
    'schooladmin:edit_stock_item': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Edit Stock Item', None)],
    'schooladmin:stock_in': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Stock In', None)],
    'schooladmin:stock_out': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Stock Out', None)],
    'schooladmin:stock_categories': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Stock Categories', None)],

    # ── Finance (added) ───────────────────────────────────────────────
    'schooladmin:add_income': [('Finance', 'schooladmin:finance_dashboard'), ('Add Income', None)],
    'schooladmin:edit_income': [('Finance', 'schooladmin:finance_dashboard'), ('Edit Income', None)],
    'schooladmin:add_expense': [('Finance', 'schooladmin:finance_dashboard'), ('Add Expense', None)],
    'schooladmin:edit_expense': [('Finance', 'schooladmin:finance_dashboard'), ('Edit Expense', None)],

    # ── Billing (added) ───────────────────────────────────────────────
    'schooladmin:billing_reminders': [('Billing', 'schooladmin:bill_list'), ('Billing Reminders', None)],

    # ── Complaints (added) ────────────────────────────────────────────
    'schooladmin:complaint_detail': [('Complaints', 'schooladmin:complaint_list'), ('Complaint Detail', None)],
    'schooladmin:complaint_detail_manage': [('Complaints', 'schooladmin:complaint_list'), ('Manage Complaint', None)],
    'schooladmin:file_complaint': [('Complaints', 'schooladmin:complaint_list'), ('File Complaint', None)],

    # ── Clients / CRM (added) ─────────────────────────────────────────
    'schooladmin:client_list': [('Clients', 'schooladmin:client_list'), ('Clients', None)],
    'schooladmin:client_detail': [('Clients', 'schooladmin:client_list'), ('Client Detail', None)],
    'schooladmin:create_client': [('Clients', 'schooladmin:client_list'), ('Add Client', None)],
    'schooladmin:client_followup_due': [('Clients', 'schooladmin:client_list'), ('Follow-ups Due', None)],

    # ── Field Visits (added) ──────────────────────────────────────────
    'schooladmin:field_visit_list': [('Field Visits', 'schooladmin:field_visit_list'), ('Field Visits', None)],
    'schooladmin:field_visit_detail': [('Field Visits', 'schooladmin:field_visit_list'), ('Field Visit Detail', None)],
    'schooladmin:live_tracking': [('Field Visits', 'schooladmin:field_visit_list'), ('Live Tracking', None)],
    'schooladmin:live_tracking_detail': [('Field Visits', 'schooladmin:field_visit_list'), ('Live Tracking Detail', None)],

    # ── Tasks (added) ─────────────────────────────────────────────────
    'schooladmin:task_detail': [('Task Management', 'schooladmin:task_dashboard'), ('Task Detail', None)],

    # ── Timesheets (added) ────────────────────────────────────────────
    'schooladmin:timesheet_detail': [('Timesheets', 'schooladmin:timesheet_list'), ('Timesheet Detail', None)],
    'schooladmin:timesheet_approve': [('Timesheets', 'schooladmin:timesheet_list'), ('Timesheet Detail', None)],
    'schooladmin:timesheet_reject': [('Timesheets', 'schooladmin:timesheet_list'), ('Timesheet Detail', None)],

    # ── Shifts (added) ────────────────────────────────────────────────
    'schooladmin:shift_list': [('Shifts', 'schooladmin:shift_list'), ('Shift List', None)],
    'schooladmin:shift_new': [('Shifts', 'schooladmin:shift_list'), ('New Shift', None)],
    'schooladmin:shift_edit': [('Shifts', 'schooladmin:shift_list'), ('Edit Shift', None)],
    'schooladmin:shift_assign': [('Shifts', 'schooladmin:shift_list'), ('Assign Shift', None)],
    'schooladmin:shift_report': [('Shifts', 'schooladmin:shift_list'), ('Shift Report', None)],

    # ── Geo Fence / Auto Check-in (added) ─────────────────────────────
    'schooladmin:location_list': [('Geo Fence Zones', 'schooladmin:location_list'), ('Geo Fence Zones', None)],
    'schooladmin:location_add': [('Geo Fence Zones', 'schooladmin:location_list'), ('Add Zone', None)],
    'schooladmin:location_edit': [('Geo Fence Zones', 'schooladmin:location_list'), ('Edit Zone', None)],
    'schooladmin:auto_checkin_list': [('Auto Check-in', 'schooladmin:auto_checkin_list'), ('Auto Check-in', None)],
    'schooladmin:auto_checkin_add': [('Auto Check-in', 'schooladmin:auto_checkin_list'), ('Add Rule', None)],
    'schooladmin:auto_checkin_edit': [('Auto Check-in', 'schooladmin:auto_checkin_list'), ('Edit Rule', None)],

    # ── QR / Face / Manual attendance (added) ─────────────────────────
    'schooladmin:qrcode_list': [('QR Attendance', 'schooladmin:qr_attendance'), ('QR Stations', None)],
    'schooladmin:qrcode_add': [('QR Attendance', 'schooladmin:qr_attendance'), ('Add QR Station', None)],
    'schooladmin:qrcode_edit': [('QR Attendance', 'schooladmin:qr_attendance'), ('Edit QR Station', None)],
    'schooladmin:qr_generate': [('QR Attendance', 'schooladmin:qr_attendance'), ('Generate QR', None)],
    'schooladmin:face_attendance': [('Face Attendance', None)],
    'schooladmin:face_enroll': [('Face Attendance', 'schooladmin:face_attendance'), ('Enroll Face', None)],
    'schooladmin:face_enroll_list': [('Face Attendance', 'schooladmin:face_attendance'), ('Enrolled Faces', None)],
    'schooladmin:manual_attendance': [('Attendance & Reports', 'handle:memberReport'), ('Manual Attendance', None)],

    # ── Reports (added) ───────────────────────────────────────────────
    'schooladmin:monthly_report': [('Attendance & Reports', 'handle:memberReport'), ('Monthly Report', None)],
    'schooladmin:memberGapReport': [('Attendance & Reports', 'handle:memberReport'), ('Gap Report', None)],
    'schooladmin:allRecord': [('Attendance & Reports', 'handle:memberReport'), ('All Records', None)],

    # ── Form Builder (added) ──────────────────────────────────────────
    'schooladmin:form_builder_new': [('Tools', 'schooladmin:form_builder'), ('New Form', None)],
    'schooladmin:form_builder_edit': [('Tools', 'schooladmin:form_builder'), ('Edit Form', None)],
    'schooladmin:form_submissions': [('Tools', 'schooladmin:form_builder'), ('Form Submissions', None)],

    'schooladmin:dynamic_feature': [('More Modules', None)],

    # ── Suppliers / Purchases / Sales (added) ────────────────────────
    'schooladmin:supplier_list': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Suppliers', None)],
    'schooladmin:add_supplier': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Suppliers', 'schooladmin:supplier_list'), ('Add Supplier', None)],
    'schooladmin:supplier_detail': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Suppliers', 'schooladmin:supplier_list'), ('Supplier Detail', None)],
    'schooladmin:edit_supplier': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Suppliers', 'schooladmin:supplier_list'), ('Edit Supplier', None)],
    'schooladmin:convert_client_to_supplier': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Suppliers', 'schooladmin:supplier_list'), ('Convert Client to Supplier', None)],

    'schooladmin:purchase_list': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Purchases', None)],
    'schooladmin:add_purchase': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Purchases', 'schooladmin:purchase_list'), ('Add Purchase', None)],
    'schooladmin:purchase_detail': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Purchases', 'schooladmin:purchase_list'), ('Purchase Detail', None)],

    'schooladmin:purchase_return_list': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Purchase Returns', None)],
    'schooladmin:add_purchase_return': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Purchase Returns', 'schooladmin:purchase_return_list'), ('Add Purchase Return', None)],
    'schooladmin:purchase_return_detail': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Purchase Returns', 'schooladmin:purchase_return_list'), ('Purchase Return Detail', None)],

    'schooladmin:sale_list': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Sales', None)],
    'schooladmin:add_sale': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Sales', 'schooladmin:sale_list'), ('Add Sale', None)],
    'schooladmin:sale_detail': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Sales', 'schooladmin:sale_list'), ('Sale Detail', None)],

    'schooladmin:sales_return_list': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Sales Returns', None)],
    'schooladmin:add_sales_return': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Sales Returns', 'schooladmin:sales_return_list'), ('Add Sales Return', None)],
    'schooladmin:sales_return_detail': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Sales Returns', 'schooladmin:sales_return_list'), ('Sales Return Detail', None)],

    'schooladmin:asset_list': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Assets', None)],
    'schooladmin:add_asset': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Assets', 'schooladmin:asset_list'), ('Add Asset', None)],
    'schooladmin:asset_detail': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Assets', 'schooladmin:asset_list'), ('Asset Detail', None)],

    'schooladmin:stock_adjustment': [('Stock / Inventory', 'schooladmin:stock_dashboard'), ('Stock Adjustment', None)],

    # ── Library (added) ───────────────────────────────────────────────
    'schooladmin:library_dashboard': [('Library', None)],
    'schooladmin:library_books': [('Library', 'schooladmin:library_dashboard'), ('Books', None)],
    'schooladmin:add_book': [('Library', 'schooladmin:library_dashboard'), ('Books', 'schooladmin:library_books'), ('Add Book', None)],
    'schooladmin:edit_book': [('Library', 'schooladmin:library_dashboard'), ('Books', 'schooladmin:library_books'), ('Edit Book', None)],
    'schooladmin:library_issue': [('Library', 'schooladmin:library_dashboard'), ('Issue Book', None)],
    'schooladmin:library_issues': [('Library', 'schooladmin:library_dashboard'), ('Issue History', None)],
    'schooladmin:library_return': [('Library', 'schooladmin:library_dashboard'), ('Issue History', 'schooladmin:library_issues'), ('Return Book', None)],
    'schooladmin:library_categories': [('Library', 'schooladmin:library_dashboard'), ('Library Catalog Setup', None)],
    'schooladmin:library_authors': [('Library', 'schooladmin:library_dashboard'), ('Library Catalog Setup', 'schooladmin:library_categories'), ('Authors', None)],
    'schooladmin:library_publishers': [('Library', 'schooladmin:library_dashboard'), ('Library Catalog Setup', 'schooladmin:library_categories'), ('Publishers', None)],
    'schooladmin:library_racks_shelves': [('Library', 'schooladmin:library_dashboard'), ('Library Catalog Setup', 'schooladmin:library_categories'), ('Racks & Shelves', None)],
    'schooladmin:library_settings': [('Library', 'schooladmin:library_dashboard'), ('Library Catalog Setup', 'schooladmin:library_categories'), ('Library Settings', None)],

    # ── Accounting (added) ────────────────────────────────────────────
    'schooladmin:accounting_dashboard': [('Accounting', None)],
    'schooladmin:accounting_accounts': [('Accounting', 'schooladmin:accounting_dashboard'), ('Chart of Accounts', None)],
    'schooladmin:add_account': [('Accounting', 'schooladmin:accounting_dashboard'), ('Chart of Accounts', 'schooladmin:accounting_accounts'), ('Add Account', None)],
    'schooladmin:edit_account': [('Accounting', 'schooladmin:accounting_dashboard'), ('Chart of Accounts', 'schooladmin:accounting_accounts'), ('Edit Account', None)],
    'schooladmin:journal_list': [('Accounting', 'schooladmin:accounting_dashboard'), ('Journal Entries', None)],
    'schooladmin:add_journal': [('Accounting', 'schooladmin:accounting_dashboard'), ('Journal Entries', 'schooladmin:journal_list'), ('New Journal Entry', None)],
    'schooladmin:journal_detail': [('Accounting', 'schooladmin:accounting_dashboard'), ('Journal Entries', 'schooladmin:journal_list'), ('Journal Entry Detail', None)],
    'schooladmin:edit_journal': [('Accounting', 'schooladmin:accounting_dashboard'), ('Journal Entries', 'schooladmin:journal_list'), ('Edit Journal Entry', None)],
    'schooladmin:general_ledger': [('Accounting', 'schooladmin:accounting_dashboard'), ('General Ledger', None)],
    'schooladmin:trial_balance': [('Accounting', 'schooladmin:accounting_dashboard'), ('Financial Reports', 'schooladmin:trial_balance'), ('Trial Balance', None)],
    'schooladmin:profit_and_loss': [('Accounting', 'schooladmin:accounting_dashboard'), ('Financial Reports', 'schooladmin:trial_balance'), ('Profit & Loss', None)],
    'schooladmin:balance_sheet': [('Accounting', 'schooladmin:accounting_dashboard'), ('Financial Reports', 'schooladmin:trial_balance'), ('Balance Sheet', None)],

    # ── Academic Management (added) ───────────────────────────────────
    'schooladmin:academic_years': [('Academic Management', 'schooladmin:academic_years'), ('Academic Years', None)],
    'schooladmin:faculty_list': [('Academic Management', 'schooladmin:academic_years'), ('Faculties', None)],
    'schooladmin:semester_list': [('Academic Management', 'schooladmin:academic_years'), ('Semesters', None)],
    'schooladmin:course_teachers': [('Academic Management', 'schooladmin:academic_years'), ('Course Teacher Assignment', None)],
    'schooladmin:subject_teachers': [('Academic Management', 'schooladmin:academic_years'), ('Subject Teacher Assignment', None)],

    'schooladmin:assignment_list': [('Academic Management', 'schooladmin:academic_years'), ('Assignments', None)],
    'schooladmin:add_assignment': [('Academic Management', 'schooladmin:academic_years'), ('Assignments', 'schooladmin:assignment_list'), ('Add Assignment', None)],
    'schooladmin:assignment_detail': [('Academic Management', 'schooladmin:academic_years'), ('Assignments', 'schooladmin:assignment_list'), ('Assignment Detail', None)],
    'schooladmin:edit_assignment': [('Academic Management', 'schooladmin:academic_years'), ('Assignments', 'schooladmin:assignment_list'), ('Edit Assignment', None)],

    'schooladmin:homework_list': [('Academic Management', 'schooladmin:academic_years'), ('Homework', None)],
    'schooladmin:add_homework': [('Academic Management', 'schooladmin:academic_years'), ('Homework', 'schooladmin:homework_list'), ('Add Homework', None)],
    'schooladmin:homework_detail': [('Academic Management', 'schooladmin:academic_years'), ('Homework', 'schooladmin:homework_list'), ('Homework Detail', None)],
    'schooladmin:edit_homework': [('Academic Management', 'schooladmin:academic_years'), ('Homework', 'schooladmin:homework_list'), ('Edit Homework', None)],

    'schooladmin:course_material_list': [('Academic Management', 'schooladmin:academic_years'), ('Course Materials', None)],
    'schooladmin:add_course_material': [('Academic Management', 'schooladmin:academic_years'), ('Course Materials', 'schooladmin:course_material_list'), ('Add Course Material', None)],
    'schooladmin:edit_course_material': [('Academic Management', 'schooladmin:academic_years'), ('Course Materials', 'schooladmin:course_material_list'), ('Edit Course Material', None)],

    'schooladmin:teaching_log_list': [('Academic Management', 'schooladmin:academic_years'), ('Teaching Logs', None)],
    'schooladmin:teaching_log_detail': [('Academic Management', 'schooladmin:academic_years'), ('Teaching Logs', 'schooladmin:teaching_log_list'), ('Teaching Log Detail', None)],
    'schooladmin:my_teaching_logs': [('Academic Management', 'schooladmin:academic_years'), ('Teaching Logs', 'schooladmin:teaching_log_list'), ('My Teaching Logs', None)],
    'schooladmin:add_teaching_log': [('Academic Management', 'schooladmin:academic_years'), ('Teaching Logs', 'schooladmin:teaching_log_list'), ('Add Teaching Log', None)],
    'schooladmin:subject_attendance_report': [('Academic Management', 'schooladmin:academic_years'), ('Subject Attendance Report', None)],

    'schooladmin:routine_grid': [('Academic Management', 'schooladmin:academic_years'), ('Class Routine', None)],
    'schooladmin:add_routine_period': [('Academic Management', 'schooladmin:academic_years'), ('Class Routine', 'schooladmin:routine_grid'), ('Add Routine Period', None)],
    'schooladmin:edit_routine_period': [('Academic Management', 'schooladmin:academic_years'), ('Class Routine', 'schooladmin:routine_grid'), ('Edit Routine Period', None)],
    'schooladmin:teacher_routine': [('Academic Management', 'schooladmin:academic_years'), ('Class Routine', 'schooladmin:routine_grid'), ('My Routine', None)],

    # ── Staff / Teacher / Student portal (user_type '3') ────────────────
    'staff:dashboard': [],
    'staff:student_bills': [('Student Portal', None), ('My Bills', None)],
    'staff:student_results': [('Student Portal', None), ('My Results', None)],
    'staff:student_gaps': [('My Absence Gaps', None)],
    'staff:my_attendance': [('My Attendance', None)],
    'staff:qr_attendance': [('Scan QR Attendance', None)],
    'staff:apply_leave': [('Apply Leave', None)],
    'staff:student_complaint': [('Complaints', None)],
    'staff:teaching_log': [('Teaching', None), ('Teaching Log', None)],
    'staff:subject_teaching_log': [('Teaching', None), ('Subject Attendance', None)],
    'staff:report': [('Class Reports', None)],
    'staff:my_payslips': [('My Records', None), ('My Payslips', None)],
    'staff:my_resignation': [('My Records', None), ('My Resignation', None)],
    'staff:my_tasks': [('Tasks', None), ('My Tasks', None)],
    'staff:timesheet_list': [('Timesheets', None), ('My Timesheets', None)],
    'handle:changePassword': [('Account', None), ('Change Password', None)],

    # ── Staff — delegated views (added) ──────────────────────────────
    'staff:payroll_report': [('Payroll', 'staff:payroll_report'), ('Payroll Report', None)],
    'staff:payroll_payslip_detail': [('Payroll', 'staff:payroll_report'), ('Payslip Detail', None)],
    'staff:payroll_settings': [('Payroll', 'staff:payroll_report'), ('Payroll Settings', None)],
    'staff:generate_payslip': [('Payroll', 'staff:payroll_report'), ('Generate Payslip', None)],
    'staff:leave_approval': [('Leave', 'staff:apply_leave'), ('Leave Approval', None)],
    'staff:leave_report': [('Leave', 'staff:apply_leave'), ('Leave Report', None)],
    'staff:hrms': [('HR Module', None)],
    'staff:course_list': [('Courses & Results', 'staff:course_list'), ('My Courses', None)],
    'staff:manage_courses': [('Courses & Results', 'staff:course_list'), ('Manage Courses', None)],
    'staff:result_entry': [('Courses & Results', 'staff:course_list'), ('Result Entry', None)],
    'staff:result_report': [('Courses & Results', 'staff:course_list'), ('Result Report', None)],
    'staff:stock_dashboard': [('Stock', 'staff:stock_dashboard'), ('Stock Overview', None)],
    'staff:stock_items': [('Stock', 'staff:stock_dashboard'), ('Stock Items', None)],
    'staff:add_stock_item': [('Stock', 'staff:stock_dashboard'), ('Add Stock Item', None)],
    'staff:edit_stock_item': [('Stock', 'staff:stock_dashboard'), ('Edit Stock Item', None)],
    'staff:stock_in': [('Stock', 'staff:stock_dashboard'), ('Stock In', None)],
    'staff:stock_out': [('Stock', 'staff:stock_dashboard'), ('Stock Out', None)],
    'staff:stock_movement_history': [('Stock', 'staff:stock_dashboard'), ('Movement History', None)],
    'staff:branch_list': [('Branches', None)],
    'staff:manage_branches': [('Branches', 'staff:branch_list'), ('Add Branch', None)],
    'staff:event_list': [('Events', None)],
    'staff:manage_events': [('Events', 'staff:event_list'), ('Manage Events', None)],
    'staff:field_visit_list': [('Field Visits', None)],
    'staff:send_location': [('Field Visits', 'staff:field_visit_list'), ('Send My Location', None)],
    'staff:live_tracking': [('Field Visits', 'staff:field_visit_list'), ('Live Tracking', None)],
    'staff:create_bill': [('Billing', 'staff:billing_dues'), ('Create Bill', None)],
    'staff:bill_detail': [('Billing', 'staff:billing_dues'), ('Bill Detail', None)],
    'staff:billing_dues': [('Billing', 'staff:billing_dues'), ('Billing Dues', None)],
    'staff:finance_dashboard': [('Finance', None)],
    'staff:add_income': [('Finance', 'staff:finance_dashboard'), ('Add Income', None)],
    'staff:add_expense': [('Finance', 'staff:finance_dashboard'), ('Add Expense', None)],
    'staff:export_hub': [('Reports', None), ('Exports', None)],
    'staff:create_task': [('Tasks', 'staff:my_tasks'), ('Assign Task', None)],
    'staff:task_dashboard': [('Tasks', 'staff:my_tasks'), ('Task Dashboard', None)],
    'staff:task_list': [('Tasks', 'staff:my_tasks'), ('All Tasks', None)],
    'staff:task_detail': [('Tasks', 'staff:my_tasks'), ('Task Detail', None)],
    'staff:task_report': [('Tasks', 'staff:my_tasks'), ('Task Report', None)],
    'staff:complaint_list': [('Complaints', 'staff:complaint_list'), ('Manage Complaints', None)],
    'staff:complaint_detail': [('Complaints', 'staff:complaint_list'), ('Complaint Detail', None)],
    'staff:client_list': [('Clients', 'staff:client_list'), ('Clients', None)],
    'staff:client_detail': [('Clients', 'staff:client_list'), ('Client Detail', None)],
    'staff:wifi_checkin': [('WiFi Check-in', None)],
    'staff:location_checkin': [('Location Check-in', None)],
    'staff:attendance': [('My Attendance', None)],
    'staff:my_report': [('Class Reports', None)],
    'staff:timesheet_create': [('Timesheets', 'staff:timesheet_list'), ('New Timesheet', None)],
    'staff:timesheet_detail': [('Timesheets', 'staff:timesheet_list'), ('Timesheet Detail', None)],
    'staff:timesheet_submit': [('Timesheets', 'staff:timesheet_list'), ('Submit Timesheet', None)],
    'staff:dynamic_feature': [('More Modules', None)],

    # ── Superadmin (user_type '1') ──────────────────────────────────────
    'superadmin:dashboard': [],
    'superadmin:addUser': [('Add Admin', None)],
    'superadmin:addOrg': [('Add Organization', None)],
    'superadmin:memberList': [('Members List', None)],
    'superadmin:setting': [('System Settings', None)],
    'superadmin:attendance_report': [('Reports & Tools', None), ('Attendance Report', None)],
    'superadmin:globalHoliday': [('Reports & Tools', None), ('Push Holidays', None)],
    'superadmin:broadcastEmail': [('Reports & Tools', None), ('Broadcast Email', None)],
    'superadmin:agent_list': [('Reports & Tools', None), ('Agent Management', None)],
    'superadmin:orgDetail': [('Members List', 'superadmin:memberList'), ('Organization Detail', None)],
}

DASHBOARD_ROOT = {
    '1': ('Dashboard', 'superadmin:dashboard'),
    '2': ('Dashboard', 'schooladmin:dashboard'),
    '3': ('Dashboard', 'staff:dashboard'),
}

_CAMEL_SPLIT_RE = re.compile(r'(?<!^)(?=[A-Z])')


def _humanize(url_name):
    """'bulk_bill_generate' or 'orgDetail' -> 'Bulk Bill Generate' / 'Org Detail'."""
    spaced = url_name.replace('_', ' ').replace('-', ' ')
    spaced = _CAMEL_SPLIT_RE.sub(' ', spaced)
    return ' '.join(w.capitalize() for w in spaced.split())


def build_breadcrumbs(request):
    """Return a list of {'label', 'url'} crumbs for the current request."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return []

    user_type = getattr(user, 'user_type', None)
    root = DASHBOARD_ROOT.get(user_type)
    if not root:
        return []

    from django.urls import reverse, NoReverseMatch

    root_label, root_url_name = root
    try:
        root_url = reverse(root_url_name)
    except NoReverseMatch:
        root_url = None
    crumbs = [{'label': root_label, 'url': root_url}]

    match = getattr(request, 'resolver_match', None)
    if not match or not match.url_name:
        crumbs[-1]['url'] = None
        return crumbs

    key = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name

    if key == root_url_name:
        # We're already on the dashboard root itself.
        crumbs[-1]['url'] = None
        return crumbs

    tail = BREADCRUMB_MAP.get(key)
    if tail is None:
        tail = [(_humanize(match.url_name), None)]

    for label, link_url_name in tail:
        url = None
        if link_url_name:
            try:
                url = reverse(link_url_name)
            except NoReverseMatch:
                url = None
        crumbs.append({'label': label, 'url': url})

    # The final crumb is always the current page — never a link.
    crumbs[-1]['url'] = None
    return crumbs
