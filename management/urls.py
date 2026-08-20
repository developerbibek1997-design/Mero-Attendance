from django.urls import path
from .import views
from .import api
app_name = 'management'

urlpatterns = [
    path('account-deletion', views.account_deletion_view, name='account-deletion'),
    path('', views.Homepage.as_view(), name="homepage"),
    path("password_reset", views.password_reset_request, name="password_reset"),
    path('pricing', views.PricingView.as_view(), name="pricing"),
    path('pricing/request-package', views.RequestPackage, name="request_package"),
    path('documentation', views.Documentation.as_view(), name="document"),
    path('download-pullar', views.Pullar.as_view(), name="pullar"),
    path('about-mero-attendance-attendance-system-nepal', views.About.as_view(), name="about"),
    path('contact-us-attendance-system', views.Contact, name="contact"),
    path('privacy-and-policy-mero-attendance', views.Privacy.as_view(), name="privacy"),
    path('terms-and-conditions-mero-attendance', views.Terms.as_view(), name="terms"),
    path('logout', views.logoutUser, name ="logout"),
    
    path('member', api.MemberList.as_view(), name='member_api'),
    path("device", api.DeviceList.as_view(), name ="device"),
    path("classification", api.ClassificationList.as_view(), name ="classification"),
    path('member/<int:pk>', api.MemberDetails.as_view(), name="member_detail"),
    path('organizationlist', api.OraganizationList.as_view(), name = "org_list"),
    path('createAttendance', api.AttendanceRecordAdd.as_view(), name= "attRec"),
    path('members/<int:pk>/', api.MemberDetail.as_view(), name='member-detail'),
    path("askforverification", views.askVerify, name ="askVerify"),
    path("completed-success-sending-report", views.completeLeave, name ="completeLeave"),
    path('leaveReport/<int:id>/sendleavereport', views.LeaveReportView.as_view(), name ="leaveReport"),
    path('book/<str:org_key>/', views.public_book, name='public_book'),
    path('forms/<str:form_uuid>/', views.public_form, name='public_form'),
    path('blog/', views.BlogListView.as_view(), name='blog'),
    path('blog/<slug:slug>/', views.BlogDetailView.as_view(), name='blog_detail'),
    # Sitemap & robots
    path('sitemap.xml', views.SitemapView.as_view(), name='sitemap'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    # SEO landing pages — one view, many slugs
    path('<slug:slug>/', views.SeoLandingView.as_view(), name='seo_landing'),
]