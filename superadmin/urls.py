from django.urls import path
from .import views
app_name = 'superadmin'

urlpatterns = [
    path('superadmin', views.Dashboard.as_view(), name ="dashboard"),
    path('searchResult', views.SearchView.as_view(), name ="searchResult"),

    path('orgDetails/<int:id>', views.OrganizationDetail.as_view(), name ="orgDetail"),

    path('all-member-list', views.MemberList.as_view(), name ="memberList"),

    path('settings', views.Settings.as_view(), name ="setting"),
    path('settings/database-backup/', views.database_backup, name="database_backup"),

    path('activate/<int:id>', views.activate, name ="activate"),

    path('deactivate/<int:id>', views.deactivate, name ="deactivate"),


    path('addOrganization', views.addOrg.as_view(), name="addOrg"),
    path('deleteOrg/<int:id>', views.deleteOrg, name="deleteOrg"),

    path('editOrg/<int:id>', views.editOrg, name="editOrg"),
    path('addUser', views.addUser.as_view(), name="addUser"),
    path('deleteUser/<int:id>', views.deleteUser, name="deleteUser"),
    path('editUser/<int:id>', views.editUser, name="editUser"),
    path('global-holiday/', views.GlobalHolidayView.as_view(), name="globalHoliday"),
    path('broadcast-email/', views.BroadcastNotificationView.as_view(), name="broadcastEmail"),
    path('attendance-report/', views.SuperAttendanceReportView.as_view(), name="attendance_report"),

    # Agent management
    path('agents/', views.AgentListView.as_view(), name="agent_list"),
    path('agents/add', views.AgentAddView.as_view(), name="agent_add"),
    path('agents/<int:agent_id>/', views.AgentDetailView.as_view(), name="agent_detail"),
    path('agents/<int:agent_id>/edit', views.AgentEditView.as_view(), name="agent_edit"),
    path('agents/<int:agent_id>/suspend', views.agent_suspend, name="agent_suspend"),
    path('agents/<int:agent_id>/activate', views.agent_activate, name="agent_activate"),

    # Blog management
    path('blog/', views.BlogListView.as_view(), name="blog_list"),
    path('blog/add/', views.BlogCreateView.as_view(), name="blog_add"),
    path('blog/<int:pk>/edit/', views.BlogEditView.as_view(), name="blog_edit"),
    path('blog/<int:pk>/delete/', views.blog_delete, name="blog_delete"),
    path('blog/<int:pk>/toggle-publish/', views.blog_toggle_publish, name="blog_toggle_publish"),

    path('faqs/', views.FAQListView.as_view(), name="faq_list"),
    path('faqs/add/', views.FAQCreateView.as_view(), name="faq_add"),
    path('faqs/<int:pk>/edit/', views.FAQEditView.as_view(), name="faq_edit"),
    path('faqs/<int:pk>/delete/', views.faq_delete, name="faq_delete"),
    path('faqs/<int:pk>/toggle-active/', views.faq_toggle_active, name="faq_toggle_active"),

    path('contacts/', views.ContactSubmissionListView.as_view(), name="contact_list"),
    path('contacts/<int:pk>/delete/', views.contact_delete, name="contact_delete"),
    path('package-requests/', views.PackageRequestListView.as_view(), name="package_request_list"),
    path('package-requests/<int:pk>/delete/', views.package_request_delete, name="package_request_delete"),

    # Dynamic feature registry
    path('features/', views.FeatureRegistryView.as_view(), name="feature_registry"),
    path('features/org/<int:org_id>/', views.OrgFeatureGrantsView.as_view(), name="org_feature_grants"),
]
