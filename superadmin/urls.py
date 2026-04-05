from django.urls import path
from .import views
app_name = 'superadmin'

urlpatterns = [
    path('superadmin', views.Dashboard.as_view(), name ="dashboard"),
    path('searchResult', views.SearchView.as_view(), name ="searchResult"),

    path('orgDetails/<int:id>', views.OrganizationDetail.as_view(), name ="orgDetail"),

    path('all-member-list', views.MemberList.as_view(), name ="memberList"),

    path('settings', views.Settings.as_view(), name ="setting"),

    path('activate/<int:id>', views.activate, name ="activate"),

    path('deactivate/<int:id>', views.deactivate, name ="deactivate"),


    path('addOrganization', views.addOrg.as_view(), name="addOrg"),
    path('deleteOrg/<int:id>', views.deleteOrg, name="deleteOrg"),
    path('editOrg/<int:id>', views.editOrg, name="editOrg"),
    path('addUser', views.addUser.as_view(), name="addUser"),
    path('deleteUser/<int:id>', views.deleteUser, name="deleteUser"),
    path('editUser/<int:id>', views.editUser, name="editUser"),


]
