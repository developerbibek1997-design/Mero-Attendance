from django.shortcuts import redirect, render
from django.views import View
from handle.models import AttendingClassification, Classification, PaySlip, member
import datetime
from django.views.generic import ListView
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from handle.models import AttendanceRecord, Organization
from django.shortcuts import get_object_or_404

"""
staff_views.py — Full Staff Attendance System Views
Add these to your existing views.py or include in a separate file
URL prefix: /staff/api/staff/
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
import datetime
import math
import qrcode
import io
import base64
from management.models import LeaveReport, LeaveType, LocationBased, QRCode, WifiBased
from handle.models import (
    AttendingClassification, Classification, member,
    AttendanceRecord, Organization
)

from django.contrib import messages
from django.views import View
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin


class StaffLeaveView(LoginRequiredMixin, View):
    template_name = 'staff/apply_leave.html'

    def get(self, request, *args, **kwargs):
        memb = getattr(request.user.staff, 'member', None)
        if not memb:
            messages.error(request, "No member profile linked to your account.")
            return redirect('staff:dashboard')
        org = request.user.staff.org
        
        # Get leave balances
        leave_types = LeaveType.objects.filter(org=org)
        balance_list = []
        for lt in leave_types:
            try:
                bal = memb.get_leave_balance(lt.id)
                balance_list.append({
                    'id': lt.id,
                    'name': lt.name,
                    'remaining': bal['remaining'],
                    'total': bal['total']
                })
            except AttributeError:
                # Fallback if get_leave_balance isn't fully defined
                balance_list.append({'id': lt.id, 'name': lt.name, 'remaining': 0, 'total': 0})
            
        return render(request, self.template_name, {'leave_types': balance_list})

    def post(self, request, *args, **kwargs):
        memb = getattr(request.user.staff, 'member', None)
        if not memb:
            messages.error(request, "No member profile linked to your account.")
            return redirect('staff:dashboard')
        org = request.user.staff.org

        lt_id = request.POST.get('leave_type')
        start_date = datetime.datetime.strptime(request.POST.get('start_date'), "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(request.POST.get('end_date'), "%Y-%m-%d").date()
        base_reason = request.POST.get('reason')
        
        # Capture Advanced Timing Logic
        timing_type = request.POST.get('timing_type', 'full_day')
        specific_time = request.POST.get('specific_time', '')
        half_day_period = request.POST.get('half_day_period', 'first_half')
        
        # 1. Calculate requested days (Default is End - Start + 1)
        days_requested = float((end_date - start_date).days + 1)

        # 2. Format the reason and adjust days based on type
        formatted_reason = base_reason
        
        if timing_type == 'late_in':
            formatted_reason = f"[Late In at {specific_time}] - {base_reason}"
        elif timing_type == 'early_out':
            formatted_reason = f"[Early Out at {specific_time}] - {base_reason}"
        elif timing_type == 'half_day':
            period_text = "Morning" if half_day_period == 'first_half' else "Afternoon"
            formatted_reason = f"[Half Day: {period_text}] - {base_reason}"
            days_requested = 0.5 # Override to only deduct half a day!

        # 3. Check Balance (ensure they have enough days)
        bal = memb.get_leave_balance(lt_id)
        if days_requested > bal['remaining']:
            messages.error(request, f"Insufficient balance. You requested {days_requested} days, but only have {bal['remaining']} left.")
            return redirect('staff:apply_leave')
            
        # 4. Save to Database
        LeaveReport.objects.create(
            member=memb,
            org=org,
            leave_type=LeaveType.objects.get(id=lt_id),
            gap_start=start_date,
            gap_end=end_date,
            reason=formatted_reason,
            approved=False # Pending admin approval
        )
        
        messages.success(request, f"Your {timing_type.replace('_', ' ').title()} request has been submitted.")
        return redirect('staff:my_attendance')
class MyAttendanceReportView(LoginRequiredMixin, View):
    template_name = 'staff/my_report.html'

    def get(self, request, *args, **kwargs):
        try:
            memb = request.user.staff.member 
            org = request.user.staff.org
        except AttributeError:
            return render(request, 'staff/my_report.html', {'error': "No associated member profile found."})

        # Month Filtering Logic
        month_str = request.GET.get('month')
        if month_str:
            try:
                target_year, target_month = map(int, month_str.split('-'))
            except ValueError:
                target_year, target_month = datetime.date.today().year, datetime.date.today().month
        else:
            today = datetime.date.today()
            target_year, target_month = today.year, today.month
            month_str = f"{target_year}-{target_month:02d}"

        # Fetch Data Filtered by Month
        attendance_logs = AttendanceRecord.objects.filter(
            mem=memb, 
            scanned_time__year=target_year,
            scanned_time__month=target_month
        ).order_by('-scanned_time')

        leave_history = LeaveReport.objects.filter(
            member=memb,
            gap_start__year=target_year,
            gap_start__month=target_month
        ).order_by('-gap_start')
        
        # Calculate Stats for the selected month
        # Using .dates() to count unique days present (in case of multiple scans per day)
        total_present = attendance_logs.dates('scanned_time', 'day').count()
        
        context = {
            'memb': memb,
            'logs': attendance_logs,
            'leaves': leave_history,
            'total_present': total_present,
            'org': org,
            'selected_month': month_str, # Passed to the HTML to keep the date picker accurate
        }
        return render(request, self.template_name, context)


class StaffLocationCheckinView(LoginRequiredMixin, View):
    template_name = 'staff/location_checkin.html'
    
    def get(self, request, *args, **kwargs):
        # Simply show the location checkin page
        return render(request, self.template_name)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in meters between two GPS coordinates."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_staff_org(user):
    return user.staff.org


def already_marked_today(memb, org):
    today = datetime.date.today()
    return AttendanceRecord.objects.filter(
        mem=memb, org=org, scanned_time__date=today
    ).exists()


def create_attendance(memb, org, method='manual'):
    return AttendanceRecord.objects.create(
        mem=memb,
        org=org,
        scanned_time=timezone.now(),
        # method=method  # uncomment if you add method field to AttendanceRecord
    )


# ─── 1. Staff Dashboard Info ──────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_staff_classes(request):
    """Returns org config + assigned classes for the logged-in staff."""
    try:
        org = get_staff_org(request.user)
        staff_classes = AttendingClassification.objects.filter(
            staff=request.user
        ).select_related('classification')

        classes_data = [
            {"id": sc.classification.id, "name": sc.classification.name}
            for sc in staff_classes
        ]

        return Response({
            "org_id": org.id,
            "org_name": org.name,
            "classes": classes_data,
            # Feature flags — Flutter uses these to show/hide methods
            "features": {
                "location_based": org.location_based,
                "qr_based": org.qr_based,
                "auto_checkin": org.auto_checkin,
                "wifi_based": getattr(org, 'wifi_based', False),
                "nepali_date": org.nepali_date,
                "multi_feature": org.mutifeature_enable,
            }
        }, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response(
            {"error": "Staff profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )


# ─── 2. Class Members + Today Attendance ─────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_class_members(request, class_id):
    """Returns all members in a class with today's attendance status."""
    try:
        clas = Classification.objects.get(id=class_id)
        org = get_staff_org(request.user)
        members = member.objects.filter(classification=clas, org=org)

        today = datetime.date.today()
        attended_ids = set(
            AttendanceRecord.objects.filter(
                mem__in=members, org=org, scanned_time__date=today
            ).values_list('mem_id', flat=True)
        )

        members_data = [
            {
                "id": m.id,
                "name": m.name,
                "phone": m.phone,
                "is_present": m.id in attended_ids,
            }
            for m in members
        ]

        return Response({
            "class_name": clas.name,
            "date": today.strftime("%Y-%m-%d"),
            "org_id": org.id,
            "members": members_data,
        }, status=status.HTTP_200_OK)

    except Classification.DoesNotExist:
        return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)


# ─── 3. Manual Mark Present ───────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_mark_present(request):
    """Manually mark a member present. Org is taken from logged-in staff."""
    member_id = request.data.get('member_id')
    if not member_id:
        return Response({"error": "Missing member_id."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        memb = member.objects.get(id=member_id)
        org = get_staff_org(request.user)

        if already_marked_today(memb, org):
            return Response(
                {"status": "already_marked", "message": f"{memb.name} already marked today."},
                status=status.HTTP_200_OK
            )

        create_attendance(memb, org, method='manual')
        return Response(
            {"status": "success", "message": f"{memb.name} marked present."},
            status=status.HTTP_201_CREATED
        )

    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ─── 4. Location-Based Attendance ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_locations(request):
    """Returns all allowed location zones for the org."""
    try:
        org = get_staff_org(request.user)
        if not org.location_based:
            return Response({"error": "Location-based attendance not enabled."}, status=status.HTTP_403_FORBIDDEN)

        locations = LocationBased.objects.filter(org=org)
        data = [
            {
                "id": loc.id,
                "name": loc.name,
                "latitude": loc.latitude,
                "longitude": loc.longitude,
                "radius": loc.radius,
            }
            for loc in locations
        ]
        return Response({"locations": data}, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_location_checkin(request):
    """
    Mark attendance based on GPS location.
    Body: { member_id, latitude, longitude }
    """
    member_id = request.data.get('member_id')
    user_lat = request.data.get('latitude')
    user_lon = request.data.get('longitude')

    if not all([member_id, user_lat, user_lon]):
        return Response({"error": "Missing member_id, latitude, or longitude."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        memb = member.objects.get(id=member_id)
        org = get_staff_org(request.user)

        if not org.location_based:
            return Response({"error": "Location-based attendance not enabled."}, status=status.HTTP_403_FORBIDDEN)

        if already_marked_today(memb, org):
            return Response(
                {"status": "already_marked", "message": f"{memb.name} already marked today."},
                status=status.HTTP_200_OK
            )

        # Check if within any allowed zone
        locations = LocationBased.objects.filter(org=org)
        in_zone = False
        matched_zone = None

        for loc in locations:
            dist = haversine_distance(float(user_lat), float(user_lon), loc.latitude, loc.longitude)
            if dist <= loc.radius:
                in_zone = True
                matched_zone = loc.name
                break

        if not in_zone:
            return Response(
                {"status": "out_of_zone", "message": "You are not within an allowed attendance zone."},
                status=status.HTTP_400_BAD_REQUEST
            )

        create_attendance(memb, org, method='location')
        return Response(
            {"status": "success", "message": f"{memb.name} marked present via location ({matched_zone})."},
            status=status.HTTP_201_CREATED
        )

    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ─── 5. QR Code Attendance ────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_qr_codes(request):
    """Returns QR codes for the org as base64 images."""
    try:
        org = get_staff_org(request.user)
        if not org.qr_based:
            return Response({"error": "QR-based attendance not enabled."}, status=status.HTTP_403_FORBIDDEN)

        qr_codes = QRCode.objects.filter(org=org)
        data = []
        for qr in qr_codes:
            # Generate a signed token QR so Flutter can verify
            token = f"ORG:{org.id}:QR:{qr.id}"
            qr_img = qrcode.make(token)
            buffer = io.BytesIO()
            qr_img.save(buffer, format='PNG')
            b64 = base64.b64encode(buffer.getvalue()).decode()

            data.append({
                "id": qr.id,
                "name": qr.name,
                "token": token,
                "qr_base64": b64,
            })

        return Response({"qr_codes": data}, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_qr_checkin(request):
    """
    Mark attendance via scanned QR token.
    Body: { member_id, qr_token }
    """
    member_id = request.data.get('member_id')
    qr_token = request.data.get('qr_token')

    if not all([member_id, qr_token]):
        return Response({"error": "Missing member_id or qr_token."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        memb = member.objects.get(id=member_id)
        org = get_staff_org(request.user)

        if not org.qr_based:
            return Response({"error": "QR-based attendance not enabled."}, status=status.HTTP_403_FORBIDDEN)

        # Validate token format: ORG:<org_id>:QR:<qr_id>
        parts = qr_token.split(':')
        if len(parts) != 4 or parts[0] != 'ORG' or parts[2] != 'QR':
            return Response({"error": "Invalid QR token."}, status=status.HTTP_400_BAD_REQUEST)

        token_org_id = int(parts[1])
        qr_id = int(parts[3])

        if token_org_id != org.id:
            return Response({"error": "QR code does not belong to your organization."}, status=status.HTTP_403_FORBIDDEN)

        # Verify QR exists
        if not QRCode.objects.filter(id=qr_id, org=org).exists():
            return Response({"error": "QR code not found."}, status=status.HTTP_404_NOT_FOUND)

        if already_marked_today(memb, org):
            return Response(
                {"status": "already_marked", "message": f"{memb.name} already marked today."},
                status=status.HTTP_200_OK
            )

        create_attendance(memb, org, method='qr')
        return Response(
            {"status": "success", "message": f"{memb.name} marked present via QR."},
            status=status.HTTP_201_CREATED
        )

    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ─── 6. WiFi-Based Attendance ─────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_wifi_checkin(request):
    """
    Mark attendance based on connected WiFi BSSID.
    Body: { member_id, bssid, ssid }
    """
    member_id = request.data.get('member_id')
    bssid = request.data.get('bssid', '').upper().strip()
    ssid = request.data.get('ssid', '').strip()

    if not all([member_id, bssid]):
        return Response({"error": "Missing member_id or bssid."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        memb = member.objects.get(id=member_id)
        org = get_staff_org(request.user)

        wifi_enabled = getattr(org, 'wifi_based', False)
        if not wifi_enabled:
            return Response({"error": "WiFi-based attendance not enabled."}, status=status.HTTP_403_FORBIDDEN)

        # Check BSSID against allowed networks
        allowed = WifiBased.objects.filter(org=org, bssid__iexact=bssid).exists()
        if not allowed:
            return Response(
                {"status": "wrong_wifi", "message": f"WiFi '{ssid}' is not an authorized network."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if already_marked_today(memb, org):
            return Response(
                {"status": "already_marked", "message": f"{memb.name} already marked today."},
                status=status.HTTP_200_OK
            )

        create_attendance(memb, org, method='wifi')
        return Response(
            {"status": "success", "message": f"{memb.name} marked present via WiFi ({ssid})."},
            status=status.HTTP_201_CREATED
        )

    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_wifi_networks(request):
    """Returns allowed WiFi networks for the org."""
    try:
        org = get_staff_org(request.user)
        networks = WifiBased.objects.filter(org=org)
        data = [{"id": w.id, "name": w.name, "ssid": w.ssid, "bssid": w.bssid} for w in networks]
        return Response({"networks": data}, status=status.HTTP_200_OK)
    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)


# ─── 7. Auto Check-in (Bulk) ─────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_auto_checkin_class(request):
    """
    Auto mark all members in a class as present.
    Body: { class_id }
    """
    class_id = request.data.get('class_id')
    if not class_id:
        return Response({"error": "Missing class_id."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        org = get_staff_org(request.user)
        if not org.auto_checkin:
            return Response({"error": "Auto check-in not enabled."}, status=status.HTTP_403_FORBIDDEN)

        clas = Classification.objects.get(id=class_id)
        members = member.objects.filter(classification=clas, org=org)

        today = datetime.date.today()
        already_attended = set(
            AttendanceRecord.objects.filter(
                mem__in=members, org=org, scanned_time__date=today
            ).values_list('mem_id', flat=True)
        )

        marked = []
        skipped = []
        for m in members:
            if m.id in already_attended:
                skipped.append(m.name)
            else:
                create_attendance(m, org, method='auto')
                marked.append(m.name)

        return Response({
            "status": "success",
            "marked_count": len(marked),
            "skipped_count": len(skipped),
            "marked": marked,
            "skipped": skipped,
        }, status=status.HTTP_201_CREATED)

    except Classification.DoesNotExist:
        return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# ─── 8. Attendance Report ─────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_attendance_summary(request, class_id):
    """
    Returns attendance records for a class.
    Query params: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    """
    try:
        org = get_staff_org(request.user)
        clas = Classification.objects.get(id=class_id)
        members = member.objects.filter(classification=clas, org=org)

        start_str = request.GET.get('start_date')
        end_str = request.GET.get('end_date')

        records = AttendanceRecord.objects.filter(mem__in=members, org=org)
        if start_str:
            records = records.filter(scanned_time__date__gte=start_str)
        if end_str:
            records = records.filter(scanned_time__date__lte=end_str)

        # Build per-member summary
        summary = {}
        for m in members:
            summary[m.id] = {"id": m.id, "name": m.name, "days_present": 0, "dates": []}

        for r in records.values('mem_id', 'scanned_time'):
            mid = r['mem_id']
            if mid in summary:
                date_str = r['scanned_time'].strftime('%Y-%m-%d')
                if date_str not in summary[mid]['dates']:
                    summary[mid]['dates'].append(date_str)
                    summary[mid]['days_present'] += 1

        return Response({
            "class_name": clas.name,
            "members": list(summary.values()),
        }, status=status.HTTP_200_OK)

    except Classification.DoesNotExist:
        return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
def mark_present(request):
    if request.method == "POST":
        member_id = request.POST.get('member_id')
        organization_id = request.POST.get('organization_id')
        
        today = datetime.date.today()
        
        # Check if record exists
        record = AttendanceRecord.objects.filter(
            mem_id=member_id,
            org_id=organization_id,
            scanned_time__date=today
        )
        
        if record.exists():
            # If exists, delete it (Undo/Mark Absent)
            record.delete()
            return JsonResponse({"status": "deleted"})
        else:
            # If not exists, create it (Mark Present)
            memb = member.objects.get(id=member_id)
            organization = Organization.objects.get(id=organization_id)
            AttendanceRecord.objects.create(mem=memb, org=organization, scanned_time=datetime.datetime.now())
            return JsonResponse({"status": "created"})
            
    return JsonResponse({"status": "failed"})



# 1. Update your existing Dashboard View
from django.contrib.auth.decorators import login_required

@login_required(login_url='/login/')
def Dashboard(request):
    if request.user.user_type != '3':
        return redirect('management:login')
    try:
        org = request.user.staff.org
    except Exception:
        messages.error(request, "Your account does not have a staff profile linked. Contact admin.")
        return redirect('management:login')

    clas = AttendingClassification.objects.filter(staff=request.user)
    memb = getattr(request.user.staff, 'member', None)

    is_student = memb and memb.member_type in ('student', 'trainee')

    if is_student:
        from handle.models import Bill, AttendanceGap, ExamTerm, ResultRecord, TaskInstance
        from management.models import LeaveReport, LeaveType
        today = datetime.date.today()
        bills = Bill.objects.filter(member=memb, org=org).order_by('-issue_date')
        unpaid_bills = bills.filter(status__in=['Unpaid', 'Partial'])
        gaps = AttendanceGap.objects.filter(member=memb, org=org).order_by('-date')[:10]
        published_exams = ExamTerm.objects.filter(org=org, is_published=True)
        recent_results = ResultRecord.objects.filter(student=memb, exam__in=published_exams).select_related('subject', 'exam')[:10]
        leave_types = LeaveType.objects.filter(org=org)
        pending_leaves = LeaveReport.objects.filter(member=memb, org=org, approved=False, rejected=False).count()

        # Task summary for students
        my_tasks_today = TaskInstance.objects.filter(assigned_member=memb, due_date=today).exclude(status='cancelled')
        my_tasks_pending = TaskInstance.objects.filter(assigned_member=memb, status='pending').count()

        return render(request, 'staff/student_dashboard.html', {
            'org': org,
            'memb': memb,
            'bills': bills[:5],
            'unpaid_count': unpaid_bills.count(),
            'total_unpaid': sum(b.balance_due for b in unpaid_bills),
            'gaps': gaps,
            'published_exams': published_exams,
            'recent_results': recent_results,
            'leave_types': leave_types,
            'pending_leaves': pending_leaves,
            'is_student': True,
            'my_tasks_today': my_tasks_today,
            'my_tasks_pending': my_tasks_pending,
        })

    # Teaching staff / employee dashboard
    today = datetime.date.today()
    total_present_today = 0
    total_members_assigned = 0
    if clas.exists():
        class_ids = clas.values_list('classification_id', flat=True)
        members_in_classes = member.objects.filter(classification_id__in=class_ids, org=org)
        total_members_assigned = members_in_classes.count()
        total_present_today = AttendanceRecord.objects.filter(
            mem__in=members_in_classes, org=org, scanned_time__date=today
        ).values('mem').distinct().count()

    from handle.models import PaySlip, AttendanceGap, CourseAttendance, TaskInstance
    payslips = PaySlip.objects.filter(member=memb, org=org).order_by('-from_date')[:3] if memb else []
    pending_gaps = AttendanceGap.objects.filter(teacher=request.user, org=org, recovery_status='pending').count()
    recent_attendance_logs = CourseAttendance.objects.filter(staff=request.user, org=org).order_by('-attendance_date')[:5]

    # Task summary for staff
    my_tasks_today = []
    my_tasks_pending = 0
    my_tasks_overdue = 0
    if memb:
        task_qs = TaskInstance.objects.filter(assigned_member=memb)
        my_tasks_today = task_qs.filter(due_date=today).exclude(status='cancelled').select_related('task')
        my_tasks_pending = task_qs.filter(status__in=['pending', 'in_progress']).count()
        my_tasks_overdue = task_qs.filter(status__in=['overdue', 'missed_absence']).count()

    return render(request, 'staff/Sdashboard.html', {
        'clas': clas,
        'org': org,
        'memb': memb,
        'is_student': False,
        'total_present_today': total_present_today,
        'total_members_assigned': total_members_assigned,
        'payslips': payslips,
        'pending_gaps': pending_gaps,
        'recent_attendance_logs': recent_attendance_logs,
        'my_tasks_today': my_tasks_today,
        'my_tasks_pending': my_tasks_pending,
        'my_tasks_overdue': my_tasks_overdue,
        'today': today,
    })


# 2. Add the Location Check-in View
class StaffLocationCheckinView(LoginRequiredMixin, View):
    template_name = 'staff/location_checkin.html'
    
    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        # Get all allowed location zones for this organization
        locations = LocationBased.objects.filter(org=org)
        
        # Pass location data to the frontend so JS can verify it
        loc_data = [{'lat': loc.latitude, 'lng': loc.longitude, 'radius': loc.radius, 'name': loc.name} for loc in locations]
        
        return render(request, self.template_name, {'locations': loc_data})

    def post(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        
        try:
            user_lat = float(request.POST.get('latitude'))
            user_lon = float(request.POST.get('longitude'))
        except (TypeError, ValueError):
            messages.error(request, "Invalid GPS coordinates received.")
            return redirect('staff:location_checkin')

        # Prevent double check-in
        today = datetime.date.today()
        if AttendanceRecord.objects.filter(mem=memb, org=org, scanned_time__date=today).exists():
            messages.warning(request, "You have already checked in for today.")
            return redirect('staff:dashboard')

        # Backend Verification: Check if within ANY allowed zone
        allowed_locations = LocationBased.objects.filter(org=org)
        in_zone = False
        matched_zone_name = ""

        for loc in allowed_locations:
            dist = haversine_distance(user_lat, user_lon, loc.latitude, loc.longitude)
            if dist <= loc.radius:
                in_zone = True
                matched_zone_name = loc.name
                break

        if in_zone:
            # Create Attendance Record
            AttendanceRecord.objects.create(mem=memb, org=org, scanned_time=timezone.now())
            messages.success(request, f"Successfully checked in at {matched_zone_name}!")
            return redirect('staff:dashboard')
        else:
            messages.error(request, "Check-in failed: You are not within the required radius of an authorized attendance zone.")
            return redirect('staff:location_checkin')

def attendanceView(request, id, name):
    from handle.models import Course, CourseAttendance, AttendanceGap
    org = request.user.staff.org
    clas = Classification.objects.get(id=id)
    mem = member.objects.filter(classification=clas, org=org)
    today = datetime.date.today()

    attendance_records = AttendanceRecord.objects.filter(
        mem__in=mem, org=org, scanned_time__date=today
    ).values_list('mem_id', flat=True)
    attended_members = set(attendance_records)

    # Courses that belong to this classification
    courses = Course.objects.filter(org=org, classifications=clas, status='active')

    # Today's teaching logs for this class (any course in this classification)
    todays_logs = CourseAttendance.objects.filter(
        org=org, staff=request.user, course__in=courses, attendance_date=today
    ).select_related('course')
    logged_course_ids = set(todays_logs.values_list('course_id', flat=True))

    if request.method == 'POST':
        course_id = request.POST.get('course_id')
        topic = request.POST.get('topic_taught', '').strip()
        gap_note = request.POST.get('gap_note', '').strip()
        absent_ids = request.POST.getlist('absent_member_ids')
        if course_id and topic:
            try:
                course = Course.objects.get(pk=course_id, org=org)
                CourseAttendance.objects.update_or_create(
                    org=org, staff=request.user, course=course, attendance_date=today,
                    defaults={'topic_taught': topic, 'gap_note': gap_note,
                              'branch': course.branch, 'classification': clas, 'section': None}
                )
                for mid in absent_ids:
                    try:
                        m = member.objects.get(pk=mid, org=org)
                        AttendanceGap.objects.get_or_create(
                            org=org, member=m, course=course, date=today,
                            defaults={'branch': course.branch, 'classification': clas,
                                      'teacher': request.user, 'topic_missed': topic}
                        )
                    except member.DoesNotExist:
                        pass
                messages.success(request, f"Teaching log saved for {course.name}.")
            except Course.DoesNotExist:
                messages.error(request, "Invalid course selected.")
        return redirect('staff:attendance', id=id, name=name)

    dist = {
        'mem': mem,
        'clas': clas,
        'date': today,
        'org': org,
        'attended_members': attended_members,
        'courses': courses,
        'todays_logs': todays_logs,
        'logged_course_ids': logged_course_ids,
    }
    return render(request, "staff/attendance.html", dist)



class memReport(ListView):
    template_name = 'staff/report.html'

    def get(self, request, *args, **kwargs):
        user = request.user
        org = user.staff.org
        today_date = datetime.date.today()

        # SECURITY FIX: Only get classes explicitly assigned to this specific staff member
        assigned_class_ids = AttendingClassification.objects.filter(
            staff=user
        ).values_list('classification_id', flat=True)
        
        assigned_classes = Classification.objects.filter(id__in=assigned_class_ids)

        # By default, show members from ALL of THEIR assigned classes
        tm = member.objects.filter(org=org, classification__in=assigned_class_ids)
       
        dist = {
            'date': today_date.strftime("%Y-%m-%d"), # Pass formatted date for HTML5 input
            'tm': tm,
            'org': org,
            'thisone': 'All Assigned',
            'clas': assigned_classes
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        user = request.user
        org = user.staff.org
        today_date = datetime.date.today()
        
        # Capture form data
        selected_class_id = request.POST.get('filter')
        posted_date = request.POST.get('date')

        # Format the date properly
        if not posted_date: 
            filter_date = today_date
        else:
            filter_date = datetime.datetime.strptime(posted_date, "%Y-%m-%d").date()
            
        # Set the class variable so your model methods (.first_daily_time()) know what date to look at
        member.date = filter_date

        # SECURITY FIX: Ensure they can only filter by their assigned classes
        assigned_class_ids = AttendingClassification.objects.filter(
            staff=user
        ).values_list('classification_id', flat=True)
        assigned_classes = Classification.objects.filter(id__in=assigned_class_ids)

        if selected_class_id and selected_class_id != 'All':
            # Verify they actually have access to the requested class (prevents HTML manipulation hacking)
            if int(selected_class_id) in assigned_class_ids:
                tm = member.objects.filter(org=org, classification_id=selected_class_id)
                sn = Classification.objects.get(id=selected_class_id).name
            else:
                tm = member.objects.none()
                sn = "Unauthorized"
        else:
            # 'All' selected - show only their assigned classes
            tm = member.objects.filter(org=org, classification__in=assigned_class_ids)
            sn = 'All Assigned'
            
        dist = {
            'date': filter_date.strftime("%Y-%m-%d"),
            'tm': tm,
            'thisone': sn,
            'org': org,
            'clas': assigned_classes
        }
        return render(request, self.template_name, dist)
    



class MyPayslipsView(LoginRequiredMixin, View):
    template_name = 'staff/my_payslips.html'

    def get(self, request, *args, **kwargs):
        try:
            memb = request.user.staff.member
            org = request.user.staff.org
        except AttributeError:
            return render(request, self.template_name, {'error': "No associated member profile found."})

        # Fetch payslips ordered by the newest first
        payslips = PaySlip.objects.filter(member=memb).order_by('-from_date')
        
        context = {
            'memb': memb,
            'org': org,
            'payslips': payslips,
        }
        return render(request, self.template_name, context) 
    

class StaffWifiCheckinView(LoginRequiredMixin, View):
    template_name = 'staff/wifi_checkin.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        
        # Security Check: We are using 'qr_based' to enable WiFi features based on your model
        if not org.qr_based:
            messages.error(request, "WiFi Auto Check-in is not enabled for your organization.")
            return redirect('staff:dashboard')

        return render(request, self.template_name, {'org': org})

# ─── Student Portal Views ─────────────────────────────────────────────────────

class StudentBillsView(LoginRequiredMixin, View):
    template_name = 'staff/student_bills.html'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import Bill
        bills = Bill.objects.filter(member=memb, org=org).prefetch_related('items').order_by('-issue_date')
        return render(request, self.template_name, {'org': org, 'memb': memb, 'bills': bills})


class StudentResultsView(LoginRequiredMixin, View):
    template_name = 'staff/student_results.html'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import ExamTerm, ResultRecord
        exams = ExamTerm.objects.filter(org=org, is_published=True).order_by('-start_date')
        selected_exam_id = request.GET.get('exam')
        results = []
        selected_exam = None
        if selected_exam_id:
            try:
                selected_exam = exams.get(pk=selected_exam_id)
                results = ResultRecord.objects.filter(student=memb, exam=selected_exam).select_related('subject')
            except ExamTerm.DoesNotExist:
                pass
        # Compute summary stats for the enhanced template
        total_obtained = 0
        total_full = 0
        pass_count = 0
        fail_count = 0
        absent_count = 0
        overall_grade = '—'
        total_percentage = 0
        overall_pass = False
        from handle.models import compute_grade
        for r in results:
            if r.is_absent:
                absent_count += 1
            else:
                total_obtained += float(r.obtained_marks)
                total_full += float(r.subject.full_marks)
                if r.is_passed:
                    pass_count += 1
                else:
                    fail_count += 1
        if total_full > 0:
            total_percentage = round(total_obtained / total_full * 100, 1)
            overall_grade = compute_grade(total_percentage)
            overall_pass = (fail_count == 0 and absent_count == 0)
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'member': memb,
            'exams': exams, 'results': results, 'selected_exam': selected_exam,
            'total_obtained': total_obtained, 'total_full': total_full,
            'total_percentage': total_percentage, 'overall_grade': overall_grade,
            'pass_count': pass_count, 'fail_count': fail_count,
            'absent_count': absent_count, 'overall_pass': overall_pass,
        })


class StudentGapsView(LoginRequiredMixin, View):
    template_name = 'staff/student_gaps.html'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import AttendanceGap
        gaps = AttendanceGap.objects.filter(member=memb, org=org).order_by('-date')
        return render(request, self.template_name, {'org': org, 'memb': memb, 'gaps': gaps})


class StudentComplaintView(LoginRequiredMixin, View):
    """Students can file complaints and view their own."""
    template_name = 'staff/student_complaint.html'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import Complaint
        my_complaints = Complaint.objects.filter(filed_by=memb, org=org).order_by('-created_at')
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'my_complaints': my_complaints,
        })

    def post(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import Complaint
        subject = request.POST.get('subject', '').strip()
        description = request.POST.get('description', '').strip()
        priority = request.POST.get('priority', 'medium')
        complaint_type = request.POST.get('complaint_type', '')
        if not subject or not description:
            messages.error(request, "Subject and description are required.")
        else:
            Complaint.objects.create(
                org=org, filed_by=memb, subject=subject,
                description=description, priority=priority,
                complaint_type=complaint_type,
            )
            messages.success(request, "Complaint submitted successfully.")
        return redirect('staff:student_complaint')


# ─── Staff Teaching Log (web) ─────────────────────────────────────────────────

class TeachingLogView(LoginRequiredMixin, View):
    """Staff records today's lesson covered (course attendance with topic)."""
    template_name = 'staff/teaching_log.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        from handle.models import Course, CourseAttendance, Classification
        assigned_class_ids = AttendingClassification.objects.filter(
            staff=request.user
        ).values_list('classification_id', flat=True)
        courses = Course.objects.filter(
            org=org, classifications__in=assigned_class_ids
        ).distinct()
        logs = CourseAttendance.objects.filter(
            staff=request.user, org=org
        ).order_by('-attendance_date')[:20]
        return render(request, self.template_name, {
            'org': org, 'courses': courses, 'logs': logs,
        })

    def post(self, request, *args, **kwargs):
        org = request.user.staff.org
        from handle.models import Course, CourseAttendance, Classification, AttendanceGap
        course_id = request.POST.get('course_id')
        topic = request.POST.get('topic_taught', '').strip()
        gap_note = request.POST.get('gap_note', '').strip()
        date_str = request.POST.get('attendance_date', '')
        mark_absent_ids = request.POST.getlist('absent_member_ids')

        if not course_id or not topic:
            messages.error(request, "Course and topic are required.")
            return redirect('staff:teaching_log')

        try:
            course = Course.objects.get(pk=course_id, org=org)
            att_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.date.today()
        except (Course.DoesNotExist, ValueError):
            messages.error(request, "Invalid course or date.")
            return redirect('staff:teaching_log')

        classification = course.classifications.first()
        branch = course.branch
        section = course.sections.first()

        log = CourseAttendance.objects.create(
            org=org, staff=request.user, course=course,
            branch=branch, classification=classification,
            section=section, attendance_date=att_date,
            topic_taught=topic, gap_note=gap_note,
        )

        for mid in mark_absent_ids:
            try:
                m = member.objects.get(pk=mid, org=org)
                AttendanceGap.objects.get_or_create(
                    org=org, member=m, course=course, date=att_date,
                    defaults={
                        'branch': branch, 'classification': classification,
                        'section': section, 'teacher': request.user,
                        'topic_missed': topic,
                    },
                )
            except member.DoesNotExist:
                pass

        messages.success(request, f"Teaching log saved for {course.name} on {att_date}.")
        return redirect('staff:teaching_log')


# ============================================================
# TASK MANAGEMENT — Staff Views
# ============================================================

from handle.models import Task, TaskInstance, TaskUpdateLog, TaskAttachment
from school.email_utils import send_task_completed_email


class MyTasksView(View):
    template_name = 'staff/tasks/my_tasks.html'

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('management:login')
        org = request.user.staff.org
        memb = getattr(request.user.staff, 'member', None)
        if not memb:
            return render(request, self.template_name, {'error': 'No member profile linked.'})

        import datetime as _dt
        today = _dt.date.today()

        # Auto-refresh overdue
        stale = TaskInstance.objects.filter(
            assigned_member=memb, due_date__lt=today, status__in=['pending', 'in_progress']
        )
        for inst in stale:
            inst.refresh_overdue_status()

        all_inst = TaskInstance.objects.filter(assigned_member=memb).select_related('task')

        today_tasks = all_inst.filter(due_date=today).exclude(status='cancelled')
        pending_tasks = all_inst.filter(status='pending').order_by('due_date')
        in_progress_tasks = all_inst.filter(status='in_progress').order_by('due_date')
        overdue_tasks = all_inst.filter(status__in=['overdue', 'missed_absence']).order_by('due_date')
        completed_tasks = all_inst.filter(status='completed').order_by('-completed_at')[:20]
        upcoming_tasks = all_inst.filter(due_date__gt=today, status='pending').order_by('due_date')[:10]

        ctx = dict(
            org=org, memb=memb, today=today,
            today_tasks=today_tasks,
            pending_tasks=pending_tasks,
            in_progress_tasks=in_progress_tasks,
            overdue_tasks=overdue_tasks,
            completed_tasks=completed_tasks,
            upcoming_tasks=upcoming_tasks,
            total=all_inst.count(),
            completed_count=all_inst.filter(status='completed').count(),
            pending_count=all_inst.filter(status__in=['pending', 'in_progress']).count(),
            overdue_count=all_inst.filter(status__in=['overdue', 'missed_absence']).count(),
        )
        return render(request, self.template_name, ctx)


class UpdateTaskStatusView(View):
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return redirect('management:login')
        org = request.user.staff.org
        memb = getattr(request.user.staff, 'member', None)
        if not memb:
            messages.error(request, 'No member profile linked.')
            return redirect('staff:my_tasks')

        from django.contrib import messages as _msg
        inst = get_object_or_404(TaskInstance, pk=pk, assigned_member=memb)
        action = request.POST.get('action')
        old_status = inst.status

        if action == 'in_progress':
            inst.status = 'in_progress'
            inst.save(update_fields=['status', 'updated_at'])
            TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='in_progress')
            _msg.success(request, "Task marked as In Progress.")

        elif action == 'completed':
            from django.utils import timezone as _tz
            note = request.POST.get('completion_note', '')
            inst.status = 'completed'
            inst.completion_note = note
            inst.completed_at = _tz.now()
            if inst.task.requires_approval:
                inst.approval_status = 'pending_approval'
            if 'proof' in request.FILES:
                inst.proof_attachment = request.FILES['proof']
            inst.save()
            TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='completed', note=note)

            # Notify admin
            try:
                admin_user = org.schooladmin_set.first()
                if admin_user and admin_user.user and admin_user.user.email:
                    send_task_completed_email(admin_user.user.email, memb.name, inst.task.title, str(inst.completed_at), note, org.name)
            except Exception:
                pass

            _msg.success(request, "Task marked as Completed!")

        elif action == 'not_completed':
            reason = request.POST.get('not_done_reason', '')
            detail = request.POST.get('not_done_detail', '')
            if not reason:
                _msg.error(request, "Please select a reason for not completing the task.")
                return redirect('staff:my_tasks')
            inst.status = 'not_completed'
            inst.not_done_reason = reason
            inst.not_done_detail = detail
            inst.save(update_fields=['status', 'not_done_reason', 'not_done_detail', 'updated_at'])
            TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='not_completed', note=f'{reason}: {detail}')
            _msg.success(request, "Task status saved.")

        return redirect('staff:my_tasks')


# ── RESIGNATION ────────────────────────────────────────────────────
from handle.models import ResignationRecord

class StaffResignationView(LoginRequiredMixin, View):
    template_name = 'staff/my_resignation.html'

    def _get_member_or_redirect(self, request):
        try:
            org = request.user.staff.org
        except Exception:
            return None, None, redirect('management:login')
        memb = getattr(request.user.staff, 'member', None)
        if not memb:
            messages.error(request, "No member profile linked to your account.")
            return None, None, redirect('staff:dashboard')
        return org, memb, None

    def get(self, request, *args, **kwargs):
        org, memb, err = self._get_member_or_redirect(request)
        if err:
            return err
        resignations = ResignationRecord.objects.filter(org=org, member=memb)
        has_pending = resignations.filter(status__in=['pending', 'approved']).exists()
        return render(request, self.template_name, {
            'org': org,
            'memb': memb,
            'resignations': resignations,
            'has_pending': has_pending,
        })

    def post(self, request, *args, **kwargs):
        org, memb, err = self._get_member_or_redirect(request)
        if err:
            return err

        # Block if already pending/approved
        if ResignationRecord.objects.filter(org=org, member=memb, status__in=['pending', 'approved']).exists():
            messages.error(request, "You already have an active resignation application.")
            return redirect('staff:my_resignation')

        resignation_date_str = request.POST.get('resignation_date', '')
        reason = request.POST.get('reason', '').strip()
        notice_days = int(request.POST.get('notice_period_days', 30))

        if not resignation_date_str or not reason:
            messages.error(request, "Please fill in all required fields.")
            return redirect('staff:my_resignation')

        try:
            resignation_date = datetime.datetime.strptime(resignation_date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('staff:my_resignation')

        import datetime as _dt
        last_working_day = resignation_date + _dt.timedelta(days=notice_days)

        ResignationRecord.objects.create(
            org=org,
            member=memb,
            resignation_date=resignation_date,
            notice_period_days=notice_days,
            last_working_day=last_working_day,
            reason=reason,
            status='pending',
            self_applied=True,
        )

        # Notify admin via email if possible
        try:
            from school.email_utils import send_resignation_status_email
            admin_user = org.schooladmin_set.first()
            if admin_user and admin_user.user and admin_user.user.email:
                send_resignation_status_email(
                    admin_user.user.email,
                    memb.name,
                    str(resignation_date),
                    'Submitted',
                    reason,
                    org.name,
                )
        except Exception:
            pass

        messages.success(request, "Your resignation application has been submitted. Admin will review it shortly.")
        return redirect('staff:my_resignation')
