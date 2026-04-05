from django.urls import path
from .import views
app_name = 'staff'

urlpatterns=[

    path('staffdashboard', views.Dashboard, name="dashboard"),
    path('staff-member-report', views.memReport.as_view(), name="report"),
    path('do-attendance-right-now/<int:id>/present-absent/<str:name>', views.attendanceView, name="attendance"),
    path('mark_present/', views.mark_present, name='mark_present'),
  
]