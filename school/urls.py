"""school URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include,re_path
from django.contrib.auth import views as auth_views 
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static
from school import pwa as pwa_views
from handle import adms as adms_views

urlpatterns = [
    # ZKTeco ADMS/Push endpoints stay at the conventional site-root paths.
    # Both slash forms are explicit because embedded devices may not follow
    # Django redirects when POSTing attendance batches.
    path('iclock/cdata', adms_views.adms_cdata, name='adms_cdata'),
    path('iclock/cdata/', adms_views.adms_cdata),
    path('iclock/getrequest', adms_views.adms_getrequest, name='adms_getrequest'),
    path('iclock/getrequest/', adms_views.adms_getrequest),
    path('iclock/devicecmd', adms_views.adms_devicecmd, name='adms_devicecmd'),
    path('iclock/devicecmd/', adms_views.adms_devicecmd),

    path('admin/', admin.site.urls),

    # ── PWA ───────────────────────────────────────────────────────────────
    # Declared BEFORE management.urls: that URLconf ends in a catch-all
    # `<slug:slug>/` SEO-landing route which would otherwise swallow /offline/.
    # service-worker.js must also stay at the site root — a worker's scope is
    # its own directory, so serving it from /static/ would limit it to /static/*.
    path('manifest.webmanifest', pwa_views.manifest, name='pwa_manifest'),
    path('service-worker.js', pwa_views.service_worker, name='pwa_service_worker'),
    path('offline/', pwa_views.offline, name='pwa_offline'),

    path('',include('management.urls', namespace='management')),
    path('handle/', include('handle.urls', namespace='handle')),
    path('schooladmin/', include('schooladmin.urls', namespace='schooladmin')),
    path('superadmin/', include('superadmin.urls', namespace="superadmin")),
    path('staff/', include('staff.urls', namespace="staff")),
    path('agent/', include('agent.urls', namespace='agent')),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='password/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name="password/password_reset_confirm.html"), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='password/password_reset_complete.html'), name='password_reset_complete'),    
    re_path(r'^media/(?P<path>.*)$', serve,{'document_root': settings.MEDIA_ROOT}), 
    re_path(r'^static/(?P<path>.*)$', serve,{'document_root': settings.STATIC_ROOT}), 
    
]+static(settings.MEDIA_URL, document_root = settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns+=static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'school.views.custom_404'
handler500 = 'school.views.custom_500'

