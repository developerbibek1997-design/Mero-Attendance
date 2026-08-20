"""
"Organization at a Glance" summary counts for the Organization Profile page
— feature-gated so a stat only appears when the org actually has that
module enabled, rather than showing a permanent zero.
"""
from django.db.models import Sum

from school.features import has_feature


def get_org_stats(org):
    from handle.models import (
        member, Branch, Classification, AttendanceRecord, StockItem,
    )
    from management.models import LeaveReport

    active_members = member.objects.filter(org=org).exclude(status='dumped')

    stats = {
        'total_members': active_members.count(),
        'total_branches': Branch.objects.filter(org=org).count(),
        'total_classifications': Classification.objects.filter(org=org).count(),
        'total_attendance_records': AttendanceRecord.objects.filter(org=org).count(),
        'total_leave_requests': LeaveReport.objects.filter(org=org).count(),
    }

    if has_feature(org, 'student_mgmt'):
        stats['total_students'] = active_members.filter(member_type='student').count()

    if has_feature(org, 'stock'):
        stock_items = StockItem.objects.filter(org=org)
        stats['total_stock_items'] = stock_items.count()
        stats['total_stock_quantity'] = stock_items.exclude(status='archived').aggregate(
            total=Sum('quantity'),
        )['total'] or 0

    return stats
