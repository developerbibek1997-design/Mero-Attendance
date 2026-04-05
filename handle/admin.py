from django.contrib import admin
from .models import member, Classification, AttendanceRecord, Device, PaySlip, Staff, AttendingClassification
# Register your models here.
admin.site.register(member)
admin.site.register(Classification)
admin.site.register(AttendanceRecord)
admin.site.register(Device)
admin.site.register(PaySlip)
admin.site.register(Staff)
admin.site.register(AttendingClassification)
