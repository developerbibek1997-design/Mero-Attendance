from django.contrib import admin
from django.db.models import Q
from .models import WifiBased , Superadmin, Schooladmin, Organization, CustomUser, LeaveReport, ContactUs, FeaturePrice, Pricing, Holiday, Occasion

# Register your models here.
admin.site.register(Superadmin)
admin.site.register(Schooladmin)
admin.site.register(Holiday)
admin.site.register(Occasion)
admin.site.register(Organization)
admin.site.register(LeaveReport)
admin.site.register(Pricing)
admin.site.register(FeaturePrice)
admin.site.register(ContactUs)
admin.site.register(WifiBased)


class OrganizationFilter(admin.SimpleListFilter):
    """Filter users by the organization of their schooladmin/staff login profile."""
    title = 'organization'
    parameter_name = 'org'

    def lookups(self, request, model_admin):
        return [(org.id, org.name) for org in Organization.objects.order_by('name')]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        return queryset.filter(
            Q(schooladmin__org_id=self.value()) | Q(staff__org_id=self.value())
        )


class HasLoggedInFilter(admin.SimpleListFilter):
    """Filter to users who have (or haven't) actually logged in at least once."""
    title = 'has logged in'
    parameter_name = 'has_logged_in'

    def lookups(self, request, model_admin):
        return [('yes', 'Yes'), ('no', 'No')]

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.filter(last_login__isnull=False)
        if self.value() == 'no':
            return queryset.filter(last_login__isnull=True)
        return queryset


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'user_type', 'org_name', 'is_active', 'last_login', 'date_joined')
    list_filter = ('user_type', OrganizationFilter, HasLoggedInFilter, 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('schooladmin__org', 'staff__org')

    @admin.display(description='Organization')
    def org_name(self, obj):
        schooladmin = getattr(obj, 'schooladmin', None)
        if schooladmin:
            return schooladmin.org.name
        staff = getattr(obj, 'staff', None)
        if staff:
            return staff.org.name
        return '—'