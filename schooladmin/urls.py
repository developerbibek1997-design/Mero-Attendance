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
    path('monthly-report/', views.MonthlyAttendanceReportView.as_view(), name="monthly_report"),
    path('monthly-report/calendar/<int:member_id>/', views.MemberCalendarDataView.as_view(), name="member_calendar_data"),
    path('monthly-report/day-action/', views.DayQuickActionView.as_view(), name="day_quick_action"),
    path('export-present-attendance/', views.export_present_attendance, name='export_present_attendance'),
    path('gapAttendanceReport', views.GapReport.as_view(), name="gapReport"),
    path('memberGapReport/<int:id>', views.MemberGapReport.as_view(), name="memberGapReport"),
    path('member/<int:pk>/profile/', views.MemberProfileView.as_view(), name='member_profile'),
    path('member/<int:pk>/history/', views.MemberHistoryView.as_view(), name='member_history'),
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
    path("add-org-shift-override", views.addOrgShiftOverride, name = 'addOrgShiftOverride'),
    path("org-shift-override/<int:pk>/delete", views.deleteOrgShiftOverride, name = 'deleteOrgShiftOverride'),
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

    # Suppliers / Purchases / Sales (extends Stock)
    path('suppliers/', views.SupplierListView.as_view(), name='supplier_list'),
    path('suppliers/add/', views.AddSupplierView.as_view(), name='add_supplier'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier_detail'),
    path('suppliers/<int:pk>/edit/', views.EditSupplierView.as_view(), name='edit_supplier'),
    path('suppliers/<int:pk>/delete/', views.delete_supplier, name='delete_supplier'),
    path('suppliers/from-client/<int:pk>/', views.ConvertClientToSupplierView.as_view(), name='convert_client_to_supplier'),
    path('purchases/', views.PurchaseListView.as_view(), name='purchase_list'),
    path('purchases/add/', views.AddPurchaseView.as_view(), name='add_purchase'),
    path('purchases/<int:pk>/', views.PurchaseDetailView.as_view(), name='purchase_detail'),
    path('purchases/<int:pk>/receive/', views.receive_purchase, name='receive_purchase'),
    path('suppliers/<int:pk>/documents/add/', views.add_supplier_document, name='add_supplier_document'),
    path('suppliers/<int:pk>/payments/add/', views.add_supplier_payment, name='add_supplier_payment'),
    path('purchase-returns/', views.PurchaseReturnListView.as_view(), name='purchase_return_list'),
    path('purchases/<int:purchase_pk>/return/', views.AddPurchaseReturnView.as_view(), name='add_purchase_return'),
    path('purchase-returns/<int:pk>/', views.PurchaseReturnDetailView.as_view(), name='purchase_return_detail'),
    path('purchase-returns/<int:pk>/complete/', views.complete_purchase_return, name='complete_purchase_return'),
    path('sales/', views.SaleListView.as_view(), name='sale_list'),
    path('sales/add/', views.AddSaleView.as_view(), name='add_sale'),
    path('sales/<int:pk>/', views.SaleDetailView.as_view(), name='sale_detail'),
    path('sales/<int:pk>/complete/', views.complete_sale, name='complete_sale'),
    path('sales/<int:pk>/payments/add/', views.add_sale_payment, name='add_sale_payment'),
    path('sales-returns/', views.SalesReturnListView.as_view(), name='sales_return_list'),
    path('sales/<int:sale_pk>/return/', views.AddSalesReturnView.as_view(), name='add_sales_return'),
    path('sales-returns/<int:pk>/', views.SalesReturnDetailView.as_view(), name='sales_return_detail'),
    path('sales-returns/<int:pk>/complete/', views.complete_sales_return, name='complete_sales_return'),
    path('assets/', views.AssetPurchaseListView.as_view(), name='asset_list'),
    path('assets/add/', views.AddAssetPurchaseView.as_view(), name='add_asset'),
    path('assets/<int:pk>/', views.AssetPurchaseDetailView.as_view(), name='asset_detail'),
    path('stock/adjustment/', views.StockAdjustmentView.as_view(), name='stock_adjustment'),

    # Library
    path('library/', views.LibraryDashboardView.as_view(), name='library_dashboard'),
    path('library/books/', views.BookListView.as_view(), name='library_books'),
    path('library/books/add/', views.AddBookView.as_view(), name='add_book'),
    path('library/books/edit/<int:pk>/', views.EditBookView.as_view(), name='edit_book'),
    path('library/books/delete/<int:pk>/', views.delete_book, name='delete_book'),
    path('library/issue/', views.IssueBookView.as_view(), name='library_issue'),
    path('library/issues/', views.BookIssueHistoryView.as_view(), name='library_issues'),
    path('library/issues/<int:pk>/return/', views.ReturnBookView.as_view(), name='library_return'),
    path('library/categories/', views.LibraryCategoryView.as_view(), name='library_categories'),
    path('library/authors/', views.LibraryAuthorView.as_view(), name='library_authors'),
    path('library/publishers/', views.LibraryPublisherView.as_view(), name='library_publishers'),
    path('library/racks-shelves/', views.LibraryRackShelfView.as_view(), name='library_racks_shelves'),
    path('library/settings/', views.LibrarySettingsView.as_view(), name='library_settings'),

    # Accounting
    path('accounting/', views.AccountingDashboardView.as_view(), name='accounting_dashboard'),
    path('accounting/accounts/', views.ChartOfAccountsView.as_view(), name='accounting_accounts'),
    path('accounting/accounts/add/', views.AddAccountView.as_view(), name='add_account'),
    path('accounting/accounts/edit/<int:pk>/', views.EditAccountView.as_view(), name='edit_account'),
    path('accounting/accounts/delete/<int:pk>/', views.delete_account, name='delete_account'),
    path('accounting/journals/', views.JournalEntryListView.as_view(), name='journal_list'),
    path('accounting/journals/add/', views.CreateJournalEntryView.as_view(), name='add_journal'),
    path('accounting/journals/<int:pk>/', views.JournalEntryDetailView.as_view(), name='journal_detail'),
    path('accounting/journals/<int:pk>/edit/', views.EditJournalEntryView.as_view(), name='edit_journal'),
    path('accounting/journals/<int:pk>/submit/', views.submit_journal_entry, name='submit_journal'),
    path('accounting/journals/<int:pk>/approve/', views.approve_journal_entry_view, name='approve_journal'),
    path('accounting/journals/<int:pk>/reject/', views.reject_journal_entry_view, name='reject_journal'),
    path('accounting/ledger/', views.GeneralLedgerView.as_view(), name='general_ledger'),
    path('accounting/reports/trial-balance/', views.TrialBalanceView.as_view(), name='trial_balance'),
    path('accounting/reports/profit-loss/', views.ProfitAndLossView.as_view(), name='profit_and_loss'),
    path('accounting/reports/balance-sheet/', views.BalanceSheetView.as_view(), name='balance_sheet'),

    # Academic Management
    path('academic/years/', views.AcademicYearListView.as_view(), name='academic_years'),
    path('academic/faculties/', views.FacultyListView.as_view(), name='faculty_list'),
    path('academic/semesters/', views.SemesterListView.as_view(), name='semester_list'),
    path('academic/courses/<int:pk>/teachers/', views.CourseTeachersView.as_view(), name='course_teachers'),
    path('academic/courses/<int:pk>/enrollments/', views.CourseEnrollmentsView.as_view(), name='course_enrollments'),
    path('academic/subjects/<int:pk>/teachers/', views.SubjectTeachersView.as_view(), name='subject_teachers'),
    path('academic/assignments/', views.AssignmentListView.as_view(), name='assignment_list'),
    path('academic/assignments/add/', views.AddAssignmentView.as_view(), name='add_assignment'),
    path('academic/assignments/<int:pk>/', views.AssignmentDetailView.as_view(), name='assignment_detail'),
    path('academic/assignments/<int:pk>/edit/', views.EditAssignmentView.as_view(), name='edit_assignment'),
    path('academic/assignments/<int:pk>/delete/', views.delete_assignment, name='delete_assignment'),
    path('academic/homework/', views.HomeworkListView.as_view(), name='homework_list'),
    path('academic/homework/add/', views.AddHomeworkView.as_view(), name='add_homework'),
    path('academic/homework/<int:pk>/', views.HomeworkDetailView.as_view(), name='homework_detail'),
    path('academic/homework/<int:pk>/edit/', views.EditHomeworkView.as_view(), name='edit_homework'),
    path('academic/homework/<int:pk>/delete/', views.delete_homework, name='delete_homework'),
    path('academic/materials/', views.CourseMaterialListView.as_view(), name='course_material_list'),
    path('academic/materials/add/', views.AddCourseMaterialView.as_view(), name='add_course_material'),
    path('academic/materials/<int:pk>/edit/', views.EditCourseMaterialView.as_view(), name='edit_course_material'),
    path('academic/materials/<int:pk>/delete/', views.delete_course_material, name='delete_course_material'),
    path('academic/teaching-logs/', views.TeachingLogListView.as_view(), name='teaching_log_list'),
    path('academic/teaching-logs/<int:pk>/', views.TeachingLogDetailView.as_view(), name='teaching_log_detail'),
    path('academic/teaching-logs/<int:pk>/approve/', views.approve_teaching_log, name='approve_teaching_log'),
    path('academic/teaching-logs/<int:pk>/reject/', views.reject_teaching_log, name='reject_teaching_log'),
    path('academic/my-teaching-logs/', views.TeacherTeachingLogListView.as_view(), name='my_teaching_logs'),
    path('academic/my-teaching-logs/add/', views.AddTeachingLogView.as_view(), name='add_teaching_log'),
    path('academic/subject-attendance-report/', views.SubjectAttendanceReportView.as_view(), name='subject_attendance_report'),
    path('academic/routine/', views.RoutineListView.as_view(), name='routine_grid'),
    path('academic/routine/add/', views.AddRoutinePeriodView.as_view(), name='add_routine_period'),
    path('academic/routine/<int:pk>/edit/', views.EditRoutinePeriodView.as_view(), name='edit_routine_period'),
    path('academic/routine/<int:pk>/delete/', views.delete_routine_period, name='delete_routine_period'),
    path('academic/my-routine/', views.TeacherRoutineView.as_view(), name='teacher_routine'),

    # Events
    path('events/', views.EventListView.as_view(), name='event_list'),
    path('events/add/', views.AddEventView.as_view(), name='add_event'),
    path('events/<int:pk>/', views.EventDetailView.as_view(), name='event_detail'),
    path('events/<int:pk>/delete/', views.delete_event, name='delete_event'),

    # Courses
    path('courses/', views.CourseListView.as_view(), name='course_list'),
    path('courses/add/', views.AddCourseView.as_view(), name='add_course'),
    path('courses/subjects/', views.SubjectListView.as_view(), name='subject_list'),
    path('courses/<int:pk>/delete/', views.delete_course, name='delete_course'),
    path('courses/attendance/', views.CourseAttendanceView.as_view(), name='course_attendance'),

    # Study Gap
    path('study-gap/', views.StudyGapListView.as_view(), name='study_gap_list'),
    path('study-gap/<int:pk>/update-status/', views.update_gap_status, name='update_gap_status'),

    # Results
    path('results/subjects/', views.SubjectListView.as_view(), name='legacy_subject_list'),
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

    # Roles & Permissions (unified: privilege preset + granular StaffPermission flags)
    path('roles-permissions/', views.RolesPermissionsListView.as_view(), name='roles_permissions_list'),
    path('roles-permissions/<int:member_id>/', views.RolesPermissionsEditView.as_view(), name='roles_permissions_edit'),

    path('features/<slug:feature_key>/', views.DynamicFeatureView.as_view(), name='dynamic_feature'),
    # Organization Feature Settings
    path('org-features/', views.OrgFeaturesView.as_view(), name='org_features'),

    # Absence Correction
    path('attendance/absence-correction/', views.AbsenceCorrectionView.as_view(), name='absence_correction'),

    # Dynamic QR Attendance
    path('qr-attendance/', views.QRAttendancePageView.as_view(), name='qr_attendance'),
    path('qr-attendance/generate/', views.QRGenerateView.as_view(), name='qr_generate'),
    path('qr-attendance/permanent/generate/', views.QRPermanentGenerateView.as_view(), name='qr_permanent_generate'),
    path('qr-attendance/permanent/<int:session_id>/print/', views.QRPermanentPrintView.as_view(), name='qr_permanent_print'),
    path('transport/', views.TransportManagementView.as_view(), name='transport_dashboard'),
    path('qr-attendance/session/<int:session_id>/status/', views.QRSessionStatusView.as_view(), name='qr_session_status'),
    path('qr-attendance/session/<int:session_id>/close/', views.QRCloseSessionView.as_view(), name='qr_session_close'),

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

    # Payslip List
    path('payroll/payslips/', views.PayslipListView.as_view(), name='payslip_list'),

    # Advance Salary
    path('payroll/advances/', views.AdvanceSalaryView.as_view(), name='advance_salary'),

    # PaySlip finalize/status change
    path('payroll/payslip/<int:pk>/finalize/', views.finalize_payslip, name='finalize_payslip'),
    path('payroll/payslip/<int:pk>/', views.paySlipViewDetail, name='payslip_detail'),

    # ID Card generation
    path('id-card/settings/', views.IDCardSettingsView.as_view(), name='idcard_settings'),
    path('id-card/generate/', views.IDCardGenerateView.as_view(), name='idcard_generate'),
    path('certificates/settings/', views.CertificateSettingsView.as_view(), name='certificate_settings'),
    path('certificates/generate/', views.CertificateGenerateView.as_view(), name='certificate_generate'),

    # Email delivery log + resend
    path('email-logs/', views.EmailLogListView.as_view(), name='email_logs'),

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

    # Field Visits
    path('field-visits/', views.FieldVisitListView.as_view(), name='field_visit_list'),
    path('field-visits/manual-add/', views.FieldVisitManualAddView.as_view(), name='field_visit_manual_add'),
    path('field-visits/<int:pk>/', views.FieldVisitDetailView.as_view(), name='field_visit_detail'),

    # Clients
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('clients/create/', views.ClientCreateView.as_view(), name='create_client'),
    path('clients/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/due/', views.ClientFollowUpDueListView.as_view(), name='client_followup_due'),
    path('clients/billing-reminders/', views.BillingReminderView.as_view(), name='billing_reminders'),

    # ── Export Hub ────────────────────────────────────────────────────────────
    path('export/', views.ExportHubView.as_view(), name='export_hub'),
    path('export/attendance/', views.export_attendance, name='export_attendance'),
    path('export/payslips/', views.export_payslips, name='export_payslips'),
    path('export/stock/', views.export_stock, name='export_stock'),
    path('export/library/', views.export_library, name='export_library'),
    path('export/accounting/', views.export_accounting, name='export_accounting'),
    path('export/academic/', views.export_academic, name='export_academic'),
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

    # ── Timesheets ────────────────────────────────────────────────────────────
    path('timesheets/', views.TimesheetAdminListView.as_view(), name='timesheet_list'),
    path('timesheets/<int:pk>/', views.TimesheetAdminDetailView.as_view(), name='timesheet_detail'),
    path('timesheets/<int:pk>/approve/', views.TimesheetAdminApproveView.as_view(), name='timesheet_approve'),
    path('timesheets/<int:pk>/reject/', views.TimesheetAdminRejectView.as_view(), name='timesheet_reject'),

    # ── Shift Management ──────────────────────────────────────────────────────
    path('shifts/', views.ShiftListView.as_view(), name='shift_list'),
    path('shifts/new/', views.ShiftFormView.as_view(), name='shift_new'),
    path('shifts/<int:pk>/edit/', views.ShiftFormView.as_view(), name='shift_edit'),
    path('shifts/<int:pk>/delete/', views.ShiftDeleteView.as_view(), name='shift_delete'),
    path('shifts/assign/', views.ShiftAssignView.as_view(), name='shift_assign'),
    path('shifts/week/<int:member_id>/', views.ShiftMemberWeekView.as_view(), name='shift_week'),
    path('shifts/week/<int:member_id>/override/add/', views.ShiftOverrideAddView.as_view(), name='shift_override_add'),
    path('shifts/override/<int:pk>/delete/', views.ShiftOverrideDeleteView.as_view(), name='shift_override_delete'),
    path('shifts/report/', views.ShiftReportView.as_view(), name='shift_report'),
    path('shifts/duty-roster/', views.DutyRosterView.as_view(), name='duty_roster'),
    path('shifts/duty-roster/<int:pk>/cancel/', views.DutyRosterCancelView.as_view(), name='duty_roster_cancel'),
    path('shifts/duty-roster/save-week/', views.WeeklyDutyRosterSaveView.as_view(), name='duty_roster_save_week'),
    path('shifts/duty-roster/duty-types/', views.DutyTypeManageView.as_view(), name='duty_type_manage'),

    # ── Facial Recognition Attendance ─────────────────────────────────────────
    path('face/', views.FaceEnrollListView.as_view(), name='face_enroll_list'),
    path('face/enroll/<int:member_id>/', views.FaceEnrollView.as_view(), name='face_enroll'),
    path('face/data/', views.FaceEnrolledDataView.as_view(), name='face_data'),
    path('face/attendance/', views.FaceAttendanceView.as_view(), name='face_attendance'),

    # ── Live Location Tracking ────────────────────────────────────────────────
    path('live-tracking/', views.LiveTrackingView.as_view(), name='live_tracking'),
    path('live-tracking/data/', views.LiveTrackingDataView.as_view(), name='live_tracking_data'),
    path('live-tracking/<int:member_id>/', views.LiveTrackingDetailView.as_view(), name='live_tracking_detail'),
    path('live-tracking/<int:member_id>/mark-attendance/', views.LiveTrackingAttendanceView.as_view(), name='live_tracking_mark_attendance'),

    # ── Form Builder ──────────────────────────────────────────────────────────
    path('forms/', views.FormBuilderView.as_view(), name='form_builder'),
    path('forms/new/', views.FormBuilderEditView.as_view(), name='form_builder_new'),
    path('forms/<int:pk>/edit/', views.FormBuilderEditView.as_view(), name='form_builder_edit'),
    path('forms/<int:pk>/submissions/', views.FormSubmissionsView.as_view(), name='form_submissions'),

    # ── Notice Board ──────────────────────────────────────────────────────────
    path('notices/', views.NoticeListView.as_view(), name='notice_list'),
    path('notices/new/', views.NoticeCreateView.as_view(), name='notice_create'),
    path('notices/<int:pk>/', views.NoticeDetailView.as_view(), name='notice_detail'),
    path('notices/<int:pk>/edit/', views.NoticeEditView.as_view(), name='notice_edit'),
    path('notices/<int:pk>/delete/', views.delete_notice, name='notice_delete'),
]
