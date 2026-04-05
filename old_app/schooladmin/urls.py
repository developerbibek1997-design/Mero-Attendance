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
    path('update-classes-staff/<int:id>', views.updateClass, name = "updateClass"),
    path('accept-reject-leave-report/<int:id>/<str:status>', views.leaveStatus, name = "acceptReject")
    
]