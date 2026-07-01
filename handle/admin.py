from django.contrib import admin
from .models import (
    AttendanceGap,
    AttendanceRecord,
    AttendingClassification,
    Branch,
    Classification,
    Course,
    CourseAttendance,
    Device,
    Bill,
    BillItem,
    BillSendLog,
    FinancialTransaction,
    ExamTerm,
    PaySlip,
    PayrollAdjustment,
    PayrollPolicy,
    ProvidentFundRecord,
    ProbationReview,
    Section,
    SocialSecurityFundRecord,
    Staff,
    Subject,
    ResultRecord,
    ResultSendLog,
    StockCategory,
    StockItem,
    StockMovement,
    TransactionCategory,
    member,
)

# अरू मोडलहरूलाई साधारण रूपमै दर्ता गर्ने
admin.site.register(Classification)
admin.site.register(Branch)
admin.site.register(Section)
admin.site.register(Course)
admin.site.register(CourseAttendance)
admin.site.register(AttendanceGap)
admin.site.register(StockCategory)
admin.site.register(StockItem)
admin.site.register(StockMovement)
admin.site.register(TransactionCategory)
admin.site.register(FinancialTransaction)
admin.site.register(PayrollPolicy)
admin.site.register(PayrollAdjustment)
admin.site.register(ProvidentFundRecord)
admin.site.register(SocialSecurityFundRecord)
admin.site.register(ProbationReview)
admin.site.register(Device)
admin.site.register(PaySlip)
admin.site.register(Staff)
admin.site.register(AttendingClassification)
admin.site.register(Subject)
admin.site.register(ExamTerm)
admin.site.register(ResultRecord)
admin.site.register(Bill)
admin.site.register(BillItem)
admin.site.register(BillSendLog)
admin.site.register(ResultSendLog)

# --- Attendance Record को लागि Custom Admin ---
class AttendanceRecordAdmin(admin.ModelAdmin):
    # एड्मिन प्यानलको लिस्टमा कुन-कुन कोलम देखाउने?
    list_display = ('mem', 'org', 'scanned_time')
    
    # दायाँपट्टि कुन-कुन फिल्डबाट फिल्टर गर्ने?
    # 'org' ले अर्गनाइजेसन अनुसार फिल्टर गर्न दिन्छ
    # 'scanned_time' ले आजको, यो हप्ताको, वा यो महिनाको भनेर फिल्टर गर्न दिन्छ
    list_filter = ('org', 'scanned_time')
    
    # माथि सर्च बक्समा के टाइप गरेर खोज्ने?
    # 'mem__name' ले member मोडलभित्र गएर name फिल्डबाट सर्च गर्छ
    search_fields = ('mem__name',)

# एड्मिन दर्ता गर्दा यो नयाँ क्लास पनि सँगै पठाउने
admin.site.register(AttendanceRecord, AttendanceRecordAdmin)


# --- Member को लागि पनि Custom Admin (तपाईँलाई पछि काम लाग्न सक्छ) ---
class MemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'org', 'branch', 'classification', 'section', 'phone', 'date_of_birth')
    list_filter = ('org', 'branch', 'classification', 'section')
    search_fields = ('name', 'phone', 'card')

admin.site.register(member, MemberAdmin)
