from django.contrib import admin
from .models import Superadmin, Schooladmin, Organization, CustomUser, LeaveReport, ContactUs, Pricing, Holiday, Occasion

# Register your models here.
admin.site.register(Superadmin)
admin.site.register(Schooladmin)
admin.site.register(Holiday)
admin.site.register(Occasion)
admin.site.register(Organization)
admin.site.register(CustomUser)
admin.site.register(LeaveReport)
admin.site.register(Pricing)
admin.site.register(ContactUs)