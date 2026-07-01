from django.urls import path
from .import views
app_name = 'schooladmin'

urlpatterns=[
    path('payroll-settings/', views.PayrollSettingsView.as_view(), name='payroll_settings'),
    path('manage-leave-types/', views.ManageLeaveTypesView.as_view(), name='manage_leave_types'),
    path('attendanceReportAll', views.AllRecord.as_view(), name="allRecord"),
    path('admindashboard', views.Dashboard.as_view(), name="dashboard"),
    path('manual-attendance/', views.ManualAttendance.as_view(), name='manual_attendance'),
    # ---------------------------------------------------------
    # 📌 ENTERPRISE HRMS & LEAVE MANAGEMENT
    # ---------------------------------------------------------
    path('log-leave/', views.AdminLogLeaveView.as_view(), name='log_leave'),
    path('manage-leave-types/', views.ManageLeaveTypesView.as_view(), name='manage_leave_types'),
    path('master-leave-report/', views.MasterLeaveReportView.as_view(), name='master_leave_report'),
    
    path('dailyattendancereport', views.DailyReport.as_view(), name="dailyReport"),
    path('gapAttendanceReport', views.GapReport.as_view(), name="gapReport"),
    path('memberGapReport/<int:id>', views.MemberGapReport.as_view(), name="memberGapReport"),
    path('member/<int:pk>/profile/', views.MemberProfileView.as_view(), name='member_profile'),
    path('students/', views.StudentListView.as_view(), name='student_list'),
    path('students/add/', views.StudentAddEditView.as_view(), name='student_add'),
    path('students/<int:pk>/edit/', views.StudentAddEditView.as_view(), name='student_edit'),
    path('students/<int:pk>/profile/', views.StudentProfileView.as_view(), name='student_profile'),
    path('getMember', views.getMember, name = "getMember"),
    path('leaveReportView', views.leaveReportView.as_view(), name ="leaveReportView"),
    path('presentDay', views.PresentToday.as_view(), name ="presentToday"),
    path('AbsentDay', views.AbsentToday.as_view(), name ="absentToday"),
    path('salaryReport/<int:id>', views.salaryReport.as_view(), name ="salaryReport"),
    path('salaryReportAll', views.salaryReportAll.as_view(), name ="salaryReportAll"),
    path('generate-payslip', views.playSlipView, name ="playslip"),
    path('member-generate-payslip/<int:id>', views.paySlipDetailView, name ="play-slip-detail"),
    path('organization-details', views.orgDetail, name = 'orgDetail'),
    path('generate/<int:id>', views.generate, name = 'generate'),
    path('make-member-staff', views.staffMake, name = "staffmake"),
    path('add-holiday', views.addHoliday, name = "addHoliday"),
    path('update-holiday', views.updateHoliday, name = "updateHoliday"),
    path("addOccasion", views.addOccasion, name = 'addOccasion'),
    path("attendance-analytics", views.attendance_analytics, name = 'analytics'),
    path('update-classes-staff/<int:id>', views.updateClass, name = "updateClass"),
    path('accept-reject-leave-report/<int:id>/<str:status>', views.leaveStatus, name = "acceptReject"),
    path('manage-wifi/', views.AdminWifiManageView.as_view(), name='admin_wifi_manage'),
    



    
    path('location/', views.location_list, name='location_list'),
    path('location/add/', views.location_add, name='location_add'),
    path('location/edit/<int:id>/', views.location_edit, name='location_edit'),
    path('location/delete/<int:id>/', views.location_delete, name='location_delete'),

    path('qrcode/', views.qrcode_list, name='qrcode_list'),
    path('qrcode/add/', views.qrcode_add, name='qrcode_add'),
    path('qrcode/edit/<int:id>/', views.qrcode_edit, name='qrcode_edit'),
    path('qrcode/delete/<int:id>/', views.qrcode_delete, name='qrcode_delete'),

    path('autocheckin/', views.auto_checkin_list, name='auto_checkin_list'),
    path('autocheckin/add/', views.auto_checkin_add, name='auto_checkin_add'),
    path('autocheckin/edit/<int:id>/', views.auto_checkin_edit, name='auto_checkin_edit'),
    path('autocheckin/delete/<int:id>/', views.auto_checkin_delete, name='auto_checkin_delete'),

    # Finance
    path('finance/', views.FinanceDashboardView.as_view(), name='finance_dashboard'),
    path('finance/income/', views.IncomeListView.as_view(), name='income_list'),
    path('finance/income/add/', views.AddIncomeView.as_view(), name='add_income'),
    path('finance/income/edit/<int:pk>/', views.EditIncomeView.as_view(), name='edit_income'),
    path('finance/income/delete/<int:pk>/', views.delete_income, name='delete_income'),
    path('finance/expense/', views.ExpenseListView.as_view(), name='expense_list'),
    path('finance/expense/add/', views.AddExpenseView.as_view(), name='add_expense'),
    path('finance/expense/edit/<int:pk>/', views.EditExpenseView.as_view(), name='edit_expense'),
    path('finance/expense/delete/<int:pk>/', views.delete_expense, name='delete_expense'),
    path('finance/categories/', views.FinanceCategoryView.as_view(), name='finance_categories'),

    # Stock
    path('stock/', views.StockDashboardView.as_view(), name='stock_dashboard'),
    path('stock/items/', views.StockItemListView.as_view(), name='stock_items'),
    path('stock/items/add/', views.AddStockItemView.as_view(), name='add_stock_item'),
    path('stock/items/edit/<int:pk>/', views.EditStockItemView.as_view(), name='edit_stock_item'),
    path('stock/items/delete/<int:pk>/', views.delete_stock_item, name='delete_stock_item'),
    path('stock/in/', views.StockInView.as_view(), name='stock_in'),
    path('stock/out/', views.StockOutView.as_view(), name='stock_out'),
    path('stock/movements/', views.StockMovementHistoryView.as_view(), name='stock_movements'),
    path('stock/categories/', views.StockCategoryView.as_view(), name='stock_categories'),

    # Events
    path('events/', views.EventListView.as_view(), name='event_list'),
    path('events/add/', views.AddEventView.as_view(), name='add_event'),
    path('events/<int:pk>/', views.EventDetailView.as_view(), name='event_detail'),
    path('events/<int:pk>/delete/', views.delete_event, name='delete_event'),

    # Courses
    path('courses/', views.CourseListView.as_view(), name='course_list'),
    path('courses/add/', views.AddCourseView.as_view(), name='add_course'),
    path('courses/<int:pk>/delete/', views.delete_course, name='delete_course'),
    path('courses/attendance/', views.CourseAttendanceView.as_view(), name='course_attendance'),

    # Study Gap
    path('study-gap/', views.StudyGapListView.as_view(), name='study_gap_list'),
    path('study-gap/<int:pk>/update-status/', views.update_gap_status, name='update_gap_status'),

    # Results
    path('results/subjects/', views.SubjectListView.as_view(), name='subject_list'),
    path('results/exams/', views.ExamTermListView.as_view(), name='exam_terms'),
    path('results/entry/', views.ResultEntryView.as_view(), name='result_entry'),
    path('results/report/', views.ResultReportView.as_view(), name='result_report'),
    path('results/exams/<int:pk>/publish-summary/', views.ResultPublishSummaryView.as_view(), name='result_publish_summary'),
    path('results/marksheet/<int:exam_pk>/<int:member_pk>/', views.MarksheetView.as_view(), name='marksheet'),
    path('results/bulk-send/', views.BulkResultSendView.as_view(), name='bulk_result_send'),

    # Complaints
    path('complaints/', views.ComplaintListView.as_view(), name='complaint_list'),
    path('complaints/file/', views.FileComplaintView.as_view(), name='file_complaint'),
    path('complaints/<int:pk>/', views.ComplaintDetailView.as_view(), name='complaint_detail'),

    # HRMS Extended
    path('hrms/resignations/', views.ResignationListView.as_view(), name='resignation_list'),
    path('hrms/resignations/add/', views.AddResignationView.as_view(), name='add_resignation'),
    path('hrms/resignations/<int:pk>/update/', views.update_resignation_status, name='update_resignation'),
    path('hrms/documents/', views.StaffDocumentListView.as_view(), name='document_list'),
    path('hrms/documents/upload/', views.UploadStaffDocumentView.as_view(), name='upload_document'),
    path('hrms/documents/<int:pk>/delete/', views.delete_document, name='delete_document'),

    # Branches
    path('branches/', views.BranchListView.as_view(), name='branch_list'),

    # Privilege Management
    path('hrms/privilege/', views.PrivilegeManageView.as_view(), name='privilege_manage'),
    # Granular Staff Permissions
    path('hrms/staff-permissions/', views.StaffPermissionsView.as_view(), name='staff_permissions'),
    path('hrms/staff-permissions/<int:member_id>/', views.EditStaffPermissionsView.as_view(), name='edit_staff_permissions'),
    # Organization Feature Settings
    path('org-features/', views.OrgFeaturesView.as_view(), name='org_features'),

    # Absence Correction
    path('attendance/absence-correction/', views.AbsenceCorrectionView.as_view(), name='absence_correction'),

    # Billing
    path('billing/', views.BillListView.as_view(), name='bill_list'),
    path('billing/create/', views.CreateBillView.as_view(), name='create_bill'),
    path('billing/bulk-generate/', views.BulkBillGenerateView.as_view(), name='bulk_bill_generate'),
    path('billing/bulk-send/', views.BulkBillSendView.as_view(), name='bulk_bill_send'),
    path('billing/<int:pk>/', views.BillDetailView.as_view(), name='bill_detail'),
    path('billing/<int:pk>/delete/', views.delete_bill, name='delete_bill'),

    # School structure hub
    path('classifications/<int:pk>/', views.ClassificationDetailView.as_view(), name='classification_detail'),

    # Bulk Payslip
    path('payroll/bulk/', views.BulkPayslipView.as_view(), name='bulk_payslip'),

    # Advance Salary
    path('payroll/advances/', views.AdvanceSalaryView.as_view(), name='advance_salary'),

    # PaySlip finalize/status change
    path('payroll/payslip/<int:pk>/finalize/', views.finalize_payslip, name='finalize_payslip'),

    # Leave with email override
    path('leave/status-email/<int:id>/<str:status>/', views.leave_status_with_email, name='leave_status_email'),

    # Resignation with email
    path('hrms/resignations/<int:pk>/update-email/', views.update_resignation_with_email, name='update_resignation_email'),

    # Exam publish with email
    path('results/exams/<int:pk>/publish/', views.publish_exam_with_email, name='publish_exam'),

    # Complaint detail with email (override)
    path('complaints/<int:pk>/manage/', views.ComplaintDetailViewWithEmail.as_view(), name='complaint_detail_manage'),

    # Task Management
    path('tasks/', views.TaskDashboardView.as_view(), name='task_dashboard'),
    path('tasks/list/', views.TaskListView.as_view(), name='task_list'),
    path('tasks/create/', views.CreateTaskView.as_view(), name='create_task'),
    path('tasks/<int:pk>/', views.TaskDetailAdminView.as_view(), name='task_detail'),
    path('tasks/report/', views.TaskReportView.as_view(), name='task_report'),

    # ── Export Hub ────────────────────────────────────────────────────────────
    path('export/', views.ExportHubView.as_view(), name='export_hub'),
    path('export/attendance/', views.export_attendance, name='export_attendance'),
    path('export/payslips/', views.export_payslips, name='export_payslips'),
    path('export/stock/', views.export_stock, name='export_stock'),
    path('export/finance/', views.export_finance, name='export_finance'),
    path('export/leave/', views.export_leave, name='export_leave'),
    path('export/members/', views.export_members, name='export_members'),
    path('export/tasks/', views.export_tasks, name='export_tasks'),

    # ── Calendar ──────────────────────────────────────────────────────────────
    path('calendar/', views.CalendarView.as_view(), name='calendar'),
    path('calendar/api/events/', views.api_calendar_events, name='api_calendar_events'),
    path('calendar/api/add/', views.api_calendar_add, name='api_calendar_add'),
    path('calendar/api/delete/<str:item_type>/<int:pk>/', views.api_calendar_delete, name='api_calendar_delete'),

    # ── Appointments ──────────────────────────────────────────────────────────
    path('appointments/', views.AppointmentTypeView.as_view(), name='appointments'),

    # ── Form Builder ──────────────────────────────────────────────────────────
    path('forms/', views.FormBuilderView.as_view(), name='form_builder'),
    path('forms/new/', views.FormBuilderEditView.as_view(), name='form_builder_new'),
    path('forms/<int:pk>/edit/', views.FormBuilderEditView.as_view(), name='form_builder_edit'),
    path('forms/<int:pk>/submissions/', views.FormSubmissionsView.as_view(), name='form_submissions'),
]
