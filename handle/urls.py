
from django.urls import path

from .import rough
from .import views
from .hikvision import hikvision_attendance_event

from .api_mobile import *

app_name = 'handle'

urlpatterns = [
    path('addMember', views.AddMember.as_view(), name="addMember"),
    path('addClassfication', views.AddClassification.as_view(), name="addClassification"),
    path('addDevice', views.AddDevice.as_view(), name="addDevice"),
    path('operations/', views.OperationsCenter.as_view(), name="operations"),
    path('search', views.Search.as_view(), name="search"),
    path('memberReport', views.MemberReport.as_view(), name="memberReport"),
    path('editDevice/<int:id>', views.editDevice, name="editDevice"),
    path('deleteDevice/<int:id>', views.deleteDevice, name ="deleteDevice"),
    path('memberEdit/<int:id>', views.memberEdit, name = "memberEdit"),
    path("deleteMember/<int:id>",views.deleteMember, name ="deleteMember"),
    path('editClassification/<int:id>', views.editClassification, name="editClassification"),
    path('deleteClassification/<int:id>', views.deleteClassification, name="deleteClassification"),
    path('sections-by-classification/', views.sections_by_classification, name="sectionsByClassification"),
    path('changePassword', views.changePassword, name = "changePassword"),

  
    path('api-org/', OrgListCreateAPIView.as_view(), name='org-data'),
    path('api-org/<int:pk>', OrgDetailAPIView.as_view(), name='org-details'),
    path('api-login/', LoginAPIView.as_view(), name='login'),
    path('api-register/', RegisterAPIView.as_view(), name='register'),
    path('api-change-password/', ChangePasswordAPIView.as_view(), name='change-password'),
    path('api-password-reset/', PasswordResetRequestAPIView.as_view(), name='password-reset'),
    path('api-password-reset-confirm/', PasswordResetConfirmAPIView.as_view(), name='password-reset-confirm'),
    
    # Member 
    path('api-members/', MemberListCreateAPIView.as_view(), name='member-list'),
    path('api-members/<int:pk>/', MemberDetailAPIView.as_view(), name='member-detail'),
    
    # Classification
    path('api-classifications/', ClassificationListCreateAPIView.as_view(), name='classification-list'),
    path('api-classifications/<int:pk>/', ClassificationDetailAPIView.as_view(), name='classification-detail'),

    # Branch / Section
    path('api-branches/', BranchListCreateAPIView.as_view(), name='branch-list'),
    path('api-branches/<int:pk>/', BranchDetailAPIView.as_view(), name='branch-detail'),
    path('api-sections/', SectionListCreateAPIView.as_view(), name='section-list'),
    path('api-sections/<int:pk>/', SectionDetailAPIView.as_view(), name='section-detail'),

    # Operations: stock, finance and birthdays
    path('api-stock-categories/', StockCategoryListCreateAPIView.as_view(), name='stock-category-list'),
    path('api-stock-categories/<int:pk>/', StockCategoryDetailAPIView.as_view(), name='stock-category-detail'),
    path('api-stock-items/', StockItemListCreateAPIView.as_view(), name='stock-item-list'),
    path('api-stock-items/<int:pk>/', StockItemDetailAPIView.as_view(), name='stock-item-detail'),
    path('api-stock-movements/', StockMovementListCreateAPIView.as_view(), name='stock-movement-list'),
    path('api-stock-movements/<int:pk>/', StockMovementDetailAPIView.as_view(), name='stock-movement-detail'),
    path('api-transaction-categories/', TransactionCategoryListCreateAPIView.as_view(), name='transaction-category-list'),
    path('api-transaction-categories/<int:pk>/', TransactionCategoryDetailAPIView.as_view(), name='transaction-category-detail'),
    path('api-financial-transactions/', FinancialTransactionListCreateAPIView.as_view(), name='financial-transaction-list'),
    path('api-financial-transactions/<int:pk>/', FinancialTransactionDetailAPIView.as_view(), name='financial-transaction-detail'),
    path('api-birthdays/', BirthdayReportAPIView.as_view(), name='birthday-report'),

    # HR payroll
    path('api-payroll-policy/', PayrollPolicyListCreateAPIView.as_view(), name='payroll-policy-list'),
    path('api-payroll-policy/<int:pk>/', PayrollPolicyDetailAPIView.as_view(), name='payroll-policy-detail'),
    path('api-payroll-adjustments/', PayrollAdjustmentListCreateAPIView.as_view(), name='payroll-adjustment-list'),
    path('api-payroll-adjustments/<int:pk>/', PayrollAdjustmentDetailAPIView.as_view(), name='payroll-adjustment-detail'),
    path('api-probation-reviews/', ProbationReviewListCreateAPIView.as_view(), name='probation-review-list'),
    path('api-probation-reviews/<int:pk>/', ProbationReviewDetailAPIView.as_view(), name='probation-review-detail'),
    path('api-provident-fund-records/', ProvidentFundRecordListAPIView.as_view(), name='provident-fund-record-list'),
    path('api-social-security-fund-records/', SocialSecurityFundRecordListAPIView.as_view(), name='social-security-fund-record-list'),
    
    # Location Based
    path('api-locations/', LocationBasedListCreateAPIView.as_view(), name='location-list'),
    path('api-locations/<int:pk>/', LocationBasedDetailAPIView.as_view(), name='location-detail'),
    
    # Course
  
    path('api-courses/', CourseListCreateAPIView.as_view(), name='course-list'),
    path('api-courses/<int:pk>/', CourseDetailAPIView.as_view(), name='course-detail'),
    
    # Course Attendance
    path('api-course-attendances/', CourseAttendanceListCreateAPIView.as_view(), name='course-attendance-list'),
    path('api-course-attendances/<int:pk>/', CourseAttendanceDetailAPIView.as_view(), name='course-attendance-detail'),

        
    # Classification Attendance
    path('api-classification-attendances/', AttendingClassificationListCreateAPIView.as_view(), name='classification-attendance-list'),
    path('api-classification-attendances/<int:pk>/', AttendingClassificationDetailAPIView.as_view(), name='classification-attendance-detail'),
    
    # Reports
    path('api-reports/attendance/', AttendanceReportAPIView.as_view(), name='attendance-report'),
    path(
        'api/hikvision/<str:org_serial_key>/<str:token>/',
        hikvision_attendance_event,
        name='hikvision_attendance_event',
    ),


    path('api-login/', LoginAPIView.as_view(), name='api_login'),
    
    # Dashboard Data APIs
    path('api-course-attendance/', CourseAttendanceListCreateAPIView.as_view(), name='api_course_attendance'),
    path('api-classification-attendances/', AttendingClassificationListCreateAPIView.as_view(), name='api_classification_attendances'),
    
    # Members & Reports APIs
    path('api-members/', MemberListCreateAPIView.as_view(), name='api_members'),
    path('api-reports/attendance/', AttendanceReportAPIView.as_view(), name='api_reports_attendance'),

    # Action API (If you used the function-based view from earlier)
    path('api-staff-mark-present/', api_mark_present, name='api_staff_mark_present'),

    path('api/leave-types/', api_leave_types, name='api_leave_types'),
    path('api/apply-leave/', api_apply_leave, name='api_apply_leave'),
    path('api/staff/my-leaves/', api_my_leaves, name='api_my_leaves'),
    path('api/staff/payslips/', api_my_payslips, name='api_my_payslips'),
    path('api/staff/wifi-checkin/', api_wifi_checkin, name='api_wifi_checkin'),
    path('api/staff/location_checkin/', api_location_checkin, name='api_location_checkin'),
    path('api/staff/my-attendance-report/', api_my_attendance_report, name='api_my_attendance_report'),
    path('api/staff/undo-attendance/', api_undo_attendance, name='api_undo_attendance'),
    path('api/staff/my-profile/',api_my_profile, name='api_my_profile'),
    path('api/staff/change-password/', api_change_password, name='api_change_password'),
    path('api/auth/forgot-password/', api_forgot_password, name='api_forgot_password'),


    
]
