from django.urls import path
from . import views

app_name = 'agent'

urlpatterns = [
    path('dashboard', views.AgentDashboard.as_view(), name='dashboard'),
    path('organizations', views.AgentOrgList.as_view(), name='org_list'),
    path('organizations/add', views.AgentAddOrg.as_view(), name='add_org'),
    path('organizations/<int:org_id>', views.AgentOrgDetail.as_view(), name='org_detail'),
    path('organizations/<int:org_id>/edit', views.AgentEditOrg.as_view(), name='org_edit'),
    path('billing', views.AgentBilling.as_view(), name='billing'),
    path('commission', views.AgentCommission.as_view(), name='commission'),
    path('reports', views.AgentReports.as_view(), name='reports'),
    path('profile', views.AgentProfileView.as_view(), name='profile'),
]
