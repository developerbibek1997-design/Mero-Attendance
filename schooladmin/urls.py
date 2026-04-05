from django.urls import path
from .import views
app_name = 'schooladmin'

urlpatterns=[

    path('attendanceReportAll', views.AllRecord.as_view(), name="allRecord"),
    path('admindashboard', views.Dashboard.as_view(), name="dashboard"),
    path('dailyattendancereport', views.DailyReport.as_view(), name="dailyReport"),
    path('gapAttendanceReport', views.GapReport.as_view(), name="gapReport"),
    path('memberGapReport/<int:id>', views.MemberGapReport.as_view(), name="memberGapReport"),
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
    
]