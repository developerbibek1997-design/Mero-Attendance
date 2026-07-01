from django.urls import path
from . import views
from .api import api_staff_classes, api_class_members, api_mark_present

app_name = 'staff'

urlpatterns = [

    # Main Dashboard
    path('staffdashboard', views.Dashboard, name="dashboard"),

    # Attendance
    path('staff-member-report', views.memReport.as_view(), name="report"),
    path('do-attendance-right-now/<int:id>/present-absent/<str:name>', views.attendanceView, name="attendance"),
    path('mark_present/', views.mark_present, name='mark_present'),
    path('my-attendance/', views.MyAttendanceReportView.as_view(), name='my_attendance'),
    path('my-report/', views.MyAttendanceReportView.as_view(), name="my_report"),

    # Leave
    path('apply-leave/', views.StaffLeaveView.as_view(), name='apply_leave'),

    # Check-in methods
    path('location-checkin/', views.StaffLocationCheckinView.as_view(), name='location_checkin'),
    path('wifi-checkin/', views.StaffWifiCheckinView.as_view(), name='wifi_checkin'),

    # Payslips
    path('my-payslips/', views.MyPayslipsView.as_view(), name='my_payslips'),

    # Student portal
    path('my-bills/', views.StudentBillsView.as_view(), name='student_bills'),
    path('my-results/', views.StudentResultsView.as_view(), name='student_results'),
    path('my-gaps/', views.StudentGapsView.as_view(), name='student_gaps'),
    path('my-complaint/', views.StudentComplaintView.as_view(), name='student_complaint'),

    # Teaching log (staff)
    path('teaching-log/', views.TeachingLogView.as_view(), name='teaching_log'),

    # Task Management
    path('tasks/', views.MyTasksView.as_view(), name='my_tasks'),
    path('tasks/<int:pk>/update/', views.UpdateTaskStatusView.as_view(), name='update_task_status'),

    # Resignation
    path('my-resignation/', views.StaffResignationView.as_view(), name='my_resignation'),

    # --- APIs ---
    # Attendance APIs
    path('api/staff/classes/', api_staff_classes, name='api_staff_classes'),
    path('api/staff/class/<int:class_id>/members/', api_class_members, name='api_class_members'),
    path('api/staff/mark_present/', api_mark_present, name='api_mark_present'),
    path('api-staff-mark-present/', api_mark_present, name='api_staff_mark_present'),

    # Location
    path('api/staff/locations/', views.api_get_locations, name='api_get_locations'),
    path('api/staff/location_checkin/', views.api_location_checkin, name='api_location_checkin'),

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
]
