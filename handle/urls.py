
from django.urls import path
from .import rough
from .import views
app_name = 'handle'

urlpatterns = [
    path('addMember', views.AddMember.as_view(), name="addMember"),
    path('addClassfication', views.AddClassification.as_view(), name="addClassification"),
    path('addDevice', views.AddDevice.as_view(), name="addDevice"),
    path('search', views.Search.as_view(), name="search"),
    path('memberReport', views.MemberReport.as_view(), name="memberReport"),
    path('editDevice/<int:id>', views.editDevice, name="editDevice"),
    path('deleteDevice/<int:id>', views.deleteDevice, name ="deleteDevice"),
    path('memberEdit/<int:id>', views.memberEdit, name = "memberEdit"),
    path("deleteMember/<int:id>",views.deleteMember, name ="deleteMember"),
    path('editClassification/<int:id>', views.editClassification, name="editClassification"),
    path('deleteClassification/<int:id>', views.deleteClassification, name="deleteClassification"),
    path('changePassword', views.changePassword, name = "changePassword"),
]
