from django.urls import path
from . import views
from .api import (
    api_staff_classes, api_class_members, api_mark_present, api_my_permissions,
    api_my_attendance_status, api_my_field_visits, api_my_field_visit_action,
    api_live_tracking, api_my_tasks, api_my_task_detail,
    api_my_notices, api_my_events, api_my_calendar,
    api_my_complaints, api_my_complaint_detail,
    api_student_dashboard, api_student_bills, api_student_routine,
    api_student_academic_work, api_student_results,
    api_teacher_dashboard, api_teacher_routine,
    api_teacher_attendance_context, api_teacher_academic_work,
    api_teacher_exams, api_teacher_exam_marks, api_teacher_sessions,
    api_driver_bus_tracking, api_student_bus_tracking,
    api_library_books, api_my_book_issues,
)

app_name = 'staff'

urlpatterns = [

    # Main Dashboard
    path('staffdashboard', views.Dashboard, name="dashboard"),
    path('profile/', views.PortalProfileView.as_view(), name="profile"),

    # Attendance
    path('staff-member-report', views.memReport.as_view(), name="report"),
    path('do-attendance-right-now/<int:id>/present-absent/<str:name>', views.attendanceView, name="attendance"),
    path('mark_present/', views.mark_present, name='mark_present'),
    path('my-attendance/', views.MyAttendanceReportView.as_view(), name='my_attendance'),
    path('notices/', views.StaffNoticeListView.as_view(), name='notices'),
    path('my-report/', views.MyAttendanceReportView.as_view(), name="my_report"),

    # Leave
    path('apply-leave/', views.StaffLeaveView.as_view(), name='apply_leave'),
    path('leave/<int:pk>/delete/', views.StaffLeaveDeleteView.as_view(), name='delete_leave'),

    # Check-in methods
    path('location-checkin/', views.StaffLocationCheckinView.as_view(), name='location_checkin'),
    path('wifi-checkin/', views.StaffWifiCheckinView.as_view(), name='wifi_checkin'),
    path('qr-attendance/', views.StaffQRScanView.as_view(), name='qr_attendance'),
    path('api/staff/qr-scan/', views.api_qr_attendance_scan, name='api_qr_attendance_scan'),

    # Field Visits
    path('send-location/', views.StaffSendLocationView.as_view(), name='send_location'),
    path('live-tracking/', views.StaffLiveTrackingView.as_view(), name='live_tracking'),

    # Clients
    path('clients/', views.StaffClientListView.as_view(), name='client_list'),
    path('clients/<int:pk>/', views.StaffClientDetailView.as_view(), name='client_detail'),
    path('clients/log-followup/', views.StaffLogFollowUpView.as_view(), name='log_followup'),

    # Payslips
    path('my-payslips/', views.MyPayslipsView.as_view(), name='my_payslips'),

    # Delegated Payroll (Phase 3, Batch 1)
    path('payroll-report/', views.StaffPayrollReportView.as_view(), name='payroll_report'),
    path('payroll-report/payslip/<int:pk>/', views.StaffPayslipDetailView.as_view(), name='payroll_payslip_detail'),
    path('payroll-settings/', views.StaffPayrollSettingsView.as_view(), name='payroll_settings'),
    path('generate-payslip/', views.StaffGeneratePayslipView.as_view(), name='generate_payslip'),

    # Delegated Leave approval + reporting (Phase 3, Batch 1)
    path('leave-approval/', views.StaffLeaveApprovalView.as_view(), name='leave_approval'),
    path('leave-report/', views.StaffLeaveReportView.as_view(), name='leave_report'),

    # Delegated HRMS (Phase 3, Batch 1)
    path('hrms/', views.StaffHRMSView.as_view(), name='hrms'),

    # Delegated Academic — Courses + Results (Phase 3, Batch 2)
    path('courses/', views.StaffCourseListView.as_view(), name='course_list'),
    path('courses/manage/', views.StaffManageCoursesView.as_view(), name='manage_courses'),
    path('results/entry/', views.StaffResultEntryView.as_view(), name='result_entry'),
    path('results/report/', views.StaffResultReportView.as_view(), name='result_report'),

    # Delegated Operations — Stock, Branches, Events, Field Visits (Phase 3, Batch 3)
    path('stock/', views.StaffStockDashboardView.as_view(), name='stock_dashboard'),
    path('stock/items/', views.StaffStockItemListView.as_view(), name='stock_items'),
    path('stock/items/add/', views.StaffAddStockItemView.as_view(), name='add_stock_item'),
    path('stock/items/<int:pk>/edit/', views.StaffEditStockItemView.as_view(), name='edit_stock_item'),
    path('stock/in/', views.StaffStockInView.as_view(), name='stock_in'),
    path('stock/out/', views.StaffStockOutView.as_view(), name='stock_out'),
    path('stock/history/', views.StaffStockMovementHistoryView.as_view(), name='stock_movement_history'),

    path('branches/', views.StaffBranchListView.as_view(), name='branch_list'),
    path('branches/manage/', views.StaffManageBranchesView.as_view(), name='manage_branches'),

    path('events/', views.StaffEventListView.as_view(), name='event_list'),
    path('events/manage/', views.StaffManageEventsView.as_view(), name='manage_events'),

    path('field-visits/', views.StaffFieldVisitListView.as_view(), name='field_visit_list'),

    # Delegated Finance, Billing & Reporting (Phase 3, Batch 4)
    path('billing/create/', views.StaffCreateBillView.as_view(), name='create_bill'),
    path('billing/<int:pk>/', views.StaffBillDetailView.as_view(), name='bill_detail'),
    path('billing/dues/', views.StaffBillingDuesView.as_view(), name='billing_dues'),
    path('billing/dues/export/', views.StaffExportBillingView.as_view(), name='export_billing'),

    path('finance/', views.StaffFinanceDashboardView.as_view(), name='finance_dashboard'),
    path('finance/income/add/', views.StaffAddIncomeView.as_view(), name='add_income'),
    path('finance/expense/add/', views.StaffAddExpenseView.as_view(), name='add_expense'),

    path('reports/export-hub/', views.StaffExportHubView.as_view(), name='export_hub'),
    path('reports/export/payslips/', views.StaffExportPayslipsView.as_view(), name='export_payslips'),
    path('reports/export/stock/', views.StaffExportStockView.as_view(), name='export_stock'),
    path('reports/export/finance/', views.StaffExportFinanceView.as_view(), name='export_finance'),
    path('reports/export/leave/', views.StaffExportLeaveView.as_view(), name='export_leave'),
    path('reports/export/attendance/', views.StaffExportAttendanceView.as_view(), name='export_attendance'),
    path('reports/export/members/', views.StaffExportMembersView.as_view(), name='export_members'),
    path('reports/export/tasks/', views.StaffExportTasksView.as_view(), name='export_tasks_csv'),

    path('tasks/create/', views.StaffCreateTaskView.as_view(), name='create_task'),
    path('tasks/dashboard/', views.StaffTaskDashboardView.as_view(), name='task_dashboard'),
    path('tasks/list/', views.StaffTaskListView.as_view(), name='task_list'),
    path('tasks/<int:pk>/', views.StaffTaskDetailView.as_view(), name='task_detail'),
    path('tasks/report/', views.StaffTaskReportView.as_view(), name='task_report'),

    path('complaints/manage/', views.StaffComplaintListView.as_view(), name='complaint_list'),
    path('complaints/manage/<int:pk>/', views.StaffComplaintDetailView.as_view(), name='complaint_detail'),

    # Student portal
    path('my-bills/', views.StudentBillsView.as_view(), name='student_bills'),
    path('my-results/', views.StudentResultsView.as_view(), name='student_results'),
    path('my-gaps/', views.StudentGapsView.as_view(), name='student_gaps'),
    path('my-complaint/', views.StudentComplaintView.as_view(), name='student_complaint'),

    # Teaching log (staff)
    path('teaching-log/', views.TeachingLogView.as_view(), name='teaching_log'),
    path('subject-teaching-log/', views.SubjectTeachingLogView.as_view(), name='subject_teaching_log'),
    path('my-class-routine/', views.StaffTeacherRoutineView.as_view(), name='teacher_routine'),
    path('my-subject-attendance-report/', views.TeacherSubjectAttendanceReportView.as_view(), name='teacher_subject_attendance_report'),
    path('api/academic/my-subject-assignments/', views.api_my_subject_assignments, name='api_my_subject_assignments'),
    path('api/academic/subjects/<int:subject_id>/roster/', views.api_assigned_subject_roster, name='api_assigned_subject_roster'),
    path('api/academic/subject-attendance/', views.api_submit_subject_attendance, name='api_submit_subject_attendance'),

    # Task Management
    path('tasks/', views.MyTasksView.as_view(), name='my_tasks'),
    path('tasks/<int:pk>/update/', views.UpdateTaskStatusView.as_view(), name='update_task_status'),

    # Resignation
    path('my-resignation/', views.StaffResignationView.as_view(), name='my_resignation'),

    # --- APIs ---
    # Attendance APIs
    path('api/staff/classes/', api_staff_classes, name='api_staff_classes'),
    path('api/my-permissions/', api_my_permissions, name='api_my_permissions'),
    path('api/mobile/attendance-status/', api_my_attendance_status, name='api_my_attendance_status'),
    path('api/mobile/field-visits/', api_my_field_visits, name='api_my_field_visits'),
    path('api/mobile/field-visits/<int:visit_id>/action/', api_my_field_visit_action, name='api_my_field_visit_action'),
    path('api/mobile/live-tracking/', api_live_tracking, name='api_live_tracking'),
    path('api/mobile/tasks/', api_my_tasks, name='api_my_tasks'),
    path('api/mobile/tasks/<int:instance_id>/', api_my_task_detail, name='api_my_task_detail'),
    path('api/mobile/notices/', api_my_notices, name='api_my_notices'),
    path('api/mobile/events/', api_my_events, name='api_my_events'),
    path('api/mobile/calendar/', api_my_calendar, name='api_my_calendar'),
    path('api/mobile/complaints/', api_my_complaints, name='api_my_complaints'),
    path('api/mobile/complaints/<int:complaint_id>/', api_my_complaint_detail, name='api_my_complaint_detail'),
    path('api/mobile/student/dashboard/', api_student_dashboard, name='api_student_dashboard'),
    path('api/mobile/student/bills/', api_student_bills, name='api_student_bills'),
    path('api/mobile/student/routine/', api_student_routine, name='api_student_routine'),
    path('api/mobile/student/academic-work/', api_student_academic_work, name='api_student_academic_work'),
    path('api/mobile/student/results/', api_student_results, name='api_student_results'),
    path('api/mobile/teacher/dashboard/', api_teacher_dashboard, name='api_teacher_dashboard'),
    path('api/mobile/teacher/routine/', api_teacher_routine, name='api_teacher_routine'),
    path('api/mobile/teacher/sessions/', api_teacher_sessions, name='api_teacher_sessions'),
    path('api/mobile/teacher/periods/<int:period_id>/attendance/', api_teacher_attendance_context, name='api_teacher_attendance_context'),
    path('api/mobile/teacher/academic-work/', api_teacher_academic_work, name='api_teacher_academic_work'),
    path('api/mobile/teacher/exams/', api_teacher_exams, name='api_teacher_exams'),
    path('api/mobile/teacher/exams/<int:exam_id>/scope/<int:scope_id>/marks/', api_teacher_exam_marks, name='api_teacher_exam_marks'),
    path('api/mobile/driver/bus/', api_driver_bus_tracking, name='api_driver_bus_tracking'),
    path('api/mobile/student/bus/', api_student_bus_tracking, name='api_student_bus_tracking'),
    path('api/staff/class/<int:class_id>/members/', api_class_members, name='api_class_members'),
    path('api/staff/mark_present/', api_mark_present, name='api_mark_present'),
    path('api-staff-mark-present/', api_mark_present, name='api_staff_mark_present'),
    path('api/library/books/', api_library_books, name='api_library_books'),
    path('api/library/my-issues/', api_my_book_issues, name='api_my_book_issues'),

    # Location
    path('api/staff/locations/', views.api_get_locations, name='api_get_locations'),
    path('api/staff/location_checkin/', views.api_location_checkin, name='api_location_checkin'),

    # Field Visits
    path('api/staff/field_visit/', views.api_field_visit_submit, name='api_field_visit_submit'),

    # Clients
    path('api/staff/clients/', views.api_client_list, name='api_client_list'),
    path('api/staff/clients/followup/', views.api_log_followup, name='api_log_followup'),
    path('api/staff/clients/due/', views.api_clients_due_followup, name='api_clients_due_followup'),

    # Timesheets
    path('timesheets/', views.StaffTimesheetListView.as_view(), name='timesheet_list'),
    path('timesheets/new/', views.StaffTimesheetCreateView.as_view(), name='timesheet_create'),
    path('timesheets/<int:pk>/', views.StaffTimesheetDetailView.as_view(), name='timesheet_detail'),
    path('timesheets/<int:pk>/entry/add/', views.StaffTimesheetEntryAddView.as_view(), name='ts_entry_add'),
    path('timesheets/<int:pk>/entry/<int:entry_pk>/edit/', views.StaffTimesheetEntryEditView.as_view(), name='ts_entry_edit'),
    path('timesheets/<int:pk>/entry/<int:entry_pk>/delete/', views.StaffTimesheetEntryDeleteView.as_view(), name='ts_entry_delete'),
    path('timesheets/<int:pk>/submit/', views.StaffTimesheetSubmitView.as_view(), name='timesheet_submit'),

    # QR
    path('api/staff/qr_codes/', views.api_get_qr_codes, name='api_get_qr_codes'),
    path('api/staff/qr_checkin/', views.api_qr_checkin, name='api_qr_checkin'),

    # WiFi
    path('api/staff/wifi_networks/', views.api_get_wifi_networks, name='api_get_wifi_networks'),
    path('api/staff/wifi_checkin/', views.api_wifi_checkin, name='api_wifi_checkin'),

    # Auto check-in
    path('api/staff/auto_checkin/', views.api_auto_checkin_class, name='api_auto_checkin'),

    # Reports
    path('api/staff/class/<int:class_id>/report/', views.api_attendance_summary, name='api_attendance_summary'),

    # Dynamic feature registry — generic zero-code landing page
    path('features/<slug:feature_key>/', views.StaffDynamicFeatureView.as_view(), name='dynamic_feature'),

    # Academic Management — student-facing
    path('teaching/assignments/', views.TeacherAssignmentListView.as_view(), name='teacher_assignments'),
    path('teaching/assignments/new/', views.TeacherAssignmentCreateView.as_view(), name='teacher_assignment_create'),
    path('teaching/assignments/<int:pk>/', views.TeacherAssignmentDetailView.as_view(), name='teacher_assignment_detail'),
    path('teaching/homework/', views.TeacherHomeworkListView.as_view(), name='teacher_homework'),
    path('teaching/homework/new/', views.TeacherHomeworkCreateView.as_view(), name='teacher_homework_create'),
    path('teaching/homework/<int:pk>/', views.TeacherHomeworkDetailView.as_view(), name='teacher_homework_detail'),
    path('teaching/exams/', views.TeacherExamListView.as_view(), name='teacher_exams'),
    path(
        'teaching/exams/<int:exam_pk>/scope/<int:scope_pk>/marks/',
        views.TeacherExamMarksView.as_view(),
        name='teacher_exam_marks',
    ),

    # Academic Management — student-facing
    path('assignments/', views.StudentAssignmentListView.as_view(), name='student_assignments'),
    path('assignments/<int:pk>/submit/', views.AssignmentSubmitView.as_view(), name='assignment_submit'),
    path('homework/', views.StudentHomeworkListView.as_view(), name='student_homework'),
    path('homework/<int:pk>/mark/', views.mark_homework_status, name='mark_homework_status'),
    path('course-materials/', views.StudentCourseMaterialListView.as_view(), name='student_course_materials'),
    path('course-materials/<int:pk>/track/', views.track_material_access, name='track_material_access'),
    path('teaching-logs/', views.StudentTeachingLogView.as_view(), name='student_teaching_logs'),
    path('subject-attendance/', views.StudentSubjectAttendanceView.as_view(), name='student_subject_attendance'),
    path('routine/', views.StudentRoutineView.as_view(), name='student_routine'),
    path('notifications/', views.NotificationListView.as_view(), name='notifications'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
]
