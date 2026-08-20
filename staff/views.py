from django.shortcuts import redirect, render
from django.views import View
from django.db.models import Count
from school.decorators import feature_required, perm_required, FeatureRequiredMixin, PermRequiredMixin
from school.nepali_utils import to_bs_display
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

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
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
from .forms import PortalProfileForm


class PortalProfileView(LoginRequiredMixin, View):
    """Self-service profile for staff, teachers, students, and trainees."""

    login_url = "/"
    template_name = "staff/profile.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.user_type != "3":
            messages.error(request, "This profile page is for portal accounts.")
            return redirect("management:homepage")
        staff_profile = getattr(request.user, "staff", None)
        if request.user.is_authenticated and (
            staff_profile is None or staff_profile.member_id is None
        ):
            messages.error(
                request,
                "No member profile is linked to your account. Contact your administrator.",
            )
            return redirect("staff:dashboard")
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _form_role(memb):
        if memb.member_type in ("student", "trainee"):
            return "student"
        if memb.member_type == "teacher":
            return "teacher"
        return "staff"

    def _context(self, request, form):
        staff_profile = request.user.staff
        memb = staff_profile.member
        completion_fields = (
            memb.name,
            request.user.email,
            memb.phone,
            memb.address,
            memb.date_of_birth,
            memb.photo,
        )
        completed = sum(bool(value) for value in completion_fields)
        return {
            "form": form,
            "memb": memb,
            "org": staff_profile.org,
            "profile_role": self._form_role(memb),
            "profile_completion_pct": round(
                completed / len(completion_fields) * 100
            ),
            "profile_courses": memb.courses.filter(
                org=staff_profile.org
            ).order_by("name"),
        }

    def get(self, request):
        memb = request.user.staff.member
        form = PortalProfileForm(
            instance=memb,
            portal_role=self._form_role(memb),
        )
        return render(request, self.template_name, self._context(request, form))

    def post(self, request):
        memb = request.user.staff.member
        form = PortalProfileForm(
            request.POST,
            request.FILES,
            instance=memb,
            portal_role=self._form_role(memb),
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile was updated successfully.")
            return redirect("staff:profile")
        messages.error(request, "Please correct the highlighted profile details.")
        return render(request, self.template_name, self._context(request, form))


class StaffLeaveView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'leave'
    required_perm = 'can_view_leave'
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
            
        my_leaves = list(LeaveReport.objects.filter(member=memb, org=org).select_related('leave_type').order_by('-gap_start')[:50])
        nepali_enabled = org.nepali_date
        if nepali_enabled:
            for leave in my_leaves:
                leave.start_display = to_bs_display(leave.gap_start)
                leave.end_display = to_bs_display(leave.gap_end)
        else:
            for leave in my_leaves:
                leave.start_display = leave.gap_start.strftime("%Y-%m-%d") if leave.gap_start else ""
                leave.end_display = leave.gap_end.strftime("%Y-%m-%d") if leave.gap_end else ""
        return render(request, self.template_name, {
            'leave_types': balance_list, 'my_leaves': my_leaves, 'nepali_enabled': nepali_enabled,
        })

    def post(self, request, *args, **kwargs):
        from school.features import has_perm
        if not has_perm(request.user, 'can_request_leave'):
            messages.error(request, "You don't have permission to request leave.")
            return redirect('staff:apply_leave')

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
        leave_type = LeaveType.objects.get(id=lt_id)
        report = LeaveReport.objects.create(
            member=memb,
            org=org,
            leave_type=leave_type,
            gap_start=start_date,
            gap_end=end_date,
            reason=formatted_reason,
            approved=False # Pending admin approval
        )

        from management.models import Schooladmin
        admin_emails = list(
            Schooladmin.objects.filter(org=org).select_related('admin')
            .values_list('admin__email', flat=True)
        )
        admin_emails = [e for e in admin_emails if e]
        if admin_emails:
            from school.email_utils import send_leave_submitted_email
            send_leave_submitted_email(
                admin_emails=admin_emails,
                member_name=memb.name,
                leave_type=leave_type.name,
                start=str(start_date),
                end=str(end_date),
                reason=formatted_reason,
                org_name=org.name,
                org=org,
                related_object_id=report.id,
            )

        messages.success(request, "Your leave request has been submitted and is pending approval.")
        return redirect('staff:apply_leave')


class StaffLeaveDeleteView(LoginRequiredMixin, View):
    """Let a staff/student member cancel their own leave request, but only
    while it's still pending — once reviewed (approved or rejected), it's
    part of the record and can't be pulled back."""

    def post(self, request, pk, *args, **kwargs):
        memb = getattr(request.user.staff, 'member', None)
        if not memb:
            messages.error(request, "No member profile linked to your account.")
            return redirect('staff:dashboard')
        org = request.user.staff.org

        leave = get_object_or_404(LeaveReport, pk=pk, member=memb, org=org)
        if leave.approved or leave.rejected:
            messages.error(request, "Can't delete a leave request that's already been reviewed.")
        else:
            leave_type_name = leave.leave_type.name if leave.leave_type else 'Leave'
            gap_start, gap_end, leave_id = leave.gap_start, leave.gap_end, leave.id
            leave.delete()

            if memb.email:
                from school.email_utils import send_leave_cancelled_email
                send_leave_cancelled_email(
                    email=memb.email,
                    name=memb.name,
                    leave_type=leave_type_name,
                    start=str(gap_start),
                    end=str(gap_end),
                    org_name=org.name,
                    org=org,
                    related_object_id=leave_id,
                )
            messages.success(request, "Leave request deleted.")
        return redirect('staff:apply_leave')


class MyAttendanceReportView(LoginRequiredMixin, View):
    template_name = 'staff/my_report.html'

    def get(self, request, *args, **kwargs):
        try:
            memb = request.user.staff.member 
            org = request.user.staff.org
        except AttributeError:
            return render(request, 'staff/my_report.html', {'error': "No associated member profile found."})

        nepali_enabled = getattr(org, 'nepali_date', False)

        # Quick-filter presets (mirrors the admin monthly report's This Month /
        # Last Month buttons) — only apply when no explicit range was typed in.
        preset = request.GET.get('preset', '')
        date_from_str = request.GET.get('date_from')
        date_to_str = request.GET.get('date_to')
        if preset and not (date_from_str and date_to_str):
            today = datetime.date.today()
            if preset == 'last_month':
                last_day_prev = today.replace(day=1) - datetime.timedelta(days=1)
                date_from_str = last_day_prev.replace(day=1).strftime("%Y-%m-%d")
                date_to_str = last_day_prev.strftime("%Y-%m-%d")
            else:  # this_month
                date_from_str = today.replace(day=1).strftime("%Y-%m-%d")
                date_to_str = today.strftime("%Y-%m-%d")

        # Date-range filter (explicit start/end date, e.g. spanning a whole
        # month or crossing two months) takes priority over the month picker
        # when both date_from and date_to are supplied.
        date_from = date_to = None
        if date_from_str and date_to_str:
            try:
                date_from = datetime.datetime.strptime(date_from_str, "%Y-%m-%d").date()
                date_to = datetime.datetime.strptime(date_to_str, "%Y-%m-%d").date()
            except ValueError:
                date_from = date_to = None

        # Month Filtering Logic (fallback when no explicit date range is given)
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

        # Fetch Data Filtered by the date range if given, else by month
        if date_from and date_to:
            attendance_logs = AttendanceRecord.objects.filter(
                mem=memb,
                scanned_time__date__gte=date_from,
                scanned_time__date__lte=date_to,
            ).order_by('-scanned_time')
            leave_history = LeaveReport.objects.filter(
                member=memb,
                gap_start__lte=date_to,
                gap_end__gte=date_from,
            ).order_by('-gap_start')
        else:
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

        # Calculate Stats for the selected period
        # Using .dates() to count unique days present (in case of multiple scans per day)
        total_present = attendance_logs.dates('scanned_time', 'day').count()

        logs = list(attendance_logs)
        leaves = list(leave_history)
        if nepali_enabled:
            from django.utils import timezone as _tz
            for log in logs:
                log.scanned_time_np = to_bs_display(_tz.localtime(log.scanned_time).date())
            for leave in leaves:
                leave.start_display = to_bs_display(leave.gap_start)
                leave.end_display = to_bs_display(leave.gap_end)
        else:
            for leave in leaves:
                leave.start_display = leave.gap_start.strftime("%Y-%m-%d") if leave.gap_start else ""
                leave.end_display = leave.gap_end.strftime("%Y-%m-%d") if leave.gap_end else ""

        from school.print_settings import get_print_preference
        context = {
            'memb': memb,
            'logs': logs,
            'leaves': leaves,
            'total_present': total_present,
            'org': org,
            'selected_month': month_str, # Passed to the HTML to keep the date picker accurate
            'date_from': date_from_str or '',
            'date_to': date_to_str or '',
            'nepali_enabled': nepali_enabled,
            'active_preset': preset,
            'print_preference': get_print_preference(request.user, 'staff_my_report', org=org),
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
        members = member.objects.filter(classification=clas, org=org).exclude(status='dumped')

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


# ─── 4b. Field Visits (send my location) ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_field_visit_submit(request):
    """
    Record a field visit location, with an optional report.
    Body (multipart for attachment): { member_id, latitude, longitude, accuracy(optional), note(optional) }
    File: attachment (optional)
    """
    from school.features import has_feature, has_perm
    from handle.models import FieldVisit, FieldVisitReport

    lat = request.data.get('latitude')
    lon = request.data.get('longitude')

    if lat in (None, '') or lon in (None, ''):
        return Response({"error": "Missing latitude or longitude."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        org = get_staff_org(request.user)
        if not has_feature(org, 'field_visits'):
            return Response({"error": "Field visits are not enabled for your organization."}, status=status.HTTP_403_FORBIDDEN)
        if not has_perm(request.user, 'can_send_location'):
            return Response({"error": "You don't have permission to send location."}, status=status.HTTP_403_FORBIDDEN)

        staff_profile = request.user.staff
        memb = staff_profile.member
        if memb is None or memb.org_id != org.id:
            return Response(
                {"error": "No valid staff member profile was found."},
                status=status.HTTP_403_FORBIDDEN,
            )
        accuracy = request.data.get('accuracy')
        try:
            accuracy = float(accuracy) if accuracy not in (None, '') else None
        except (TypeError, ValueError):
            accuracy = None

        visit = FieldVisit.objects.create(
            org=org, member=memb, latitude=float(lat), longitude=float(lon),
            accuracy_meters=accuracy, created_by=request.user,
        )

        note = request.data.get('note', '')
        attachment = request.FILES.get('attachment')
        has_report = bool((note or '').strip() or attachment)
        if has_report:
            FieldVisitReport.objects.create(visit=visit, note=note, attachment=attachment)

        return Response(
            {"status": "success", "visit_id": visit.id, "report_attached": has_report},
            status=status.HTTP_201_CREATED
        )

    except member.DoesNotExist:
        return Response({"error": "Member not found."}, status=status.HTTP_404_NOT_FOUND)
    except (TypeError, ValueError):
        return Response({"error": "Invalid latitude/longitude."}, status=status.HTTP_400_BAD_REQUEST)
    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        return Response(
            {"error": "Unable to record the field visit."},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ─── 4c. Client Follow-Up ──────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_client_list(request):
    """
    Returns clients for the org, optionally filtered by client_number/client_org.
    Query params: ?client_number=&client_org=
    """
    from django.db.models import Q
    from school.features import has_feature, has_perm
    from handle.models import Client

    try:
        org = get_staff_org(request.user)
        if not has_feature(org, 'clients'):
            return Response({"error": "Client module is not enabled for your organization."}, status=status.HTTP_403_FORBIDDEN)
        if not has_perm(request.user, 'can_view_clients'):
            return Response({"error": "You don't have permission to view clients."}, status=status.HTTP_403_FORBIDDEN)

        qs = Client.objects.filter(org=org, is_active=True, created_by=request.user)
        client_number = request.query_params.get('client_number')
        client_org = request.query_params.get('client_org')
        if client_number:
            qs = qs.filter(client_number__icontains=client_number)
        if client_org:
            qs = qs.filter(client_org_name__icontains=client_org)

        data = []
        for c in qs:
            latest = c.latest_follow_up()
            data.append({
                "id": c.id,
                "client_number": c.client_number,
                "client_org_name": c.client_org_name,
                "priority": c.priority,
                "contact_person": c.contact_person,
                "phone": c.phone,
                "follow_up_count": c.follow_up_count(),
                "latest_follow_up_date": latest.follow_up_date.strftime("%Y-%m-%d") if latest else None,
                "next_follow_up_date": latest.next_follow_up_date.strftime("%Y-%m-%d") if latest and latest.next_follow_up_date else None,
            })
        return Response({"clients": data}, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_log_followup(request):
    """
    Log a follow-up for a client. Creates the client if client_id is omitted
    and client_number/client_org_name are provided.
    Body: { client_id (or client_number+client_org_name), feedback, follow_up_date, next_follow_up_date(optional) }
    """
    from school.features import has_feature, has_perm
    from handle.models import Client, ClientFollowUp

    try:
        org = get_staff_org(request.user)
        if not has_feature(org, 'clients'):
            return Response({"error": "Client module is not enabled for your organization."}, status=status.HTTP_403_FORBIDDEN)
        if not has_perm(request.user, 'can_manage_clients'):
            return Response({"error": "You don't have permission to manage clients."}, status=status.HTTP_403_FORBIDDEN)

        client_id = request.data.get('client_id')
        if client_id:
            try:
                client = Client.objects.get(pk=client_id, org=org, created_by=request.user)
            except Client.DoesNotExist:
                return Response({"error": "Client not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            client_number = (request.data.get('client_number') or '').strip()
            client_org_name = (request.data.get('client_org_name') or '').strip()
            if not client_org_name:
                return Response({"error": "client_id or client_org_name is required."}, status=status.HTTP_400_BAD_REQUEST)
            if client_number and Client.objects.filter(org=org, client_number=client_number).exists():
                return Response({"error": f"Client number '{client_number}' already exists."}, status=status.HTTP_400_BAD_REQUEST)
            client = Client.create_for_org(
                org=org, client_number=client_number,
                client_org_name=client_org_name, created_by=request.user,
            )

        feedback = (request.data.get('feedback') or '').strip()
        if not feedback:
            return Response({"error": "feedback is required."}, status=status.HTTP_400_BAD_REQUEST)

        follow_up_date = request.data.get('follow_up_date') or timezone.now().date()
        next_follow_up_date = request.data.get('next_follow_up_date') or None

        priority = (request.data.get('priority') or 'medium').strip()
        if priority not in dict(ClientFollowUp.PRIORITY_CHOICES):
            return Response({"error": "Invalid follow-up priority."}, status=status.HTTP_400_BAD_REQUEST)

        # The actor is always derived from the authenticated profile.  Never
        # accept a posted member id for CRM attribution.
        memb = getattr(getattr(request.user, 'staff', None), 'member', None)

        fu = ClientFollowUp.objects.create(
            client=client, org=org, visited_by=memb, feedback=feedback,
            priority=priority,
            follow_up_date=follow_up_date, next_follow_up_date=next_follow_up_date,
            created_by=request.user,
        )
        return Response({"status": "success", "client_id": client.id, "follow_up_id": fu.id}, status=status.HTTP_201_CREATED)

    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_clients_due_followup(request):
    """Returns clients whose latest follow-up's next_follow_up_date is today or overdue, soonest/most-overdue first."""
    from django.db.models import Case, IntegerField, OuterRef, Subquery, Value, When
    from school.features import has_feature, has_perm
    from handle.models import Client, ClientFollowUp

    try:
        org = get_staff_org(request.user)
        if not has_feature(org, 'clients'):
            return Response({"error": "Client module is not enabled for your organization."}, status=status.HTTP_403_FORBIDDEN)
        if not has_perm(request.user, 'can_view_clients'):
            return Response({"error": "You don't have permission to view clients."}, status=status.HTTP_403_FORBIDDEN)

        today = timezone.now().date()
        latest = ClientFollowUp.objects.filter(client=OuterRef('pk')).order_by('-follow_up_date', '-id')
        requested_priority = request.query_params.get('priority', '').strip()
        clients_due = (
            Client.objects.filter(org=org, is_active=True, created_by=request.user)
            .annotate(latest_next=Subquery(latest.values('next_follow_up_date')[:1]))
            .filter(latest_next__isnull=False, latest_next__lte=today)
            .annotate(priority_order=Case(
                When(priority='high', then=Value(0)),
                When(priority='medium', then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            ))
            .order_by('priority_order', 'latest_next')
        )
        if requested_priority in dict(Client.PRIORITY_CHOICES):
            clients_due = clients_due.filter(priority=requested_priority)

        data = [
            {
                "id": c.id,
                "client_number": c.client_number,
                "client_org_name": c.client_org_name,
                "priority": c.priority,
                "next_follow_up_date": c.latest_next.strftime("%Y-%m-%d"),
            }
            for c in clients_due
        ]
        return Response({"clients_due": data}, status=status.HTTP_200_OK)

    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)


# ─── 5. QR Code Attendance ────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_get_qr_codes(request):
    """Deprecated: reusable static QR tokens are intentionally disabled."""
    return Response(
        {
            "error": "Static QR codes are no longer supported.",
            "replacement": "/staff/api/staff/qr-scan/",
        },
        status=status.HTTP_410_GONE,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_qr_checkin(request):
    """Deprecated: the dynamic session endpoint derives the member from JWT."""
    return Response(
        {
            "error": "Reusable QR check-in is no longer supported.",
            "replacement": "/staff/api/staff/qr-scan/",
        },
        status=status.HTTP_410_GONE,
    )


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
        members = member.objects.filter(classification=clas, org=org).exclude(status='dumped')

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
        members = member.objects.filter(classification=clas, org=org).exclude(status='dumped')

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
        return redirect('management:homepage')
    try:
        org = request.user.staff.org
    except Exception:
        messages.error(request, "Your account does not have a staff profile linked. Contact admin.")
        return redirect('management:homepage')

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

        context = {
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
            'dash_notices': notices_for_member(memb, org, limit=5),
            'unread_notices': unread_notice_count(memb, org),
        }

        # Academic Management tiles — computed only when the org actually has
        # the feature, so a disabled org pays zero extra queries.
        if has_feature(org, 'academic_management'):
            from handle.models import (
                RoutinePeriod, HomeworkStatus, Assignment, AssignmentSubmission,
                CourseMaterial, TeachingLog, Event, StudentCourseEnrollment,
                SubjectAttendanceRecord,
            )
            from handle.notifications import unread_notification_count

            active_enrollments = StudentCourseEnrollment.objects.filter(
                org=org,
                student=memb,
                start_date__lte=today,
            ).exclude(status='cancelled').filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).select_related(
                'academic_year', 'course', 'classification', 'section',
            ).order_by('course__name', 'classification__name', 'section__name')

            academic_scope = Q(pk__in=[])
            subject_scope = Q(pk__in=[])
            assignment_scope = Q(pk__in=[])
            for enrollment in active_enrollments:
                section_scope = Q(section__isnull=True)
                subject_section_scope = Q(subject__section__isnull=True)
                if enrollment.section_id:
                    section_scope |= Q(section=enrollment.section)
                    subject_section_scope |= Q(subject__section=enrollment.section)
                academic_scope |= (
                    (
                        Q(subject__course=enrollment.course)
                        | Q(subject__course__isnull=True)
                    )
                    & Q(classification=enrollment.classification)
                    & section_scope
                )
                subject_scope |= (
                    (
                        Q(subject__course=enrollment.course)
                        | Q(subject__course__isnull=True)
                    )
                    & Q(subject__classification=enrollment.classification)
                    & subject_section_scope
                )
                assignment_scope |= (
                    (Q(course=enrollment.course) | Q(course__isnull=True))
                    & Q(classification=enrollment.classification)
                    & section_scope
                )
            if not active_enrollments.exists():
                current_course_ids = memb.courses.filter(org=org).values_list('pk', flat=True)
                section_scope = Q(section__isnull=True)
                subject_section_scope = Q(subject__section__isnull=True)
                if memb.section_id:
                    section_scope |= Q(section=memb.section)
                    subject_section_scope |= Q(subject__section=memb.section)
                academic_scope = (
                    (
                        Q(subject__course_id__in=current_course_ids)
                        | Q(subject__course__isnull=True)
                    )
                    & Q(classification=memb.classification)
                    & section_scope
                )
                subject_scope = (
                    (
                        Q(subject__course_id__in=current_course_ids)
                        | Q(subject__course__isnull=True)
                    )
                    & Q(subject__classification=memb.classification)
                    & subject_section_scope
                )
                assignment_scope = (
                    (Q(course_id__in=current_course_ids) | Q(course__isnull=True))
                    & Q(classification=memb.classification)
                    & section_scope
                )

            student_periods = RoutinePeriod.objects.filter(
                academic_scope, org=org, is_active=True,
            ).select_related(
                'academic_year', 'subject__course', 'teacher', 'classification', 'section',
            ).order_by('period_number')
            from handle.academics import student_routine_reminders
            student_routine_data = student_routine_reminders(
                student_periods, on_date=today,
            )
            todays_classes = student_routine_data['today_periods']

            homework_pending = HomeworkStatus.objects.filter(student=memb, homework__org=org, status='pending').count()

            assignment_qs = Assignment.objects.filter(
                assignment_scope, org=org, visibility='published',
            )
            submitted_ids = set(AssignmentSubmission.objects.filter(student=memb).values_list('assignment_id', flat=True))
            assignments_pending = assignment_qs.exclude(id__in=submitted_ids).filter(due_date__gte=today).count()

            recent_materials = CourseMaterial.objects.filter(
                subject_scope, org=org, is_active=True,
            ).select_related('subject__course').order_by('-created_at')[:5]

            teaching_log_qs = TeachingLog.objects.filter(
                academic_scope, org=org, status='approved',
            )
            recent_teaching_logs = teaching_log_qs.select_related(
                'teacher', 'subject__course', 'classification', 'section',
            ).order_by('-date', '-pk')[:5]

            month_start = today.replace(day=1)
            subject_attendance = SubjectAttendanceRecord.objects.filter(
                member=memb,
                org=org,
                teaching_log__date__gte=month_start,
                teaching_log__date__lte=today,
            )
            attendance_counts = {
                row['status']: row['total']
                for row in subject_attendance.values('status').annotate(total=Count('pk'))
            }
            attendance_total = sum(attendance_counts.values())
            attendance_present_like = (
                attendance_counts.get('present', 0) + attendance_counts.get('late', 0)
            )
            subject_attendance_pct = round(
                attendance_present_like / attendance_total * 100, 1
            ) if attendance_total else 0
            recent_subject_attendance = subject_attendance.select_related(
                'teaching_log__subject__course', 'teaching_log__teacher',
            ).order_by('-teaching_log__date', '-teaching_log__period')[:8]

            upcoming_events = Event.objects.filter(org=org, status='upcoming').order_by('start_date')[:5]

            # Profile completion — simple derived percentage, no new model.
            required_fields = ['name', 'email', 'phone', 'address', 'date_of_birth', 'photo', 'gender', 'guardian_name', 'guardian_phone']
            filled = sum(1 for f in required_fields if getattr(memb, f, None))
            profile_completion_pct = round(filled / len(required_fields) * 100)

            context.update({
                'todays_classes': todays_classes,
                'student_active_routine': student_routine_data['active'],
                'student_routine_reminder': student_routine_data['attention'],
                'student_next_routine': student_routine_data['next_period'],
                'homework_pending': homework_pending,
                'assignments_pending': assignments_pending,
                'recent_materials': recent_materials,
                'recent_teaching_logs': recent_teaching_logs,
                'student_enrollments': active_enrollments,
                'subject_attendance_counts': attendance_counts,
                'subject_attendance_total': attendance_total,
                'subject_attendance_pct': subject_attendance_pct,
                'recent_subject_attendance': recent_subject_attendance,
                'upcoming_events': upcoming_events,
                'unread_notifications': unread_notification_count(memb),
                'profile_completion_pct': profile_completion_pct,
                'book_issues': memb.book_issues.select_related('book').order_by('-issue_date')[:5] if has_feature(org, 'library') else [],
            })

        return render(request, 'staff/student_dashboard.html', context)

    # Teaching staff / employee dashboard
    today = datetime.date.today()
    total_present_today = 0
    total_members_assigned = 0
    if clas.exists():
        class_ids = clas.values_list('classification_id', flat=True)
        members_in_classes = member.objects.filter(classification_id__in=class_ids, org=org).exclude(status='dumped')
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

    is_teacher = bool(memb and memb.member_type == 'teacher')
    teacher_academic = {
        'teacher_assignments': [],
        'teacher_assigned_course_count': 0,
        'teacher_assigned_subject_count': 0,
        'teacher_roster_student_count': 0,
        'teacher_today_periods': [],
        'teacher_routine_reminder': None,
        'teacher_next_routine': None,
        'teacher_weekly_routine': [],
        'teacher_recent_sessions': [],
        'teacher_draft_sessions': 0,
        'teacher_submitted_sessions': 0,
        'teacher_rejected_sessions': 0,
        'teacher_open_assignments': 0,
        'teacher_ungraded_submissions': 0,
        'teacher_active_homework': 0,
        'teacher_exam_count': 0,
    }
    if has_feature(org, 'academic_management'):
        from handle.academics import roster_for_subject, teacher_routine_reminders
        from handle.models import (
            AcademicYear, Assignment, AssignmentSubmission, ExamTerm, Homework,
            Subject, SubjectTeacherAssignment, TeachingLog,
        )

        current_year = AcademicYear.objects.filter(
            org=org, is_current=True, status='active',
        ).order_by('-start_date', '-pk').first()
        active_assignments = SubjectTeacherAssignment.objects.filter(
            org=org, teacher=request.user, status='active', start_date__lte=today,
            subject__status='active',
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        )
        if current_year:
            active_assignments = active_assignments.filter(
                Q(academic_year=current_year) | Q(academic_year__isnull=True)
            )
        active_assignments = active_assignments.select_related(
            'academic_year', 'course', 'classification', 'section', 'subject',
        ).order_by('course__name', 'classification__name', 'section__name', 'subject__name')
        assigned_subject_ids = set(active_assignments.values_list('subject_id', flat=True))
        legacy_subject_ids = set(Subject.objects.filter(
            org=org, teacher=request.user, teacher_assignments__isnull=True,
            status='active',
        ).values_list('pk', flat=True))
        subject_ids = assigned_subject_ids | legacy_subject_ids
        is_teacher = is_teacher or bool(subject_ids)

        routine_data = teacher_routine_reminders(
            org,
            request.user,
            subject_ids,
            assignment_ids=set(active_assignments.values_list('pk', flat=True)),
            on_date=today,
            academic_year=current_year,
        )
        today_periods = routine_data['today_periods']

        roster_student_ids = set()
        for assignment in active_assignments:
            roster_student_ids.update(
                roster_for_subject(
                    org, assignment.subject, assignment.classification,
                    assignment.section, attendance_date=today,
                    academic_year=assignment.academic_year,
                ).values_list('pk', flat=True)
            )
        session_qs = TeachingLog.objects.filter(
            org=org, teacher=request.user,
        )
        active_assignment_ids = set(
            active_assignments.values_list('pk', flat=True)
        )
        teacher_assignment_qs = Assignment.objects.filter(
            org=org,
            teacher_assignment_id__in=active_assignment_ids,
        )
        teacher_homework_qs = Homework.objects.filter(
            org=org,
            teacher_assignment_id__in=active_assignment_ids,
        )
        teacher_academic.update({
            'teacher_assignments': active_assignments,
            'teacher_assigned_course_count': Subject.objects.filter(
                org=org, pk__in=subject_ids,
            ).exclude(course=None).values('course_id').distinct().count(),
            'teacher_assigned_subject_count': len(subject_ids),
            'teacher_roster_student_count': len(roster_student_ids),
            'teacher_today_periods': today_periods,
            'teacher_routine_reminder': routine_data['attention'],
            'teacher_next_routine': routine_data['next_period'],
            'teacher_weekly_routine': routine_data['periods'],
            'teacher_recent_sessions': session_qs.select_related(
                'course', 'subject', 'classification', 'section',
            ).order_by('-date', '-pk')[:8],
            'teacher_draft_sessions': session_qs.filter(status='draft').count(),
            'teacher_submitted_sessions': session_qs.filter(status='submitted').count(),
            'teacher_rejected_sessions': session_qs.filter(status='rejected').count(),
            'teacher_open_assignments': teacher_assignment_qs.filter(
                status='open',
            ).count(),
            'teacher_ungraded_submissions': AssignmentSubmission.objects.filter(
                assignment__in=teacher_assignment_qs,
            ).exclude(status='graded').count(),
            'teacher_active_homework': teacher_homework_qs.filter(
                status='active',
            ).count(),
            'teacher_exam_count': ExamTerm.objects.filter(
                org=org,
                classification_id__in=active_assignments.values(
                    'classification_id'
                ),
                status__in=('draft', 'marks_entry'),
            ).distinct().count(),
        })

    context = {
        'clas': clas,
        'org': org,
        'memb': memb,
        'is_student': False,
        'is_teacher': is_teacher,
        'dashboard_role': 'teacher' if is_teacher else 'staff',
        'dashboard_role_label': 'Teacher Workspace' if is_teacher else 'Staff Workspace',
        'total_present_today': total_present_today,
        'total_members_assigned': total_members_assigned,
        'payslips': payslips,
        'pending_gaps': pending_gaps,
        'recent_attendance_logs': recent_attendance_logs,
        'my_tasks_today': my_tasks_today,
        'my_tasks_pending': my_tasks_pending,
        'my_tasks_overdue': my_tasks_overdue,
        'today': today,
        'dash_notices': notices_for_member(memb, org, limit=5),
        'unread_notices': unread_notice_count(memb, org),
    }
    context.update(teacher_academic)
    return render(request, 'staff/Sdashboard.html', context)


class StaffTeacherRoutineView(
    LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View
):
    """Read-only weekly routine for an assigned teaching staff account."""
    required_feature = 'academic_management'
    required_perm = 'can_view_attendance'
    template_name = 'staff/academic/teacher_routine.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.user_type == '3':
            memb = getattr(getattr(request.user, 'staff', None), 'member', None)
            if memb and memb.member_type in ('student', 'trainee'):
                messages.error(request, "This routine page is for teaching staff.")
                return redirect('staff:student_routine')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from handle.academics import teacher_routine_reminders
        from handle.models import AcademicYear, RoutinePeriod, Subject, SubjectTeacherAssignment

        org = request.user.staff.org
        today = timezone.localdate()
        current_year = AcademicYear.objects.filter(
            org=org, is_current=True, status='active',
        ).order_by('-start_date', '-pk').first()
        active_assignments = SubjectTeacherAssignment.objects.filter(
            org=org,
            teacher=request.user,
            status='active',
            start_date__lte=today,
            subject__status='active',
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        )
        if current_year:
            active_assignments = active_assignments.filter(
                Q(academic_year=current_year) | Q(academic_year__isnull=True)
            )
        subject_ids = set(active_assignments.values_list('subject_id', flat=True))
        subject_ids.update(Subject.objects.filter(
            org=org,
            teacher=request.user,
            teacher_assignments__isnull=True,
            status='active',
        ).values_list('pk', flat=True))
        routine_data = teacher_routine_reminders(
            org,
            request.user,
            subject_ids,
            assignment_ids=set(active_assignments.values_list('pk', flat=True)),
            on_date=today,
            academic_year=current_year,
        )
        days = list(RoutinePeriod.DAY_CHOICES)
        grid = {
            day_num: [
                period for period in routine_data['periods']
                if period.day_of_week == day_num
            ]
            for day_num, _ in days
        }
        return render(request, self.template_name, {
            'org': org,
            'today': today,
            'current_day': (today.weekday() + 1) % 7,
            'days': days,
            'grid': grid,
            'today_periods': routine_data['today_periods'],
            'routine_reminder': routine_data['attention'],
            'next_routine': routine_data['next_period'],
        })


# 2. Add the Location Check-in View
class StaffLocationCheckinView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'gps'
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


# ─── Field Visits (send my location) ──────────────────────────────────────────

from handle.models import FieldVisit, FieldVisitReport, Client, ClientFollowUp
from school.features import has_feature, get_staff_permissions


class StaffSendLocationView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    template_name = 'staff/send_location.html'
    required_feature = 'field_visits'
    required_perm = 'can_send_location'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        perms = get_staff_permissions(request.user)
        can_view_clients = (
            has_feature(org, 'clients')
            and getattr(perms, 'can_view_clients', False)
        )
        can_manage_clients = (
            has_feature(org, 'clients')
            and getattr(perms, 'can_manage_clients', False)
        )
        clients = []
        if can_view_clients or can_manage_clients:
            clients = Client.objects.filter(
                org=org, is_active=True, created_by=request.user,
            ).order_by('-priority', 'client_org_name')
        return render(request, self.template_name, {
            'clients': clients,
            'can_view_clients': can_view_clients,
            'can_manage_clients': can_manage_clients,
            'client_priority_choices': Client.PRIORITY_CHOICES,
        })

    def post(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        perms = get_staff_permissions(request.user)

        try:
            lat = float(request.POST.get('latitude'))
            lon = float(request.POST.get('longitude'))
        except (TypeError, ValueError):
            messages.error(request, "Invalid GPS coordinates received.")
            return redirect('staff:send_location')

        accuracy = request.POST.get('accuracy')
        try:
            accuracy = float(accuracy) if accuracy else None
        except (TypeError, ValueError):
            accuracy = None

        area_name = request.POST.get('area_name', '').strip()[:300]

        # Optional client and follow-up captured alongside the location.
        client = None
        follow_up_logged = False
        client_id = request.POST.get('client_id')
        feedback = request.POST.get('feedback', '').strip()
        can_manage_clients = (
            has_feature(org, 'clients') and getattr(perms, 'can_manage_clients', False)
        )
        can_view_clients = (
            has_feature(org, 'clients') and getattr(perms, 'can_view_clients', False)
        )
        if (can_manage_clients or can_view_clients) and client_id and client_id != 'new':
            client = Client.objects.filter(pk=client_id, org=org, created_by=request.user).first()
        new_client_name = request.POST.get('client_org_name', '').strip()
        client_priority = request.POST.get('client_priority', 'medium')
        log_follow_up = request.POST.get('log_follow_up') == 'on'
        if log_follow_up and not can_manage_clients:
            messages.error(request, "You do not have permission to log client follow-ups.")
            return redirect('staff:send_location')
        if log_follow_up and (
            (not client_id and not new_client_name) or not feedback
        ):
            messages.error(
                request,
                "Choose or create a client and enter feedback, or select Skip follow-up.",
            )
            return redirect('staff:send_location')
        if client_priority not in dict(Client.PRIORITY_CHOICES):
            client_priority = 'medium'
        client_phone = ''.join(
            char for char in request.POST.get('client_phone', '') if char.isdigit()
        )
        if new_client_name:
            if not can_manage_clients:
                messages.error(request, "You do not have permission to add client data.")
                return redirect('staff:send_location')
            if request.POST.get('client_phone') and not client_phone:
                messages.error(request, "Client phone must contain digits.")
                return redirect('staff:send_location')

        if log_follow_up and (
            (not client and not new_client_name) or not feedback
        ):
            messages.error(
                request,
                "Choose or create a client and enter feedback, or select Skip follow-up.",
            )
            return redirect('staff:send_location')

        follow_up_priority = request.POST.get('follow_up_priority', 'medium')
        if follow_up_priority not in dict(ClientFollowUp.PRIORITY_CHOICES):
            follow_up_priority = 'medium'

        note = request.POST.get('note', '').strip()
        attachment = request.FILES.get('attachment')
        from django.db import transaction
        with transaction.atomic():
            if not client and new_client_name:
                client = Client.create_for_org(
                    org=org,
                    client_number=request.POST.get('client_number', '').strip(),
                    client_org_name=new_client_name,
                    contact_person=request.POST.get('contact_person', '').strip(),
                    phone=int(client_phone) if client_phone else None,
                    address=request.POST.get('client_address', '').strip(),
                    priority=client_priority,
                    created_by=request.user,
                )
            visit = FieldVisit.objects.create(
                org=org, member=memb, latitude=lat, longitude=lon,
                area_name=area_name, accuracy_meters=accuracy,
                client=client, created_by=request.user,
            )

            if log_follow_up:
                ClientFollowUp.objects.create(
                    client=client, org=org, visited_by=memb, feedback=feedback,
                    priority=follow_up_priority,
                    follow_up_date=request.POST.get('follow_up_date') or datetime.date.today(),
                    next_follow_up_date=request.POST.get('next_follow_up_date') or None,
                    field_visit=visit, created_by=request.user,
                )
                follow_up_logged = True

            if note or attachment:
                FieldVisitReport.objects.create(visit=visit, note=note, attachment=attachment)

        if follow_up_logged:
            messages.success(request, "Location shared and client follow-up logged successfully.")
        elif note or attachment:
            messages.success(request, "Location and report sent successfully.")
        else:
            messages.success(request, "Location sent successfully.")

        return redirect('staff:dashboard')


# ─── Client Follow-Up ──────────────────────────────────────────────────────────

class StaffClientListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    template_name = 'staff/clients/client_list.html'
    required_feature = 'clients'
    required_perm = 'can_view_clients'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        # Staff only see clients they personally added, not the whole org's list.
        qs = Client.objects.filter(org=org, is_active=True, created_by=request.user)

        q = request.GET.get('q', '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(client_number__icontains=q) | Q(client_org_name__icontains=q))

        clients = [{'client': c, 'count': c.follow_up_count(), 'latest': c.latest_follow_up()} for c in qs]
        return render(request, self.template_name, {'org': org, 'clients': clients, 'q': q})


class StaffClientDetailView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    template_name = 'staff/clients/client_detail.html'
    required_feature = 'clients'
    required_perm = 'can_view_clients'

    def get(self, request, pk, *args, **kwargs):
        org = request.user.staff.org
        client = get_object_or_404(Client, pk=pk, org=org, created_by=request.user)
        follow_ups = client.follow_ups.select_related('visited_by').all()
        return render(request, self.template_name, {'org': org, 'client': client, 'follow_ups': follow_ups})


class StaffLogFollowUpView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    template_name = 'staff/clients/log_followup.html'
    required_feature = 'clients'
    required_perm = 'can_manage_clients'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        client_id = request.GET.get('client_id')
        client = None
        if client_id:
            client = Client.objects.filter(pk=client_id, org=org, created_by=request.user).first()
        clients = Client.objects.filter(org=org, is_active=True, created_by=request.user)
        return render(request, self.template_name, {'org': org, 'client': client, 'clients': clients})

    def post(self, request, *args, **kwargs):
        org = request.user.staff.org
        memb = request.user.staff.member

        client_id = request.POST.get('client_id')
        if client_id:
            client = get_object_or_404(Client, pk=client_id, org=org, created_by=request.user)
        else:
            client_number = request.POST.get('client_number', '').strip()
            client_org_name = request.POST.get('client_org_name', '').strip()
            if not client_org_name:
                messages.error(request, "Client organization name is required.")
                return redirect('staff:log_followup')
            if client_number and Client.objects.filter(org=org, client_number=client_number).exists():
                messages.error(request, f"Client number '{client_number}' already exists.")
                return redirect('staff:log_followup')
            client = Client.create_for_org(
                org=org, client_number=client_number, client_org_name=client_org_name,
                priority=(
                    request.POST.get('client_priority')
                    if request.POST.get('client_priority') in dict(Client.PRIORITY_CHOICES)
                    else 'medium'
                ),
                contact_person=request.POST.get('contact_person', '').strip(),
                phone=request.POST.get('phone') or None,
                email=request.POST.get('email') or None,
                address=request.POST.get('address', '').strip(),
                created_by=request.user,
            )

        feedback = request.POST.get('feedback', '').strip()
        follow_up_date = request.POST.get('follow_up_date') or datetime.date.today()
        next_follow_up_date = request.POST.get('next_follow_up_date') or None

        if not feedback:
            messages.error(request, "Feedback is required.")
            return redirect('staff:log_followup')

        ClientFollowUp.objects.create(
            client=client, org=org, visited_by=memb, feedback=feedback,
            priority=(
                request.POST.get('priority')
                if request.POST.get('priority') in dict(ClientFollowUp.PRIORITY_CHOICES)
                else 'medium'
            ),
            follow_up_date=follow_up_date, next_follow_up_date=next_follow_up_date,
            created_by=request.user,
        )
        messages.success(request, "Follow-up logged successfully.")
        return redirect('staff:client_detail', pk=client.pk)


def attendanceView(request, id, name):
    from handle.models import Course, CourseAttendance, AttendanceGap
    org = request.user.staff.org
    clas = get_object_or_404(Classification, id=id, org=org)
    mem = member.objects.filter(classification=clas, org=org).exclude(status='dumped')
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



class memReport(LoginRequiredMixin, PermRequiredMixin, ListView):
    required_perm = 'can_view_reports'
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
        tm = member.objects.filter(org=org, classification__in=assigned_class_ids).exclude(status='dumped')
       
        from school.print_settings import get_print_preference
        dist = {
            'date': today_date.strftime("%Y-%m-%d"), # Pass formatted date for HTML5 input
            'tm': tm,
            'org': org,
            'thisone': 'All Assigned',
            'clas': assigned_classes,
            'print_preference': get_print_preference(request.user, 'daily_report', org=org),
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
                tm = member.objects.filter(org=org, classification_id=selected_class_id).exclude(status='dumped')
                sn = Classification.objects.get(id=selected_class_id).name
            else:
                tm = member.objects.none()
                sn = "Unauthorized"
        else:
            # 'All' selected - show only their assigned classes
            tm = member.objects.filter(org=org, classification__in=assigned_class_ids).exclude(status='dumped')
            sn = 'All Assigned'
            
        from school.print_settings import get_print_preference
        dist = {
            'date': filter_date.strftime("%Y-%m-%d"),
            'tm': tm,
            'thisone': sn,
            'org': org,
            'clas': assigned_classes,
            'print_preference': get_print_preference(request.user, 'daily_report', org=org),
        }
        return render(request, self.template_name, dist)
    



class MyPayslipsView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'payroll'
    required_perm = 'can_view_own_payslip'
    template_name = 'staff/my_payslips.html'

    def get(self, request, *args, **kwargs):
        try:
            memb = request.user.staff.member
            org = request.user.staff.org
        except AttributeError:
            return render(request, self.template_name, {'error': "No associated member profile found."})

        # Fetch payslips ordered by the newest first
        payslips = PaySlip.objects.filter(member=memb).order_by('-from_date')

        # Attach a per-day attendance/hours breakdown (punch in/out, late in,
        # early out, overtime, worked hours, and Rs. amount) to each payslip
        # so staff can see exactly how their pay was derived, not just totals.
        from schooladmin.payroll_service import calculate_attendance_stats, calculate_payroll_components
        from handle.models import PayrollPolicy
        policy = PayrollPolicy.objects.filter(org=org).first()
        for slip in payslips:
            if slip.from_date and slip.to_date:
                stats, daily_logs = calculate_attendance_stats(memb, slip.from_date, slip.to_date, org)
                if policy:
                    calculate_payroll_components(memb, stats, org, policy, slip.to_date, daily_logs=daily_logs)
                slip.daily_logs = daily_logs
            else:
                slip.daily_logs = []

        from school.print_settings import get_print_preference
        context = {
            'memb': memb,
            'org': org,
            'payslips': payslips,
            'print_preference': get_print_preference(request.user, 'payslip', org=org),
        }
        return render(request, self.template_name, context)
    

class StaffPayrollReportView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only team payroll report, delegated via can_view_payroll."""
    required_feature = 'payroll'
    required_perm = 'can_view_payroll'
    template_name = 'staff/payroll_report.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        classification_id = request.GET.get('classification')
        members_qs = member.objects.filter(org=org, salary_amount__gt=0).exclude(status='dumped').order_by('name')
        if classification_id:
            members_qs = members_qs.filter(classification_id=classification_id)
        return render(request, self.template_name, {
            'org': org,
            'members': members_qs,
            'classifications': Classification.objects.filter(org=org),
            'selected_classification': classification_id,
        })


class StaffPayslipDetailView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only detail page for any org member's payslip, delegated via can_view_payroll."""
    required_feature = 'payroll'
    required_perm = 'can_view_payroll'
    template_name = 'staff/payroll_payslip_detail.html'

    def get(self, request, pk, *args, **kwargs):
        org = request.user.staff.org
        slip = get_object_or_404(PaySlip, pk=pk, org=org)
        return render(request, self.template_name, {'org': org, 'slip': slip, 'mem': slip.member})


class StaffPayrollSettingsView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Delegated payroll policy + adjustment management via can_manage_payroll_cfg.
    Deliberately excludes probation review (mutates member.status/staff_type
    org-wide) — that action stays admin-only.
    """
    required_feature = 'payroll'
    required_perm = 'can_manage_payroll_cfg'
    template_name = 'staff/payroll_settings.html'

    def get(self, request, *args, **kwargs):
        from handle.models import PayrollPolicy, PayrollAdjustment
        from handle.forms import PayrollPolicyForm, PayrollAdjustmentForm
        org = request.user.staff.org
        policy, _ = PayrollPolicy.objects.get_or_create(org=org)
        return render(request, self.template_name, {
            'org': org,
            'policy': policy,
            'policy_form': PayrollPolicyForm(instance=policy),
            'adjustment_form': PayrollAdjustmentForm(org=org),
            'adjustments': PayrollAdjustment.objects.filter(org=org).select_related('member', 'created_by')[:30],
        })

    def post(self, request, *args, **kwargs):
        from handle.models import PayrollPolicy
        from handle.forms import PayrollPolicyForm, PayrollAdjustmentForm
        org = request.user.staff.org
        action = request.POST.get('action')
        policy, _ = PayrollPolicy.objects.get_or_create(org=org)

        if action == 'policy':
            form = PayrollPolicyForm(request.POST, instance=policy)
            if form.is_valid():
                form.save()
                messages.success(request, "Payroll policy updated successfully.")
            else:
                messages.error(request, "Could not update payroll policy: " + form.errors.as_text())
        elif action == 'adjustment':
            form = PayrollAdjustmentForm(request.POST, org=org)
            if form.is_valid():
                adjustment = form.save(commit=False)
                adjustment.org = org
                adjustment.created_by = request.user
                adjustment.save()
                messages.success(request, "Payroll adjustment saved successfully.")
            else:
                messages.error(request, "Could not save adjustment: " + form.errors.as_text())
        else:
            messages.error(request, "Invalid payroll settings action.")
        return redirect('staff:payroll_settings')


class StaffGeneratePayslipView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Single-member payslip generation, delegated via can_generate_payroll.
    Unlike the admin bulk-generate flow, this deliberately does NOT auto-post
    a FinancialTransaction expense entry — granting this flag lets staff
    create a payslip record, not silently write to the Finance ledger.
    """
    required_feature = 'payroll'
    required_perm = 'can_generate_payroll'
    template_name = 'staff/generate_payslip.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        members_qs = member.objects.filter(org=org, salary_amount__gt=0).exclude(status='dumped').order_by('name')
        return render(request, self.template_name, {'org': org, 'members': members_qs})

    def post(self, request, *args, **kwargs):
        from handle.models import ProvidentFundRecord, SocialSecurityFundRecord
        from schooladmin.payroll_service import calculate_attendance_stats, calculate_payroll_components, get_or_create_policy
        org = request.user.staff.org
        member_id = request.POST.get('member_id')
        from_date_str = request.POST.get('from_date')
        to_date_str = request.POST.get('to_date')
        month_name = request.POST.get('month_name', '')

        if not member_id or not from_date_str or not to_date_str or not month_name:
            messages.error(request, "Please fill all required fields.")
            return redirect('staff:generate_payslip')

        try:
            m = member.objects.get(pk=member_id, org=org)
            from_date = datetime.datetime.strptime(from_date_str, '%Y-%m-%d').date()
            to_date = datetime.datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except (member.DoesNotExist, ValueError):
            messages.error(request, "Invalid member or date.")
            return redirect('staff:generate_payslip')

        if PaySlip.objects.filter(member=m, org=org, from_date=from_date, to_date=to_date).exists():
            messages.error(request, f"A payslip for {m.name} already covers this period.")
            return redirect('staff:generate_payslip')

        policy = get_or_create_policy(org)
        stats, _ = calculate_attendance_stats(m, from_date, to_date, org)
        comps = calculate_payroll_components(m, stats, org, policy, to_date)

        slip = PaySlip.objects.create(
            member=m, org=org, from_date=from_date, to_date=to_date, month_name=month_name,
            total_days=stats['total_days'], present_days=stats['days_present'],
            paid_leaves=stats['days_paid_leave'], holidays=stats['days_holiday'],
            unpaid_absences=stats['days_unpaid_absent'], salary_type=m.salary_type,
            gross_salary=comps['gross_salary'], allowance_total=comps['allowance_total'],
            bonus_total=comps['bonus_total'], advance_deduction=comps['advance_deduction'],
            loan_deduction=comps['loan_deduction'], other_deduction=comps['other_deduction'],
            tax_deduction=comps['tax_amount'], pf_employee=comps['pf_employee'],
            pf_employer=comps['pf_employer'], ssf_employee=comps['ssf_employee'],
            ssf_employer=comps['ssf_employer'], probation_adjustment=comps['probation_adjustment'],
            overtime_hours=comps['overtime_hours'], overtime_amount=comps['overtime_amount'],
            net_payable=comps['net_payable'], status='draft',
        )
        if slip.pf_employee or slip.pf_employer:
            ProvidentFundRecord.objects.create(
                org=org, member=m, payslip=slip, month_name=month_name,
                employee_contribution=slip.pf_employee, employer_contribution=slip.pf_employer,
            )
        if slip.ssf_employee or slip.ssf_employer:
            SocialSecurityFundRecord.objects.create(
                org=org, member=m, payslip=slip, month_name=month_name,
                employee_contribution=slip.ssf_employee, employer_contribution=slip.ssf_employer,
            )
        messages.success(request, f"Payslip generated for {m.name} (draft — an admin must finalize it).")
        return redirect('staff:generate_payslip')


class StaffLeaveApprovalView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Delegated leave approval via can_approve_leave. Org-scoped throughout —
    the admin-only equivalents (schooladmin/views.py leaveStatus /
    leave_status_with_email) previously had no org filter at all (a
    cross-org IDOR, fixed alongside this).
    """
    required_feature = 'leave'
    required_perm = 'can_approve_leave'
    template_name = 'staff/leave_approval.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        pending = list(LeaveReport.objects.filter(org=org, approved=False, rejected=False).select_related(
            'member', 'leave_type'
        ).order_by('-id'))
        nepali_enabled = org.nepali_date
        if nepali_enabled:
            for leave in pending:
                leave.start_display = to_bs_display(leave.gap_start)
                leave.end_display = to_bs_display(leave.gap_end)
        else:
            for leave in pending:
                leave.start_display = leave.gap_start.strftime("%Y-%m-%d") if leave.gap_start else ""
                leave.end_display = leave.gap_end.strftime("%Y-%m-%d") if leave.gap_end else ""
        return render(request, self.template_name, {
            'org': org, 'pending': pending, 'nepali_enabled': nepali_enabled,
        })

    def post(self, request, *args, **kwargs):
        org = request.user.staff.org
        report_id = request.POST.get('report_id')
        action = request.POST.get('action')
        report = get_object_or_404(LeaveReport, pk=report_id, org=org)

        if action == 'approve':
            report.approved = True
            report.rejected = False
        elif action == 'reject':
            report.approved = False
            report.rejected = True
        else:
            messages.error(request, "Invalid action.")
            return redirect('staff:leave_approval')
        report.seen = True
        report.save()
        messages.success(request, f"Leave request {'approved' if action == 'approve' else 'rejected'}.")
        return redirect('staff:leave_approval')


class StaffLeaveReportView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only org-wide leave balance report, delegated via can_view_leave_report."""
    required_feature = 'leave'
    required_perm = 'can_view_leave_report'
    template_name = 'staff/leave_report.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        members_qs = member.objects.filter(org=org).exclude(status='dumped')
        leave_types = LeaveType.objects.filter(org=org)
        master_data = []
        for mem in members_qs:
            balances = [{'type_name': lt.name, 'data': mem.get_leave_balance(lt.id)} for lt in leave_types]
            master_data.append({'member': mem, 'balances': balances})
        return render(request, self.template_name, {'org': org, 'leave_types': leave_types, 'master_data': master_data})


class StaffHRMSView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Delegated HR module. Viewing resignations/documents needs can_view_hrms;
    filing a resignation on someone's behalf or uploading a document needs
    can_manage_hrms (checked explicitly in post(), since one page serves both
    capability levels). Final clearance/settlement sign-off and document
    deletion are deliberately not exposed here — they stay admin-only.
    """
    required_feature = 'hrms'
    required_perm = 'can_view_hrms'
    template_name = 'staff/hrms.html'

    def get(self, request, *args, **kwargs):
        from handle.models import ResignationRecord, StaffDocument
        from school.features import has_perm
        org = request.user.staff.org
        can_manage = has_perm(request.user, 'can_manage_hrms')
        return render(request, self.template_name, {
            'org': org,
            'resignations': ResignationRecord.objects.filter(org=org).select_related('member').order_by('-id')[:50],
            'documents': StaffDocument.objects.filter(org=org).select_related('member').order_by('-id')[:50],
            'members': member.objects.filter(org=org).exclude(status='dumped').order_by('name') if can_manage else None,
            'can_manage': can_manage,
        })

    def post(self, request, *args, **kwargs):
        from handle.models import ResignationRecord, StaffDocument
        from school.features import has_perm
        org = request.user.staff.org
        if not has_perm(request.user, 'can_manage_hrms'):
            return render(request, '403.html', {
                'reason': "You don't have permission to perform this action.",
            }, status=403)

        action = request.POST.get('action')
        if action == 'file_resignation':
            mem = get_object_or_404(member, pk=request.POST.get('member_id'), org=org)
            ResignationRecord.objects.create(
                org=org, member=mem,
                resignation_date=request.POST.get('resignation_date') or timezone.localdate(),
                last_working_day=request.POST.get('last_working_day') or None,
                reason=request.POST.get('reason', ''),
                self_applied=False,
            )
            messages.success(request, f"Resignation filed for {mem.name}.")
        elif action == 'upload_document':
            mem = get_object_or_404(member, pk=request.POST.get('member_id'), org=org)
            doc_file = request.FILES.get('file')
            if doc_file:
                StaffDocument.objects.create(
                    org=org, member=mem,
                    document_type=request.POST.get('document_type', 'other'),
                    title=request.POST.get('title') or doc_file.name,
                    file=doc_file,
                )
                messages.success(request, f"Document uploaded for {mem.name}.")
            else:
                messages.error(request, "Please choose a file to upload.")
        else:
            messages.error(request, "Invalid action.")
        return redirect('staff:hrms')


class StaffCourseListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """"My courses" only (Course.teacher=self), delegated via can_view_courses — narrower than the admin org-wide list, since Course.teacher is a direct FK to the logged-in user."""
    required_feature = 'courses'
    required_perm = 'can_view_courses'
    template_name = 'staff/course_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Course
        org = request.user.staff.org
        courses = Course.objects.filter(org=org, teacher=request.user).select_related('branch').prefetch_related(
            'classifications', 'sections'
        ).order_by('name')
        return render(request, self.template_name, {'org': org, 'courses': courses})


class StaffManageCoursesView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Create a course (org-wide teacher picker, matching current admin behavior
    since course creation has no owner concept) and edit courses where
    teacher=request.user. delete_course (hard delete) stays admin-only.
    """
    required_feature = 'courses'
    required_perm = 'can_manage_courses'
    template_name = 'staff/manage_courses.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Course, Branch, Classification, Section, Staff
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org,
            'branches': Branch.objects.filter(org=org, status='active'),
            'classifications': Classification.objects.filter(org=org),
            'sections': Section.objects.filter(org=org),
            'staff_list': Staff.objects.filter(org=org).select_related('admin'),
            'my_courses': Course.objects.filter(org=org, teacher=request.user).order_by('name'),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import Course
        org = request.user.staff.org
        action = request.POST.get('action')

        if action == 'create':
            try:
                course = Course.objects.create(
                    org=org,
                    name=request.POST.get('name'),
                    code=request.POST.get('code', ''),
                    branch_id=request.POST.get('branch') or None,
                    teacher_id=request.POST.get('teacher') or None,
                    description=request.POST.get('description', ''),
                    credit_hour=request.POST.get('credit_hour', 0),
                    status=request.POST.get('status', 'active'),
                )
                classification_ids = request.POST.getlist('classifications')
                section_ids = request.POST.getlist('sections')
                if classification_ids:
                    course.classifications.set(classification_ids)
                if section_ids:
                    course.sections.set(section_ids)
                messages.success(request, f"Course '{course.name}' created.")
            except Exception as e:
                messages.error(request, f"Error: {e}")
        elif action == 'edit':
            course = get_object_or_404(Course, pk=request.POST.get('course_id'), org=org, teacher=request.user)
            course.name = request.POST.get('name', course.name)
            course.description = request.POST.get('description', course.description)
            course.status = request.POST.get('status', course.status)
            course.save()
            messages.success(request, f"Course '{course.name}' updated.")
        else:
            messages.error(request, "Invalid action.")
        return redirect('staff:manage_courses')


class StaffResultEntryView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Delegated marks entry via can_publish_results. Despite the flag's name,
    this deliberately only allows entering marks — the actual org-wide
    publish/unpublish toggle (and mass guardian email) stays admin-only.
    """
    required_feature = 'results'
    required_perm = 'can_publish_results'
    template_name = 'staff/result_entry.html'

    def _build_members_data(self, org, exam, classification, section_id=None):
        from handle.models import Subject, ResultRecord
        from django.db.models import Q
        subjects_qs = Subject.objects.filter(org=org, classification=classification, status='active')
        if section_id:
            subjects_qs = subjects_qs.filter(Q(section_id=section_id) | Q(section__isnull=True))
        subjects = list(subjects_qs)
        members_filter = {'org': org, 'classification': classification}
        if section_id:
            members_filter['section_id'] = section_id
        members_qs = member.objects.filter(**members_filter).exclude(status='dumped').order_by('name')
        members_data = []
        for mem in members_qs:
            existing = {
                r.subject_id: r for r in ResultRecord.objects.filter(student=mem, exam=exam).select_related('subject')
            } if exam else {}
            members_data.append({'member': mem, 'records': existing})
        return subjects, members_data

    def get(self, request, *args, **kwargs):
        from handle.models import ExamTerm, Classification, Section
        org = request.user.staff.org
        exam_id = request.GET.get('exam')
        classification_id = request.GET.get('classification')
        section_id = request.GET.get('section')
        exam = classification = None
        subjects = []
        members_data = []
        sections = []

        if exam_id:
            exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
        if classification_id:
            classification = get_object_or_404(Classification, pk=classification_id, org=org)
            sections = list(Section.objects.filter(org=org, classification=classification))
            if exam:
                subjects, members_data = self._build_members_data(org, exam, classification, section_id)

        return render(request, self.template_name, {
            'org': org,
            'exams': ExamTerm.objects.filter(org=org),
            'classifications': Classification.objects.filter(org=org),
            'sections': sections,
            'selected_exam': exam,
            'selected_classification': classification,
            'selected_section': section_id,
            'subjects': subjects,
            'members_data': members_data,
        })

    def post(self, request, *args, **kwargs):
        from handle.models import ExamTerm, Subject, ResultRecord
        from django.db.models import Q
        org = request.user.staff.org
        exam_id = request.POST.get('exam_id')
        classification_id = request.POST.get('classification_id')
        section_id = request.POST.get('section_id') or None
        exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
        subjects_qs = Subject.objects.filter(org=org, classification_id=classification_id, status='active')
        if section_id:
            subjects_qs = subjects_qs.filter(Q(section_id=section_id) | Q(section__isnull=True))
        members_filter = {'org': org, 'classification_id': classification_id}
        if section_id:
            members_filter['section_id'] = section_id
        members_qs = member.objects.filter(**members_filter).exclude(status='dumped')

        saved = 0
        for mem in members_qs:
            for subj in subjects_qs:
                marks_val = request.POST.get(f"marks_{mem.id}_{subj.id}", '').strip()
                is_absent = request.POST.get(f"absent_{mem.id}_{subj.id}") == 'on'
                if marks_val != '' or is_absent:
                    try:
                        marks_float = 0.0 if is_absent else float(marks_val)
                        ResultRecord.objects.update_or_create(
                            student=mem, exam=exam, subject=subj,
                            defaults={
                                'obtained_marks': marks_float,
                                'is_absent': is_absent,
                                'remarks': request.POST.get(f"remarks_{mem.id}_{subj.id}", '').strip() or ('Absent' if is_absent else None),
                                'updated_by': request.user,
                            }
                        )
                        saved += 1
                    except (ValueError, Exception):
                        pass

        if exam.status == 'draft' and saved:
            exam.status = 'marks_entry'
            exam.save(update_fields=['status'])

        messages.success(request, f"Saved {saved} result records.")
        from django.urls import reverse
        qs = f"?exam={exam_id}&classification={classification_id}"
        if section_id:
            qs += f"&section={section_id}"
        return redirect(f"{reverse('staff:result_entry')}{qs}")


class StaffResultReportView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Read-only team/class result report, delegated via can_view_result_report.
    This is a thin wrapper around the same query logic as the admin
    ResultReportView (schooladmin/views.py), which was already correctly
    perm-gated on this exact flag — it was only unreachable for staff because
    of the middleware's schooladmin/ prefix block, not a scoping problem.
    """
    required_feature = 'results'
    required_perm = 'can_view_result_report'
    template_name = 'staff/result_report.html'

    def get(self, request, *args, **kwargs):
        from handle.models import ExamTerm, Classification, Section, Subject, ResultRecord, compute_grade
        from django.db.models import Q
        org = request.user.staff.org
        exam_id = request.GET.get('exam')
        classification_id = request.GET.get('classification')
        section_id = request.GET.get('section')
        exam = classification = None
        report_data = []
        subjects = []
        sections = []
        stat_summary = {}

        if exam_id and classification_id:
            exam = get_object_or_404(ExamTerm, pk=exam_id, org=org)
            classification = get_object_or_404(Classification, pk=classification_id, org=org)
            sections = list(Section.objects.filter(org=org, classification=classification))
            subjects_qs = Subject.objects.filter(org=org, classification=classification, status='active')
            if section_id:
                subjects_qs = subjects_qs.filter(Q(section_id=section_id) | Q(section__isnull=True))
            subjects = list(subjects_qs)
            members_filter = {'org': org, 'classification': classification}
            if section_id:
                members_filter['section_id'] = section_id
            members_qs = member.objects.filter(**members_filter).exclude(status='dumped').order_by('name')

            pass_count = fail_count = absent_count = entry_count = 0
            for mem in members_qs:
                results = {r.subject_id: r for r in ResultRecord.objects.filter(student=mem, exam=exam).select_related('subject')}
                total_obt = float(sum(r.obtained_marks for r in results.values()))
                full_total = float(sum(s.full_marks for s in subjects))
                pct = round(total_obt / full_total * 100, 1) if full_total else 0
                passed = all(r.is_passed for r in results.values()) if results else False
                has_absent = any(r.is_absent for r in results.values())
                if results:
                    entry_count += 1
                    if has_absent:
                        absent_count += 1
                    elif passed:
                        pass_count += 1
                    else:
                        fail_count += 1
                report_data.append({
                    'member': mem, 'results': results, 'total': total_obt, 'full_total': full_total,
                    'percentage': pct, 'passed': passed, 'grade': compute_grade(pct),
                    'has_absent': has_absent, 'rank': 0,
                })

            ranked = sorted([r for r in report_data if r['results']], key=lambda x: x['total'], reverse=True)
            for i, r in enumerate(ranked, 1):
                r['rank'] = i

            stat_summary = {
                'total_students': len(report_data), 'entry_count': entry_count,
                'pass_count': pass_count, 'fail_count': fail_count,
                'absent_count': absent_count, 'pending_count': len(report_data) - entry_count,
            }

        return render(request, self.template_name, {
            'org': org,
            'exams': ExamTerm.objects.filter(org=org),
            'classifications': Classification.objects.filter(org=org),
            'sections': sections,
            'selected_exam': exam,
            'selected_classification': classification,
            'selected_section': section_id,
            'subjects': subjects,
            'report_data': report_data,
            'stat_summary': stat_summary,
        })


class StaffStockDashboardView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only stock overview, delegated via can_view_stock. Org-wide (no Staff.branch field exists to narrow further)."""
    required_feature = 'stock'
    required_perm = 'can_view_stock'
    template_name = 'staff/stock_dashboard.html'

    def get(self, request, *args, **kwargs):
        from handle.models import StockItem, StockMovement, StockCategory, Branch
        org = request.user.staff.org
        branch_id = request.GET.get('branch', '')
        category_id = request.GET.get('category', '')
        items = StockItem.objects.filter(org=org, status='active').select_related('category', 'branch')
        movements_qs = StockMovement.objects.filter(org=org).select_related('item', 'branch').order_by('-movement_date')
        if branch_id:
            items = items.filter(branch_id=branch_id)
            movements_qs = movements_qs.filter(branch_id=branch_id)
        if category_id:
            items = items.filter(category_id=category_id)
        low_stock = [i for i in items if i.is_low_stock]
        return render(request, self.template_name, {
            'org': org, 'items': items, 'low_stock': low_stock, 'low_stock_count': len(low_stock),
            'total_items': items.count(),
            'total_value': sum((i.quantity * (i.purchase_cost or 0)) for i in items),
            'recent_movements': movements_qs[:10],
            'categories': StockCategory.objects.filter(org=org),
            'branches': Branch.objects.filter(org=org, status='active'),
            'selected_branch': branch_id, 'selected_category': category_id,
        })


class StaffStockItemListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only stock item list, delegated via can_view_stock."""
    required_feature = 'stock'
    required_perm = 'can_view_stock'
    template_name = 'staff/stock_item_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import StockItem, StockCategory, Branch
        from django.db.models import Q
        org = request.user.staff.org
        qs = StockItem.objects.filter(org=org).select_related('category', 'branch').order_by('name')
        search = request.GET.get('search', '')
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))
        return render(request, self.template_name, {
            'org': org, 'items': qs, 'branches': Branch.objects.filter(org=org, status='active'),
            'categories': StockCategory.objects.filter(org=org), 'search': search,
        })


class StaffAddStockItemView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Add a new stock item, delegated via can_add_stock."""
    required_feature = 'stock'
    required_perm = 'can_add_stock'
    template_name = 'staff/add_stock_item.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Branch, StockCategory
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'branches': Branch.objects.filter(org=org, status='active'),
            'categories': StockCategory.objects.filter(org=org),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import StockItem
        from decimal import Decimal
        org = request.user.staff.org
        try:
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, "Item name is required.")
                return redirect('staff:add_stock_item')
            StockItem.objects.create(
                org=org, name=name, sku=request.POST.get('sku', ''), unit=request.POST.get('unit', 'pcs'),
                category_id=request.POST.get('category') or None, branch_id=request.POST.get('branch') or None,
                quantity=Decimal('0'), low_stock_threshold=int(request.POST.get('low_stock_threshold', 5) or 5),
                supplier=request.POST.get('supplier', ''),
                purchase_cost=Decimal(str(request.POST.get('purchase_cost', 0) or 0)),
                status=request.POST.get('status', 'active'),
            )
            messages.success(request, f"Stock item '{name}' added.")
            return redirect('staff:stock_items')
        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('staff:add_stock_item')


class StaffEditStockItemView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Edit an existing stock item, delegated via can_edit_stock. Deleting a stock item stays admin-only."""
    required_feature = 'stock'
    required_perm = 'can_edit_stock'
    template_name = 'staff/edit_stock_item.html'

    def get(self, request, pk, *args, **kwargs):
        from handle.models import StockItem, Branch, StockCategory
        org = request.user.staff.org
        item = get_object_or_404(StockItem, pk=pk, org=org)
        return render(request, self.template_name, {
            'org': org, 'item': item, 'branches': Branch.objects.filter(org=org, status='active'),
            'categories': StockCategory.objects.filter(org=org),
        })

    def post(self, request, pk, *args, **kwargs):
        from handle.models import StockItem
        from decimal import Decimal
        org = request.user.staff.org
        item = get_object_or_404(StockItem, pk=pk, org=org)
        item.name = request.POST.get('name', item.name)
        item.sku = request.POST.get('sku', item.sku)
        item.unit = request.POST.get('unit', item.unit)
        item.category_id = request.POST.get('category') or None
        item.branch_id = request.POST.get('branch') or None
        item.low_stock_threshold = int(request.POST.get('low_stock_threshold', item.low_stock_threshold) or 0)
        item.supplier = request.POST.get('supplier', item.supplier)
        item.purchase_cost = Decimal(str(request.POST.get('purchase_cost', item.purchase_cost) or 0))
        item.status = request.POST.get('status', item.status)
        item.save()
        messages.success(request, "Stock item updated.")
        return redirect('staff:stock_items')


class StaffStockInView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Record incoming stock, delegated via can_stock_in_out. Deliberately
    excludes the admin flow's "add as expense" checkbox — that auto-posts a
    FinancialTransaction, a cross-module side effect not appropriate for a
    plain stock permission.
    """
    required_feature = 'stock'
    required_perm = 'can_stock_in_out'
    template_name = 'staff/stock_in.html'

    def get(self, request, *args, **kwargs):
        from handle.models import StockItem
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'items': StockItem.objects.filter(org=org, status='active').order_by('name'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import StockItem, StockMovement
        from decimal import Decimal
        org = request.user.staff.org
        item_id = request.POST.get('item')
        quantity = request.POST.get('quantity')
        unit_cost = request.POST.get('unit_cost', 0)
        note = request.POST.get('note', '')
        movement_date = request.POST.get('movement_date', datetime.date.today())
        if not item_id or not quantity:
            messages.error(request, "Item and quantity are required.")
            return redirect('staff:stock_in')
        item = get_object_or_404(StockItem, pk=item_id, org=org)
        StockMovement.objects.create(
            org=org, branch=item.branch, item=item, created_by=request.user, movement_type='in',
            quantity=Decimal(str(quantity)), unit_cost=Decimal(str(unit_cost or 0)),
            movement_date=movement_date, note=note,
        )
        messages.success(request, f"Stock in recorded for '{item.name}'.")
        return redirect('staff:stock_items')


class StaffStockOutView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Record outgoing stock, delegated via can_stock_in_out."""
    required_feature = 'stock'
    required_perm = 'can_stock_in_out'
    template_name = 'staff/stock_out.html'

    def get(self, request, *args, **kwargs):
        from handle.models import StockItem
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'items': StockItem.objects.filter(org=org, status='active').order_by('name'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import StockItem, StockMovement
        from decimal import Decimal
        org = request.user.staff.org
        item_id = request.POST.get('item')
        quantity = Decimal(str(request.POST.get('quantity', 0) or 0))
        note = request.POST.get('note', '')
        movement_date = request.POST.get('movement_date', datetime.date.today())
        if not item_id or quantity <= 0:
            messages.error(request, "Item and valid quantity are required.")
            return redirect('staff:stock_out')
        item = get_object_or_404(StockItem, pk=item_id, org=org)
        if item.quantity < quantity:
            messages.error(request, f"Insufficient stock. Available: {item.quantity} {item.unit}")
            return redirect('staff:stock_out')
        StockMovement.objects.create(
            org=org, branch=item.branch, item=item, created_by=request.user, movement_type='out',
            quantity=quantity, unit_cost=item.purchase_cost or Decimal('0'), movement_date=movement_date, note=note,
        )
        messages.success(request, f"Stock out recorded for '{item.name}'.")
        return redirect('staff:stock_items')


class StaffStockMovementHistoryView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only stock movement history, delegated via can_view_stock."""
    required_feature = 'stock'
    required_perm = 'can_view_stock'
    template_name = 'staff/stock_movement_history.html'

    def get(self, request, *args, **kwargs):
        from handle.models import StockMovement, StockItem
        org = request.user.staff.org
        qs = StockMovement.objects.filter(org=org).select_related('item', 'branch', 'created_by').order_by('-movement_date', '-id')
        item_id = request.GET.get('item')
        movement_type = request.GET.get('movement_type')
        if item_id:
            qs = qs.filter(item_id=item_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        return render(request, self.template_name, {
            'org': org, 'movements': qs, 'items': StockItem.objects.filter(org=org).order_by('name'),
            'selected_item': item_id, 'selected_type': movement_type,
        })


class StaffBranchListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only branch list, delegated via can_view_branches."""
    required_feature = 'branches'
    required_perm = 'can_view_branches'
    template_name = 'staff/branch_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Branch
        from django.db.models import Count, Q
        org = request.user.staff.org
        branches = Branch.objects.filter(org=org).annotate(
            member_count=Count('members', filter=Q(members__status='active'))
        ).order_by('name')
        return render(request, self.template_name, {'org': org, 'branches': branches})


class StaffManageBranchesView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Add a branch, delegated via can_manage_branches. Deleting a branch stays admin-only."""
    required_feature = 'branches'
    required_perm = 'can_manage_branches'
    template_name = 'staff/manage_branches.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Branch
        org = request.user.staff.org
        return render(request, self.template_name, {'org': org, 'branches': Branch.objects.filter(org=org).order_by('name')})

    def post(self, request, *args, **kwargs):
        from handle.models import Branch
        org = request.user.staff.org
        name = request.POST.get('name', '').strip()
        code = request.POST.get('code', '').strip()
        if not name or not code:
            messages.error(request, "Name and code are required.")
        else:
            Branch.objects.get_or_create(org=org, code=code, defaults={
                'name': name, 'address': request.POST.get('address', ''),
                'phone': request.POST.get('phone', ''), 'email': request.POST.get('email', ''),
            })
            messages.success(request, f"Branch '{name}' added.")
        return redirect('staff:manage_branches')


class StaffEventListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only event list, delegated via can_view_events."""
    required_feature = 'events'
    required_perm = 'can_view_events'
    template_name = 'staff/event_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Event, Branch
        org = request.user.staff.org
        qs = Event.objects.filter(org=org).select_related('branch', 'responsible_staff').order_by('-start_date')
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'org': org, 'events': qs, 'branches': Branch.objects.filter(org=org, status='active'),
            'selected_status': status, 'event_types': Event.EVENT_TYPE_CHOICES, 'status_choices': Event.STATUS_CHOICES,
        })


class StaffManageEventsView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Add/edit an event, delegated via can_manage_events. Deliberately excludes
    delete_event and the stock-usage add/remove sub-actions (those mutate
    StockItem.quantity as a cross-module side effect) — both stay admin-only.
    """
    required_feature = 'events'
    required_perm = 'can_manage_events'
    template_name = 'staff/manage_events.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Event, Branch, Staff
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'branches': Branch.objects.filter(org=org, status='active'),
            'staff_list': Staff.objects.filter(org=org).select_related('admin'),
            'event_types': Event.EVENT_TYPE_CHOICES, 'status_choices': Event.STATUS_CHOICES,
            'today': datetime.date.today().strftime('%Y-%m-%d'),
            'my_events': Event.objects.filter(org=org).select_related('branch').order_by('-start_date')[:30],
        })

    def post(self, request, *args, **kwargs):
        from handle.models import Event
        org = request.user.staff.org
        action = request.POST.get('action')

        if action == 'create':
            try:
                event = Event.objects.create(
                    org=org, title=request.POST.get('title'), event_type=request.POST.get('event_type', 'other'),
                    branch_id=request.POST.get('branch') or None, start_date=request.POST.get('start_date'),
                    end_date=request.POST.get('end_date'), location=request.POST.get('location', ''),
                    description=request.POST.get('description', ''),
                    responsible_staff_id=request.POST.get('responsible_staff') or None,
                    status=request.POST.get('status', 'upcoming'),
                )
                messages.success(request, f"Event '{event.title}' created.")
            except Exception as e:
                messages.error(request, f"Error: {e}")
        elif action == 'update_event':
            event = get_object_or_404(Event, pk=request.POST.get('event_id'), org=org)
            event.title = request.POST.get('title', event.title)
            event.event_type = request.POST.get('event_type', event.event_type)
            event.start_date = request.POST.get('start_date', event.start_date)
            event.end_date = request.POST.get('end_date', event.end_date)
            event.location = request.POST.get('location', event.location)
            event.description = request.POST.get('description', event.description)
            event.status = request.POST.get('status', event.status)
            event.save()
            messages.success(request, "Event updated.")
        else:
            messages.error(request, "Invalid action.")
        return redirect('staff:manage_events')


class StaffFieldVisitListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Read-only "my field visits" list, delegated via can_view_field_visits —
    the same created_by=request.user scoping already used by StaffClientListView.
    Approve/reject stays on the existing admin FieldVisitDetailView (creates
    real attendance records, already double-gated with AdminRequiredMixin).
    """
    required_feature = 'field_visits'
    required_perm = 'can_view_field_visits'
    template_name = 'staff/field_visit_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import FieldVisit
        org = request.user.staff.org
        visits = FieldVisit.objects.filter(org=org, created_by=request.user).select_related('client').order_by('-visited_at')
        return render(request, self.template_name, {'org': org, 'visits': visits})


class StaffCreateBillView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Single-member bill creation, delegated via can_generate_bills."""
    required_feature = 'billing'
    required_perm = 'can_generate_bills'
    template_name = 'staff/create_bill.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org
        return render(request, self.template_name, {'org': org, 'members': member.objects.filter(org=org).exclude(status='dumped').order_by('name')})

    def post(self, request, *args, **kwargs):
        from handle.models import Bill, BillItem
        from decimal import Decimal
        from django.db import transaction
        from school.email_utils import send_bill_email
        import random, string
        org = request.user.staff.org
        member_id = request.POST.get('member_id')
        due_date = request.POST.get('due_date')
        remarks = request.POST.get('remarks', '')
        send_email = request.POST.get('send_email') == 'on'
        descriptions = request.POST.getlist('description')
        amounts = request.POST.getlist('amount')

        if not member_id or not due_date or not descriptions:
            messages.error(request, "Member, due date and at least one item are required.")
            return redirect('staff:create_bill')

        m = get_object_or_404(member, pk=member_id, org=org)
        invoice_no = 'INV-' + ''.join(random.choices(string.digits, k=8))
        items = []
        total = Decimal('0')
        for desc, amt in zip(descriptions, amounts):
            desc = desc.strip()
            if desc and amt:
                try:
                    amt_d = Decimal(str(amt))
                    items.append({'desc': desc, 'amount': amt_d})
                    total += amt_d
                except Exception:
                    pass

        if not items:
            messages.error(request, "Add at least one valid line item.")
            return redirect('staff:create_bill')

        with transaction.atomic():
            bill = Bill.objects.create(org=org, member=m, invoice_number=invoice_no, due_date=due_date, total_amount=total, remarks=remarks)
            for it in items:
                BillItem.objects.create(bill=bill, description=it['desc'], amount=it['amount'])

        if send_email and m.email:
            send_bill_email(email=m.email, name=m.name, invoice_number=invoice_no, total_amount=total, due_date=due_date, items=items, org_name=org.name, remarks=remarks)

        messages.success(request, f"Bill {invoice_no} created for {m.name}.")
        return redirect('staff:create_bill')


class StaffBillDetailView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Record a payment or resend the invoice email, delegated via
    can_record_payment. Deliberately excludes delete_bill (hard delete),
    which stays admin-only.
    """
    required_feature = 'billing'
    required_perm = 'can_record_payment'
    template_name = 'staff/bill_detail.html'

    def get(self, request, pk, *args, **kwargs):
        from handle.models import Bill
        org = request.user.staff.org
        bill = get_object_or_404(Bill, pk=pk, org=org)
        return render(request, self.template_name, {'org': org, 'bill': bill})

    def post(self, request, pk, *args, **kwargs):
        from handle.models import Bill, TransactionCategory, FinancialTransaction
        from decimal import Decimal
        from django.db import transaction
        from school.email_utils import send_bill_email
        org = request.user.staff.org
        bill = get_object_or_404(Bill, pk=pk, org=org)
        action = request.POST.get('action')

        if action == 'update_payment':
            try:
                new_amount = Decimal(request.POST.get('amount_paid', '0'))
            except Exception:
                messages.error(request, "Invalid amount.")
                return redirect('staff:bill_detail', pk=pk)
            if new_amount < 0 or new_amount > bill.total_amount:
                messages.error(request, f"Amount must be between 0 and the bill total (Rs. {bill.total_amount}).")
                return redirect('staff:bill_detail', pk=pk)

            requested_status = request.POST.get('status', bill.status)
            valid_statuses = dict(Bill.STATUS_CHOICES)
            if requested_status == 'Cancelled' and requested_status in valid_statuses:
                new_status = 'Cancelled'
            elif new_amount >= bill.total_amount:
                new_status = 'Paid'
            elif new_amount > 0:
                new_status = 'Partial'
            else:
                new_status = 'Unpaid'

            with transaction.atomic():
                delta = new_amount - bill.amount_paid
                bill.amount_paid = new_amount
                bill.status = new_status
                bill.save()
                if delta > 0:
                    bill_cat, _ = TransactionCategory.objects.get_or_create(org=org, name='Bill Collection', transaction_type='income')
                    FinancialTransaction.objects.create(
                        org=org, transaction_type='income',
                        title=f"Bill Payment — {bill.invoice_number} ({bill.member.name})",
                        amount=delta, category=bill_cat, reference_number=bill.invoice_number,
                        note=f"Auto-linked from invoice #{bill.invoice_number}", created_by=request.user,
                    )
            messages.success(request, "Payment updated.")
        elif action == 'resend_email':
            if bill.member.email:
                items = [{'desc': i.description, 'amount': i.amount} for i in bill.items.all()]
                send_bill_email(email=bill.member.email, name=bill.member.name, invoice_number=bill.invoice_number,
                                 total_amount=bill.total_amount, due_date=bill.due_date, items=items, org_name=org.name, remarks=bill.remarks or '')
                messages.success(request, f"Invoice emailed to {bill.member.email}.")
            else:
                messages.error(request, "Member has no email address on file.")
        return redirect('staff:bill_detail', pk=pk)


class StaffBillingDuesView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only org-wide dues list, delegated via can_view_dues."""
    required_feature = 'billing'
    required_perm = 'can_view_dues'
    template_name = 'staff/billing_dues.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Bill
        org = request.user.staff.org
        bills = Bill.objects.filter(org=org).exclude(status='Cancelled').select_related('member').order_by('-due_date')
        for b in bills:
            b.due_amount = b.total_amount - b.amount_paid
        return render(request, self.template_name, {'org': org, 'bills': bills})


class StaffExportBillingView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's bills/dues, delegated via can_export_billing."""
    required_feature = 'billing'
    required_perm = 'can_export_billing'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        from handle.models import Bill
        org = request.user.staff.org
        bills = Bill.objects.filter(org=org).exclude(status='Cancelled').select_related('member').order_by('-due_date')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="billing_dues.csv"'
        w = csv.writer(resp)
        w.writerow(['Invoice', 'Member', 'Due Date', 'Total', 'Paid', 'Due', 'Status'])
        for b in bills:
            w.writerow([b.invoice_number, b.member.name, b.due_date, b.total_amount, b.amount_paid, b.total_amount - b.amount_paid, b.status])
        return resp


class StaffFinanceDashboardView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only finance overview, delegated via can_view_finance. Org-wide (no Staff.branch field to narrow further)."""
    required_feature = 'finance'
    required_perm = 'can_view_finance'
    template_name = 'staff/finance_dashboard.html'

    def get(self, request, *args, **kwargs):
        from handle.models import FinancialTransaction, TransactionCategory, Branch
        from django.db.models import Sum
        org = request.user.staff.org
        today = datetime.date.today()
        month_start = today.replace(day=1)
        income_qs = FinancialTransaction.objects.filter(org=org, transaction_type='income')
        expense_qs = FinancialTransaction.objects.filter(org=org, transaction_type='expense')
        total_income = income_qs.aggregate(t=Sum('amount'))['t'] or 0
        total_expense = expense_qs.aggregate(t=Sum('amount'))['t'] or 0
        month_income = income_qs.filter(transaction_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0
        month_expense = expense_qs.filter(transaction_date__gte=month_start).aggregate(t=Sum('amount'))['t'] or 0
        recent_transactions = FinancialTransaction.objects.filter(org=org).select_related('branch', 'category').order_by('-transaction_date')[:10]
        return render(request, self.template_name, {
            'org': org, 'total_income': total_income, 'total_expense': total_expense,
            'net_balance': total_income - total_expense, 'month_income': month_income, 'month_expense': month_expense,
            'recent_transactions': recent_transactions,
        })


class StaffAddIncomeView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Record income, delegated via can_manage_finance. Editing/deleting existing entries stays admin-only."""
    required_feature = 'finance'
    required_perm = 'can_manage_finance'
    template_name = 'staff/add_income.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Branch, TransactionCategory
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='income'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import FinancialTransaction
        org = request.user.staff.org
        try:
            title = request.POST.get('title', '').strip()
            amount = request.POST.get('amount')
            transaction_date = request.POST.get('transaction_date')
            if not all([title, amount, transaction_date]):
                messages.error(request, "Title, amount, and date are required.")
                return redirect('staff:add_income')
            FinancialTransaction.objects.create(
                org=org, transaction_type='income', title=title, amount=amount,
                category_id=request.POST.get('category') or None, branch_id=request.POST.get('branch') or None,
                transaction_date=transaction_date, payment_method=request.POST.get('payment_method', 'cash'),
                note=request.POST.get('note', ''), reference_number=request.POST.get('reference_number', ''),
                created_by=request.user,
            )
            messages.success(request, f"Income '{title}' added successfully.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect('staff:add_income')


class StaffAddExpenseView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Record expense, delegated via can_manage_finance. Editing/deleting existing entries stays admin-only."""
    required_feature = 'finance'
    required_perm = 'can_manage_finance'
    template_name = 'staff/add_expense.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Branch, TransactionCategory
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'branches': Branch.objects.filter(org=org, status='active'),
            'categories': TransactionCategory.objects.filter(org=org, transaction_type='expense'),
            'today': datetime.date.today().strftime('%Y-%m-%d'),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import FinancialTransaction
        org = request.user.staff.org
        try:
            title = request.POST.get('title', '').strip()
            amount = request.POST.get('amount')
            transaction_date = request.POST.get('transaction_date')
            if not all([title, amount, transaction_date]):
                messages.error(request, "Title, amount, and date are required.")
                return redirect('staff:add_expense')
            FinancialTransaction.objects.create(
                org=org, transaction_type='expense', title=title, amount=amount,
                category_id=request.POST.get('category') or None, branch_id=request.POST.get('branch') or None,
                transaction_date=transaction_date, payment_method=request.POST.get('payment_method', 'cash'),
                note=request.POST.get('note', ''), reference_number=request.POST.get('reference_number', ''),
                created_by=request.user,
            )
            messages.success(request, f"Expense '{title}' added successfully.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
        return redirect('staff:add_expense')


class StaffExportHubView(LoginRequiredMixin, View):
    """
    Delegated export hub, surfacing only the exports this staff member's
    flags actually allow. Unlike the admin ExportHubView, this links to
    staff-namespaced CSV views below — the admin schooladmin/export/* routes
    are unreachable for staff regardless of permission flags, since
    SecurityEnforcementMiddleware blocks the whole schooladmin/ prefix for
    non-admin users before any view-level check runs.
    """
    template_name = 'staff/export_hub.html'

    def get(self, request, *args, **kwargs):
        from school.features import has_perm
        from django.urls import reverse
        exports = []
        if has_perm(request.user, 'can_bulk_export'):
            exports.append({'label': 'Payslips', 'url': reverse('staff:export_payslips')})
        if has_perm(request.user, 'can_view_stock'):
            exports.append({'label': 'Stock', 'url': reverse('staff:export_stock')})
        if has_perm(request.user, 'can_view_finance'):
            exports.append({'label': 'Finance', 'url': reverse('staff:export_finance')})
        if has_perm(request.user, 'can_view_leave_report'):
            exports.append({'label': 'Leave', 'url': reverse('staff:export_leave')})
        if has_perm(request.user, 'can_export_reports'):
            exports.append({'label': 'Attendance', 'url': reverse('staff:export_attendance')})
            exports.append({'label': 'Members', 'url': reverse('staff:export_members')})
            exports.append({'label': 'Tasks', 'url': reverse('staff:export_tasks_csv')})
        return render(request, self.template_name, {'exports': exports})


class StaffExportPayslipsView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's payslips, delegated via can_bulk_export."""
    required_feature = 'bulk_export'
    required_perm = 'can_bulk_export'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        org = request.user.staff.org
        slips = PaySlip.objects.filter(org=org).select_related('member').order_by('-from_date')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="payslips.csv"'
        w = csv.writer(resp)
        w.writerow(['Member', 'Period', 'Gross Salary', 'Net Payable', 'Status'])
        for s in slips:
            w.writerow([s.member.name, f"{s.from_date} to {s.to_date}", s.gross_salary, s.net_payable, s.status])
        return resp


class StaffExportStockView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's stock items, delegated via can_view_stock."""
    required_feature = 'stock'
    required_perm = 'can_view_stock'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        from handle.models import StockItem
        org = request.user.staff.org
        items = StockItem.objects.filter(org=org).select_related('branch', 'category').order_by('name')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="stock_items.csv"'
        w = csv.writer(resp)
        w.writerow(['Name', 'SKU', 'Branch', 'Quantity', 'Unit', 'Status'])
        for i in items:
            w.writerow([i.name, i.sku, i.branch.name if i.branch else '', i.quantity, i.unit, i.status])
        return resp


class StaffExportFinanceView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's financial transactions, delegated via can_view_finance."""
    required_feature = 'finance'
    required_perm = 'can_view_finance'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        from handle.models import FinancialTransaction
        org = request.user.staff.org
        txs = FinancialTransaction.objects.filter(org=org).select_related('category', 'branch').order_by('-transaction_date')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="finance_transactions.csv"'
        w = csv.writer(resp)
        w.writerow(['Date', 'Type', 'Title', 'Amount', 'Category', 'Branch'])
        for t in txs:
            w.writerow([t.transaction_date, t.transaction_type, t.title, t.amount, t.category.name if t.category else '', t.branch.name if t.branch else ''])
        return resp


class StaffExportLeaveView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's leave records, delegated via can_view_leave_report."""
    required_feature = 'leave'
    required_perm = 'can_view_leave_report'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        org = request.user.staff.org
        qs = LeaveReport.objects.filter(org=org).select_related('member', 'leave_type').order_by('-id')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="leave_records.csv"'
        w = csv.writer(resp)
        w.writerow(['Member', 'Type', 'Start', 'End', 'Approved', 'Rejected'])
        for r in qs:
            w.writerow([r.member.name, r.leave_type.name if r.leave_type else '', r.gap_start, r.gap_end, r.approved, r.rejected])
        return resp


class StaffExportAttendanceView(LoginRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's attendance records, delegated via can_export_reports (a core, always-available permission per PERMISSION_REGISTRY)."""
    required_perm = 'can_export_reports'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        org = request.user.staff.org
        qs = AttendanceRecord.objects.filter(org=org).select_related('mem').order_by('-scanned_time')[:5000]
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="attendance.csv"'
        w = csv.writer(resp)
        w.writerow(['Member', 'Scanned Time', 'Method'])
        for r in qs:
            w.writerow([r.mem.name, r.scanned_time, r.attendance_method])
        return resp


class StaffExportMembersView(LoginRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's members, delegated via can_export_reports (a core, always-available permission per PERMISSION_REGISTRY)."""
    required_perm = 'can_export_reports'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        org = request.user.staff.org
        qs = member.objects.filter(org=org).exclude(status='dumped').order_by('name')
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="members.csv"'
        w = csv.writer(resp)
        w.writerow(['Name', 'Type', 'Phone', 'Email', 'Status'])
        for m in qs:
            w.writerow([m.name, m.member_type, m.phone, m.email, m.status])
        return resp


class StaffExportTasksView(LoginRequiredMixin, PermRequiredMixin, View):
    """CSV export of the org's task instances, delegated via can_export_reports (a core, always-available permission per PERMISSION_REGISTRY)."""
    required_perm = 'can_export_reports'

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse
        from handle.models import TaskInstance
        org = request.user.staff.org
        qs = TaskInstance.objects.filter(task__org=org).select_related('task', 'assigned_member').order_by('-due_date')[:5000]
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = 'attachment; filename="tasks.csv"'
        w = csv.writer(resp)
        w.writerow(['Task', 'Assigned To', 'Due Date', 'Status'])
        for i in qs:
            w.writerow([i.task.title, i.assigned_member.name if i.assigned_member else '', i.due_date, i.status])
        return resp


class StaffCreateTaskView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Assign a task to org members, delegated via can_assign_tasks. Org-wide assignee picker (no team/branch relation exists on Task)."""
    required_feature = 'tasks'
    required_perm = 'can_assign_tasks'
    template_name = 'staff/create_task.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Task, Branch
        org = request.user.staff.org
        return render(request, self.template_name, {
            'org': org, 'members': member.objects.filter(org=org, status='active').order_by('name'),
            'branches': Branch.objects.filter(org=org), 'priority_choices': Task.PRIORITY_CHOICES,
            'type_choices': Task.TASK_TYPE_CHOICES, 'today': datetime.date.today(),
        })

    def post(self, request, *args, **kwargs):
        from handle.models import Task
        from school.email_utils import send_task_assigned_email
        import datetime as _dt
        org = request.user.staff.org
        title = request.POST.get('title', '').strip()
        start_date = request.POST.get('start_date')
        due_date = request.POST.get('due_date')
        member_ids = request.POST.getlist('assigned_to')

        if not title or not start_date or not due_date or not member_ids:
            messages.error(request, "Title, dates, and at least one assignee are required.")
            return redirect('staff:create_task')
        try:
            sd = _dt.date.fromisoformat(start_date)
            dd = _dt.date.fromisoformat(due_date)
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('staff:create_task')
        if dd < sd:
            messages.error(request, "Due date must be on or after start date.")
            return redirect('staff:create_task')

        task = Task.objects.create(
            org=org, branch_id=request.POST.get('branch') or None, title=title,
            description=request.POST.get('description', ''), priority=request.POST.get('priority', 'medium'),
            task_type=request.POST.get('task_type', 'one_time'), start_date=sd, due_date=dd,
            due_time=request.POST.get('due_time') or None, notes=request.POST.get('notes', ''),
            requires_approval=request.POST.get('requires_approval') == 'on', created_by=request.user,
        )
        assigned_members = member.objects.filter(id__in=member_ids, org=org).exclude(status='dumped')
        task.assigned_to.set(assigned_members)
        task.generate_instances()
        assigned_by = request.user.get_full_name() or request.user.username
        for m in assigned_members:
            if m.email:
                send_task_assigned_email(m.email, m.name, task.title, str(dd), task.priority, org.name, assigned_by)
        from handle.notifications import notify_task_assigned
        notify_task_assigned(task, assigned_members, actor=request.user)
        messages.success(request, f"Task '{title}' created and assigned to {assigned_members.count()} member(s).")
        return redirect('staff:task_list')


class StaffTaskDashboardView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only task stats, delegated via can_manage_tasks."""
    required_feature = 'tasks'
    required_perm = 'can_manage_tasks'
    template_name = 'staff/task_dashboard.html'

    def get(self, request, *args, **kwargs):
        from handle.models import TaskInstance
        org = request.user.staff.org
        today = datetime.date.today()
        all_inst = TaskInstance.objects.filter(task__org=org)
        return render(request, self.template_name, {
            'org': org, 'today': today,
            'total': all_inst.count(), 'pending': all_inst.filter(status='pending').count(),
            'in_progress': all_inst.filter(status='in_progress').count(), 'completed': all_inst.filter(status='completed').count(),
            'overdue': all_inst.filter(status='overdue').count(),
            'pending_approval': all_inst.filter(approval_status='pending_approval').count(),
            'today_tasks': all_inst.filter(due_date=today).select_related('task', 'assigned_member'),
        })


class StaffTaskListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only task instance list, delegated via can_manage_tasks."""
    required_feature = 'tasks'
    required_perm = 'can_manage_tasks'
    template_name = 'staff/task_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Task, TaskInstance
        org = request.user.staff.org
        qs = TaskInstance.objects.filter(task__org=org).select_related('task', 'assigned_member').order_by('-due_date')[:200]
        return render(request, self.template_name, {
            'org': org, 'instances': qs, 'members': member.objects.filter(org=org, status='active').order_by('name'),
        })


class StaffTaskDetailView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """
    Approve/reject/reassign/cancel a single task instance, delegated via
    can_manage_tasks. Deliberately excludes 'deactivate' (kills the task
    definition for every assigned member at once) — stays admin-only.
    """
    required_feature = 'tasks'
    required_perm = 'can_manage_tasks'
    template_name = 'staff/task_detail.html'

    def get(self, request, pk, *args, **kwargs):
        from handle.models import Task
        org = request.user.staff.org
        task = get_object_or_404(Task, pk=pk, org=org)
        instances = task.instances.select_related('assigned_member', 'approved_by').order_by('due_date', 'assigned_member__name')
        return render(request, self.template_name, {
            'org': org, 'task': task, 'instances': instances,
            'members': member.objects.filter(org=org, status='active').order_by('name'),
        })

    def post(self, request, pk, *args, **kwargs):
        from handle.models import Task, TaskInstance, TaskUpdateLog
        from school.email_utils import send_task_approval_email, send_task_assigned_email
        org = request.user.staff.org
        task = get_object_or_404(Task, pk=pk, org=org)
        action = request.POST.get('action')
        inst_id = request.POST.get('instance_id')

        if action == 'approve_instance':
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            inst.approval_status = 'approved'
            inst.status = 'completed'
            inst.approved_by = request.user
            inst.approved_at = timezone.now()
            inst.save()
            log = TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status='completed', new_status='completed', note='Approved.')
            if inst.assigned_member.email:
                send_task_approval_email(inst.assigned_member.email, inst.assigned_member.name, task.title, 'approved', '', org.name)
            from handle.notifications import notify_task_assignee
            notify_task_assignee(
                inst, 'task_approved', f'Task approved: {task.title}',
                'Your task completion was approved.',
                actor=request.user, log_id=log.pk, priority='normal',
            )
            messages.success(request, "Task completion approved.")
        elif action == 'reject_instance':
            reason = request.POST.get('rejection_reason', '')
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            old_status = inst.status
            inst.approval_status = 'rejected'
            inst.status = 'rework_required'
            inst.rejection_reason = reason
            inst.approved_by = request.user
            inst.approved_at = timezone.now()
            inst.save()
            log = TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='rework_required', note=f'Rejected: {reason}')
            if inst.assigned_member.email:
                send_task_approval_email(inst.assigned_member.email, inst.assigned_member.name, task.title, 'rejected', reason, org.name)
            from handle.notifications import notify_task_assignee
            notify_task_assignee(
                inst, 'task_rejected', f'Rework required: {task.title}',
                reason or 'Your completion was returned for correction.',
                actor=request.user, log_id=log.pk, priority='urgent',
            )
            messages.success(request, "Task rejected and returned to staff.")
        elif action == 'reassign':
            new_m = get_object_or_404(member, pk=request.POST.get('new_member'), org=org)
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            old_member = inst.assigned_member
            old_status = inst.status
            inst.assigned_member = new_m
            inst.status = 'pending'
            inst.completion_note = ''
            inst.save()
            task.assigned_to.add(new_m)
            log = TaskUpdateLog.objects.create(
                instance=inst, changed_by=request.user,
                old_status=old_status, new_status='pending',
                note=f'Reassigned from {old_member.name} to {new_m.name}.',
            )
            if new_m.email:
                send_task_assigned_email(new_m.email, new_m.name, task.title, str(inst.due_date), task.priority, org.name, 'Reassigned')
            from django.urls import reverse
            from handle.notifications import notify, notify_task_assignee
            if old_member.pk != new_m.pk:
                notify(
                    old_member, 'task_reassigned', f'Task reassigned: {task.title}',
                    f'This task was reassigned to {new_m.name}.',
                    reverse('staff:my_tasks'), actor=request.user,
                    dedupe_key=f'task-reassigned-old:{inst.pk}:{log.pk}:{old_member.pk}',
                )
            notify_task_assignee(
                inst, 'task_reassigned', f'Task reassigned to you: {task.title}',
                f'Due {inst.due_date}.',
                actor=request.user, log_id=log.pk,
            )
            messages.success(request, f"Task reassigned to {new_m.name}.")
        elif action == 'cancel_instance':
            inst = get_object_or_404(TaskInstance, pk=inst_id, task=task)
            old = inst.status
            inst.status = 'cancelled'
            inst.save()
            log = TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old, new_status='cancelled', note='Cancelled.')
            from handle.notifications import notify_task_assignee
            notify_task_assignee(
                inst, 'task_cancelled', f'Task cancelled: {task.title}',
                f'The task due {inst.due_date} was cancelled.',
                actor=request.user, log_id=log.pk, priority='normal',
            )
            messages.success(request, "Task instance cancelled.")
        else:
            messages.error(request, "Invalid action.")
        return redirect('staff:task_detail', pk=pk)


class StaffTaskReportView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Read-only filtered task report, delegated via can_view_task_report."""
    required_feature = 'tasks'
    required_perm = 'can_view_task_report'
    template_name = 'staff/task_report.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Task, TaskInstance
        org = request.user.staff.org
        qs = TaskInstance.objects.filter(task__org=org).select_related('task', 'assigned_member')
        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')
        if from_date:
            qs = qs.filter(due_date__gte=from_date)
        if to_date:
            qs = qs.filter(due_date__lte=to_date)
        qs = qs.order_by('-due_date')[:500]
        return render(request, self.template_name, {
            'org': org, 'instances': qs, 'from_date': from_date, 'to_date': to_date,
        })


class StaffComplaintListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Org-wide complaint list, delegated via can_manage_complaints."""
    required_feature = 'complaints'
    required_perm = 'can_manage_complaints'
    template_name = 'staff/complaint_list.html'

    def get(self, request, *args, **kwargs):
        from handle.models import Complaint
        org = request.user.staff.org
        qs = Complaint.objects.filter(org=org).select_related('filed_by').order_by('-created_at')
        status = request.GET.get('status')
        if status:
            qs = qs.filter(status=status)
        return render(request, self.template_name, {
            'org': org, 'complaints': qs, 'status_choices': Complaint.STATUS_CHOICES,
            'selected_status': status, 'pending_count': Complaint.objects.filter(org=org, status='pending').count(),
        })


class StaffComplaintDetailView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """Resolve a complaint (with notify-filer email), delegated via can_manage_complaints."""
    required_feature = 'complaints'
    required_perm = 'can_manage_complaints'
    template_name = 'staff/complaint_detail.html'

    def get(self, request, pk, *args, **kwargs):
        from handle.models import Complaint
        org = request.user.staff.org
        complaint = get_object_or_404(
            Complaint.objects.prefetch_related('messages'),
            pk=pk,
            org=org,
        )
        return render(request, self.template_name, {'org': org, 'complaint': complaint, 'status_choices': Complaint.STATUS_CHOICES})

    def post(self, request, pk, *args, **kwargs):
        from handle.models import Complaint, ComplaintMessage
        from school.email_utils import send_complaint_update_email
        from django.utils.timezone import now
        org = request.user.staff.org
        complaint = get_object_or_404(Complaint, pk=pk, org=org)
        old_status = complaint.status
        complaint.status = request.POST.get('status', complaint.status)
        complaint.admin_remarks = request.POST.get('admin_remarks', '')
        reply_message = request.POST.get('reply_message', '').strip()
        if complaint.status == 'resolved' and not complaint.resolution_date:
            complaint.resolution_date = now().date()
        complaint.save()
        if reply_message:
            ComplaintMessage.objects.create(
                complaint=complaint,
                author=request.user,
                message=reply_message,
                is_staff_reply=True,
            )

        if complaint.status != old_status and complaint.filed_by.email:
            send_complaint_update_email(
                email=complaint.filed_by.email, name=complaint.filed_by.name, subject_text=complaint.subject,
                status=complaint.status, remarks=complaint.admin_remarks, org_name=org.name,
            )
        messages.success(request, "Complaint updated.")
        return redirect('staff:complaint_detail', pk=pk)


class StaffWifiCheckinView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'wifi'
    template_name = 'staff/wifi_checkin.html'

    def get(self, request, *args, **kwargs):
        org = request.user.staff.org

        # Security Check: We are using 'qr_based' to enable WiFi features based on your model
        if not org.qr_based:
            messages.error(request, "WiFi Auto Check-in is not enabled for your organization.")
            return redirect('staff:dashboard')

        return render(request, self.template_name, {'org': org})

# ─── Student Portal Views ─────────────────────────────────────────────────────

class StudentSelfServiceMixin:
    """Restrict self-service pages to the signed-in student/trainee.

    Organisation feature gates are applied by ``FeatureRequiredMixin``. Staff
    management permissions must not be reused here: a student reads only
    records already scoped to their own member profile.
    """

    def dispatch(self, request, *args, **kwargs):
        profile = getattr(request.user, 'staff', None)
        memb = getattr(profile, 'member', None)
        if memb is None or memb.member_type not in ('student', 'trainee'):
            messages.error(request, 'This page is available only in the student portal.')
            return redirect('staff:dashboard')
        return super().dispatch(request, *args, **kwargs)


class StudentBillsView(
    LoginRequiredMixin, FeatureRequiredMixin, StudentSelfServiceMixin, View
):
    required_feature = 'billing'
    template_name = 'staff/student_bills.html'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import Bill
        bills = Bill.objects.filter(member=memb, org=org).prefetch_related('items').order_by('-issue_date')
        return render(request, self.template_name, {'org': org, 'memb': memb, 'bills': bills})


class StudentResultsView(
    LoginRequiredMixin, FeatureRequiredMixin, StudentSelfServiceMixin, View
):
    required_feature = 'results'
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


class StudentGapsView(LoginRequiredMixin, StudentSelfServiceMixin, View):
    template_name = 'staff/student_gaps.html'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        org = request.user.staff.org
        from handle.models import AttendanceGap
        gaps = AttendanceGap.objects.filter(member=memb, org=org).order_by('-date')
        return render(request, self.template_name, {'org': org, 'memb': memb, 'gaps': gaps})


class StudentComplaintView(
    LoginRequiredMixin, FeatureRequiredMixin, StudentSelfServiceMixin, View
):
    required_feature = 'complaints'
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

def _assigned_course_queryset(user, org):
    """Return active courses this staff user is explicitly allowed to teach."""
    from django.db.models import Q
    from handle.models import Course

    # Course.teacher is the legacy primary-teacher field. Keep it as a
    # compatibility fallback while CourseTeacherAssignment is authoritative
    # for all assignments made through the current admin screen.
    return Course.objects.filter(
        org=org,
        status='active',
    ).filter(
        Q(teacher=user) | Q(teacher_assignments__teacher=user)
    ).distinct()


@login_required(login_url='/login/')
def api_assigned_course_members(request, course_id):
    """Return the roster only when the course is assigned to this staff user."""
    if getattr(request.user, 'user_type', '') != '3' or not hasattr(request.user, 'staff'):
        return JsonResponse({'error': 'Staff access required.'}, status=403)

    org = request.user.staff.org
    course = _assigned_course_queryset(request.user, org).filter(pk=course_id).first()
    if not course:
        return JsonResponse({'error': 'Course is not assigned to you.'}, status=403)

    roster = member.objects.filter(
        org=org,
        courses=course,
        status='active',
    ).select_related('classification', 'section').distinct().order_by('name')
    return JsonResponse({
        'course_id': course.pk,
        'course_name': course.name,
        'members': [
            {
                'id': m.pk,
                'name': m.name,
                'classification': m.classification.name if m.classification else '',
                'section': m.section.name if m.section else '',
            }
            for m in roster
        ],
    })


class TeachingLogView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'academic_management'
    required_perm = 'can_view_attendance'
    """Legacy URL: course attendance now runs through subject assignments."""
    template_name = 'staff/teaching_log.html'

    def get(self, request, *args, **kwargs):
        return redirect('staff:subject_teaching_log')
        org = request.user.staff.org
        from handle.models import CourseAttendance
        courses = _assigned_course_queryset(request.user, org).prefetch_related(
            'classifications', 'sections'
        )
        logs = CourseAttendance.objects.filter(
            staff=request.user, org=org
        ).select_related('course', 'classification', 'section').order_by(
            '-attendance_date', '-pk'
        )[:20]
        return render(request, self.template_name, {
            'org': org, 'courses': courses, 'logs': logs,
        })

    def post(self, request, *args, **kwargs):
        return redirect('staff:subject_teaching_log')
        org = request.user.staff.org
        from handle.models import Course, CourseAttendance, AttendanceGap
        course_id = request.POST.get('course_id')
        topic = request.POST.get('topic_taught', '').strip()
        gap_note = request.POST.get('gap_note', '').strip()
        date_str = request.POST.get('attendance_date', '')
        mark_absent_ids = request.POST.getlist('absent_member_ids')

        if not course_id or not topic:
            messages.error(request, "Course and topic are required.")
            return redirect('staff:teaching_log')

        try:
            course = _assigned_course_queryset(request.user, org).get(pk=course_id)
            att_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.date.today()
        except Course.DoesNotExist:
            messages.error(request, "That course is not assigned to you.")
            return redirect('staff:teaching_log')
        except (ValueError, TypeError):
            messages.error(request, "Please enter a valid attendance date.")
            return redirect('staff:teaching_log')

        roster = member.objects.filter(
            org=org, courses=course, status='active'
        ).select_related('classification', 'section').distinct()
        allowed_member_ids = set(roster.values_list('pk', flat=True))
        absent_member_ids = {
            int(mid) for mid in mark_absent_ids
            if str(mid).isdigit() and int(mid) in allowed_member_ids
        }

        classifications = list(course.classifications.all()[:2])
        sections = list(course.sections.all()[:2])
        classification = classifications[0] if len(classifications) == 1 else None
        branch = course.branch
        section = sections[0] if len(sections) == 1 else None

        log = CourseAttendance.objects.filter(
            org=org,
            staff=request.user,
            course=course,
            attendance_date=att_date,
        ).order_by('pk').first()
        if log:
            log.branch = branch
            log.classification = classification
            log.section = section
            log.topic_taught = topic
            log.gap_note = gap_note
            log.save(update_fields=[
                'branch', 'classification', 'section', 'topic_taught', 'gap_note'
            ])
        else:
            CourseAttendance.objects.create(
                org=org, staff=request.user, course=course,
                branch=branch, classification=classification,
                section=section, attendance_date=att_date,
                topic_taught=topic, gap_note=gap_note,
            )

        for m in roster.filter(pk__in=absent_member_ids):
            AttendanceGap.objects.update_or_create(
                org=org, member=m, course=course, date=att_date,
                defaults={
                    'branch': branch,
                    'classification': m.classification,
                    'section': m.section,
                    'teacher': request.user,
                    'topic_missed': topic,
                },
            )

        messages.success(request, f"Teaching log saved for {course.name} on {att_date}.")
        return redirect('staff:teaching_log')


class SubjectTeachingLogView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    """The Academic Management "Submit Teaching Log & Attendance" flow, for
    real teachers (user_type '3'). Core logic is shared with schooladmin's
    AddTeachingLogView via handle/academics.py — teachers never reach
    schooladmin/ URLs (blocked at the middleware level), so this staff-portal
    counterpart is required, not optional."""
    required_feature = 'academic_management'
    required_perm = 'can_view_attendance'
    template_name = 'staff/academic/teaching_log_form.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.user_type == '3':
            memb = getattr(getattr(request.user, 'staff', None), 'member', None)
            if memb and memb.member_type in ('student', 'trainee'):
                messages.error(request, "Only assigned teaching staff can mark subject attendance.")
                return redirect('staff:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.db.models import Q
        from handle.academics import (
            todays_routine_period_options, roster_for_subject,
            teacher_is_assigned_to_subject,
        )
        from handle.models import Classification, Section, Subject, TeachingLog
        from handle.forms import TeachingLogForm

        org = request.user.staff.org
        today = timezone.localdate()
        period_options = todays_routine_period_options(org, request.user, is_admin=False)
        selected_routine_period_id = request.GET.get('routine_period', '')
        assigned_subjects = Subject.objects.filter(
            org=org, status='active',
        ).filter(
            Q(
                teacher_assignments__teacher=request.user,
                teacher_assignments__status='active',
                teacher_assignments__start_date__lte=today,
            )
            & (
                Q(teacher_assignments__end_date__isnull=True)
                | Q(teacher_assignments__end_date__gte=today)
            )
            | Q(teacher=request.user, teacher_assignments__isnull=True)
        ).select_related('course', 'classification', 'section').distinct()

        manual_classification_id = request.GET.get('classification')
        manual_section_id = request.GET.get('section')
        manual_subject_id = request.GET.get('subject')
        manual_roster = None
        manual_subject = None
        if manual_classification_id and manual_subject_id:
            classification = Classification.objects.filter(org=org, pk=manual_classification_id).first()
            manual_subject = assigned_subjects.filter(
                pk=manual_subject_id,
                classification=classification,
            ).first()
            section = Section.objects.filter(
                org=org,
                pk=manual_section_id,
                classification=classification,
            ).first() if manual_section_id and classification else None
            if (
                classification
                and manual_subject
                and teacher_is_assigned_to_subject(
                    manual_subject, request.user, section=section,
                )
            ):
                if not manual_subject.section_id or manual_subject.section_id == getattr(section, 'pk', None):
                    manual_roster = roster_for_subject(
                        org, manual_subject, classification, section
                    )

        form = TeachingLogForm(org=org, initial={
            'classification': manual_classification_id or None,
            'section': manual_section_id or None,
            'subject': manual_subject_id or None,
            'date': request.GET.get('date') or today,
        })
        assigned_class_ids = assigned_subjects.values_list('classification_id', flat=True)
        form.fields['subject'].queryset = assigned_subjects
        form.fields['classification'].queryset = Classification.objects.filter(
            org=org, status='active', pk__in=assigned_class_ids
        ).distinct()
        form.fields['section'].queryset = Section.objects.filter(
            org=org, status='active', classification_id__in=assigned_class_ids
        ).distinct()

        context = {
            'org': org, 'form': form, 'today': today, 'is_admin': False,
            'period_options': period_options,
            'manual_roster': manual_roster,
            'manual_subject': manual_subject,
            'assigned_subjects': assigned_subjects,
            'manual_classification_id': manual_classification_id,
            'manual_section_id': manual_section_id,
            'manual_subject_id': manual_subject_id,
            'selected_routine_period_id': selected_routine_period_id,
            'teachers': None,
            'recent_logs': TeachingLog.objects.filter(
                org=org, teacher=request.user,
            ).select_related('course', 'subject', 'classification', 'section').order_by('-date', '-pk')[:10],
        }
        return render(request, self.template_name, context)

    def post(self, request):
        from handle.academics import submit_teaching_log_and_attendance
        from handle.models import TeachingLogAttachment

        org = request.user.staff.org
        log, error = submit_teaching_log_and_attendance(org, request.user, False, request.POST)
        if error:
            messages.error(request, error)
            return redirect('staff:subject_teaching_log')

        for f in request.FILES.getlist('attachments'):
            TeachingLogAttachment.objects.create(log=log, file=f)

        messages.success(request, "Teaching log & attendance submitted.")
        return redirect('staff:subject_teaching_log')


class TeacherSubjectAttendanceReportView(
    LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View
):
    required_feature = 'academic_management'
    required_perm = 'can_view_attendance'
    template_name = 'staff/academic/teacher_attendance_report.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.user_type == '3':
            memb = getattr(getattr(request.user, 'staff', None), 'member', None)
            if memb and memb.member_type in ('student', 'trainee'):
                messages.error(request, "Only teaching staff can view this report.")
                return redirect('staff:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from handle.models import Subject, SubjectAttendanceRecord

        org = request.user.staff.org
        today = timezone.localdate()
        month_start = today.replace(day=1)

        def parse_date(value, default):
            try:
                return datetime.datetime.strptime(value, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                return default

        date_from = parse_date(request.GET.get('date_from'), month_start)
        date_to = parse_date(request.GET.get('date_to'), today)
        if date_from > date_to:
            date_from, date_to = date_to, date_from
        subject_id = request.GET.get('subject', '')
        attendance_status = request.GET.get('status', '')

        records = SubjectAttendanceRecord.objects.filter(
            org=org,
            teaching_log__teacher=request.user,
            teaching_log__date__gte=date_from,
            teaching_log__date__lte=date_to,
        ).select_related(
            'member', 'teaching_log__course', 'teaching_log__classification',
            'teaching_log__section', 'teaching_log__subject',
        )
        if subject_id:
            records = records.filter(teaching_log__subject_id=subject_id)
        if attendance_status in dict(SubjectAttendanceRecord.STATUS_CHOICES):
            records = records.filter(status=attendance_status)
        records = records.order_by(
            '-teaching_log__date', 'teaching_log__period', 'member__name',
        )
        counts = {
            row['status']: row['total']
            for row in records.values('status').annotate(total=Count('pk'))
        }
        return render(request, self.template_name, {
            'org': org,
            'records': records,
            'counts': counts,
            'total': sum(counts.values()),
            'date_from': date_from,
            'date_to': date_to,
            'subjects': Subject.objects.filter(
                org=org, teaching_logs__teacher=request.user,
            ).distinct().order_by('name'),
            'status_choices': SubjectAttendanceRecord.STATUS_CHOICES,
            'selected_subject': subject_id,
            'selected_status': attendance_status,
        })


def _academic_teacher_api_context(request):
    if request.user.user_type != '3':
        return None, Response({'detail': 'Teaching staff access required.'}, status=403)
    try:
        org = request.user.staff.org
        memb = request.user.staff.member
    except Exception:
        return None, Response({'detail': 'A linked staff profile is required.'}, status=403)
    if memb and memb.member_type in ('student', 'trainee'):
        return None, Response({'detail': 'Teaching staff access required.'}, status=403)
    if not has_feature(org, 'academic_management'):
        return None, Response({'detail': 'Academic Management is not enabled.'}, status=403)
    return org, None


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def api_my_subject_assignments(request):
    """Mobile-safe hierarchy for the logged-in teacher's active assignments."""
    from handle.models import SubjectTeacherAssignment

    org, error = _academic_teacher_api_context(request)
    if error:
        return error
    today = timezone.localdate()
    assignments = SubjectTeacherAssignment.objects.filter(
        org=org,
        teacher=request.user,
        status='active',
        start_date__lte=today,
        classification__isnull=False,
        subject__status='active',
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    ).select_related(
        'academic_year', 'course', 'classification', 'section', 'subject',
    ).order_by('course__name', 'classification__name', 'section__name', 'subject__name')
    return Response({
        'results': [{
            'assignment_id': assignment.pk,
            'academic_year': (
                {'id': assignment.academic_year_id, 'name': assignment.academic_year.name}
                if assignment.academic_year_id else None
            ),
            'course': (
                {'id': assignment.subject.course_id, 'name': assignment.subject.course.name}
                if assignment.subject.course_id else None
            ),
            'classification': {
                'id': assignment.classification_id,
                'name': assignment.classification.name,
            },
            'section': (
                {'id': assignment.section_id, 'name': assignment.section.name}
                if assignment.section_id else None
            ),
            'subject': {'id': assignment.subject_id, 'name': assignment.subject.name},
            'start_date': assignment.start_date,
            'end_date': assignment.end_date,
            'is_primary': assignment.is_primary,
        } for assignment in assignments],
    })


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def api_assigned_subject_roster(request, subject_id):
    """Server-reconstructed roster; posted student IDs are never trusted."""
    from handle.academics import roster_for_subject, subject_assignment_for_teacher
    from handle.models import AcademicYear, Subject

    org, error = _academic_teacher_api_context(request)
    if error:
        return error
    subject = Subject.objects.filter(
        pk=subject_id, org=org, status='active',
    ).select_related('course', 'classification', 'section').first()
    if not subject:
        return Response({'detail': 'Subject not found.'}, status=404)
    try:
        attendance_date = datetime.datetime.strptime(
            request.GET.get('date', ''), '%Y-%m-%d',
        ).date()
    except (TypeError, ValueError):
        attendance_date = timezone.localdate()
    academic_year = AcademicYear.objects.filter(
        pk=request.GET.get('academic_year'), org=org,
    ).first() if request.GET.get('academic_year') else None
    requested_section = None
    if request.GET.get('section'):
        from handle.models import Section
        requested_section = Section.objects.filter(
            pk=request.GET.get('section'),
            org=org,
            classification=subject.classification,
        ).first()
        if not requested_section:
            return Response({'detail': 'Section not found.'}, status=404)
    assignment = subject_assignment_for_teacher(
        subject,
        request.user,
        on_date=attendance_date,
        academic_year=academic_year,
        section=requested_section or subject.section,
    )
    if assignment is False:
        return Response({'detail': 'This subject is not actively assigned to you.'}, status=403)
    roster = roster_for_subject(
        org,
        subject,
        subject.classification,
        requested_section or getattr(assignment, 'section', None) or subject.section,
        attendance_date=attendance_date, academic_year=academic_year,
    )
    return Response({
        'subject': {
            'id': subject.pk,
            'name': subject.name,
            'course_id': subject.course_id,
            'course': subject.course.name if subject.course_id else None,
            'classification_id': subject.classification_id,
            'classification': subject.classification.name,
            'section_id': (
                requested_section.pk
                if requested_section
                else getattr(assignment, 'section_id', None)
            ),
            'section': (
                requested_section.name
                if requested_section
                else (
                    assignment.section.name
                    if getattr(assignment, 'section_id', None)
                    else None
                )
            ),
        },
        'students': [{
            'id': student.pk,
            'name': student.name,
            'roll_number': student.roll_number,
            'card': student.card,
        } for student in roster],
    })


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def api_submit_subject_attendance(request):
    """Idempotent API equivalent of the teacher dashboard attendance form."""
    from handle.academics import submit_teaching_log_and_attendance

    org, error = _academic_teacher_api_context(request)
    if error:
        return error
    payload = request.data.copy()
    attendance = request.data.get('attendance', [])
    if attendance and not isinstance(attendance, list):
        return Response({'detail': 'attendance must be a list.'}, status=400)
    for item in attendance:
        if not isinstance(item, dict) or not str(item.get('student_id', '')).isdigit():
            continue
        student_id = int(item['student_id'])
        payload[f'status_{student_id}'] = item.get('status', '')
        payload[f'remarks_{student_id}'] = item.get('remarks', '')
    log, submit_error = submit_teaching_log_and_attendance(
        org, request.user, False, payload,
    )
    if submit_error:
        return Response({'detail': submit_error}, status=400)
    return Response({
        'id': log.pk,
        'status': log.status,
        'course_id': log.course_id,
        'classification_id': log.classification_id,
        'section_id': log.section_id,
        'subject_id': log.subject_id,
        'date': log.date,
        'period': log.period,
        'attendance': {
            'present': log.attendance_present or 0,
            'absent': log.attendance_absent or 0,
            'late': log.attendance_late,
            'excused': log.attendance_excused,
            'leave': log.attendance_leave,
        },
    }, status=200)


# ============================================================
# TASK MANAGEMENT — Staff Views
# ============================================================

from handle.models import Task, TaskInstance, TaskUpdateLog, TaskAttachment
from school.email_utils import send_task_completed_email


class MyTasksView(FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'tasks'
    required_perm = 'can_view_tasks'
    template_name = 'staff/tasks/my_tasks.html'

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect('management:homepage')
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


class UpdateTaskStatusView(FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'tasks'
    required_perm = 'can_view_tasks'
    def post(self, request, pk):
        if not request.user.is_authenticated:
            return redirect('management:homepage')
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
            log = TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='in_progress')
            from handle.notifications import notify_task_managers
            notify_task_managers(
                inst, 'task_started', f'{memb.name} started a task',
                inst.task.title, actor=request.user, log_id=log.pk,
            )
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
            log = TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='completed', note=note)

            # Notify admin
            try:
                admin_profile = org.schooladmin_set.select_related('admin').first()
                if admin_profile and admin_profile.admin.email:
                    send_task_completed_email(admin_profile.admin.email, memb.name, inst.task.title, str(inst.completed_at), note, org.name)
            except Exception:
                pass
            from handle.notifications import notify_task_managers
            notify_task_managers(
                inst, 'task_completed', f'{memb.name} completed a task',
                f'{inst.task.title}. {note}'.strip(),
                actor=request.user, log_id=log.pk,
            )

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
            log = TaskUpdateLog.objects.create(instance=inst, changed_by=request.user, old_status=old_status, new_status='not_completed', note=f'{reason}: {detail}')
            from handle.notifications import notify_task_managers
            notify_task_managers(
                inst, 'task_not_completed',
                f'{memb.name} could not complete a task',
                f'{inst.task.title}: {detail or reason}',
                actor=request.user, log_id=log.pk,
            )
            _msg.success(request, "Task status saved.")

        return redirect('staff:my_tasks')


# ── RESIGNATION ────────────────────────────────────────────────────
from handle.models import ResignationRecord

class StaffResignationView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'hrms'
    template_name = 'staff/my_resignation.html'

    def _get_member_or_redirect(self, request):
        try:
            org = request.user.staff.org
        except Exception:
            return None, None, redirect('management:homepage')
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
            'nepali_enabled': getattr(org, 'nepali_date', False),
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


# ─── Dynamic QR Attendance (Staff Side) ──────────────────────────────────────

from handle.models import QRAttendanceSession, QRAttendanceScanLog
from django.utils import timezone as _tz
from rest_framework.decorators import api_view as _api_view, permission_classes as _pc
from rest_framework.permissions import IsAuthenticated as _IsAuth
from rest_framework.response import Response as _Resp
from rest_framework import status as _status
import secrets as _secrets


class StaffQRScanView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'qr_attendance'
    required_perm = 'can_scan_qr_attendance'
    """Web page with camera scanner for staff/students to scan admin QR."""
    template_name = 'staff/qr_scan.html'
    login_url = '/'

    def get(self, request, *args, **kwargs):
        try:
            org = request.user.staff.org
        except Exception:
            messages.error(request, "Staff profile not found.")
            return redirect('/')
        if not org.enable_qr_attendance:
            messages.error(request, "QR Attendance is not enabled for your organization.")
            return redirect('staff:dashboard')
        return render(request, self.template_name, {'org': org})


@_api_view(['POST'])
@_pc([_IsAuth])
def api_qr_attendance_scan(request):
    """
    POST { token: <qr_token>, latitude?, longitude? }
    Validates the QR session and marks attendance.
    """
    def _get_ip(req):
        x_forward = req.META.get('HTTP_X_FORWARDED_FOR')
        return x_forward.split(',')[0].strip() if x_forward else req.META.get('REMOTE_ADDR')

    token = request.data.get('token', '').strip()
    if not token:
        return _Resp({'status': 'error', 'message': 'QR token is required.'}, status=_status.HTTP_400_BAD_REQUEST)

    # Resolve staff member
    try:
        memb = request.user.staff.member
        org = request.user.staff.org
    except Exception:
        return _Resp({'status': 'error', 'message': 'Staff profile not found. Please log in as a staff member.'}, status=_status.HTTP_403_FORBIDDEN)

    from django.db import transaction as _transaction
    from django.db.models import F as _F
    from school.features import has_feature as _has_feature, has_perm as _has_perm

    # Feature and staff-role permission are both enforced by the API. Students
    # retain self-service QR access when the organisation enables it.
    if not _has_feature(org, 'qr_attendance'):
        return _Resp({'status': 'error', 'message': 'QR Attendance is not enabled for your organization.'}, status=_status.HTTP_403_FORBIDDEN)
    if memb.member_type not in {'student', 'trainee'} and not _has_perm(
        request.user, 'can_scan_qr_attendance'
    ):
        return _Resp(
            {'status': 'error', 'message': 'You do not have permission to scan QR attendance.'},
            status=_status.HTTP_403_FORBIDDEN,
        )

    # Check member active
    INACTIVE_STATUSES = {'inactive', 'resigned', 'passed_out', 'dropped', 'suspended'}
    if memb.status in INACTIVE_STATUSES or memb.black_list:
        return _Resp({
            'status': 'error',
            'message': 'Your account is inactive. Please contact your administrator.'
        }, status=_status.HTTP_403_FORBIDDEN)

    ip = _get_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '')[:500]

    def _log_failure(session, reason_code, reason_msg):
        QRAttendanceScanLog.objects.create(
            session=session, member=memb, org=org,
            status=reason_code, failure_reason=reason_msg,
            ip_address=ip, user_agent=ua,
        )
        QRAttendanceSession.objects.filter(pk=session.pk).update(
            total_scans=_F('total_scans') + 1,
        )

    with _transaction.atomic():
        try:
            session = (
                QRAttendanceSession.objects.select_for_update()
                .select_related('org', 'branch')
                .get(token=token)
            )
        except QRAttendanceSession.DoesNotExist:
            return _Resp(
                {'status': 'invalid_qr', 'message': 'Invalid QR code. Please ask admin to generate a new QR.'},
                status=_status.HTTP_404_NOT_FOUND,
            )

        if session.org_id != org.id:
            _log_failure(session, 'invalid_org', 'The QR session belongs to another organization.')
            return _Resp({'status': 'invalid_org', 'message': 'This QR code is not for your organization.'}, status=_status.HTTP_403_FORBIDDEN)

        if session.branch_id and session.branch_id != memb.branch_id:
            _log_failure(session, 'error', 'The QR session belongs to another branch.')
            return _Resp({'status': 'invalid_branch', 'message': 'This QR code is not for your branch.'}, status=_status.HTTP_403_FORBIDDEN)

        now = _tz.now()
        today = _tz.localdate()
        if session.status == 'closed':
            _log_failure(session, 'session_closed', 'Session was manually closed by admin.')
            return _Resp({'status': 'session_closed', 'message': 'QR session has been closed by admin. Please ask for a new QR.'}, status=_status.HTTP_410_GONE)

        if session.session_type == 'permanent':
            import math

            user_lat = request.data.get('latitude')
            user_lon = request.data.get('longitude')
            if user_lat in (None, '') or user_lon in (None, ''):
                _log_failure(
                    session,
                    'location_required',
                    'A location fix is required for a permanent QR.',
                )
                return _Resp({
                    'status': 'location_required',
                    'message': 'Location is required for this permanent attendance QR.',
                }, status=_status.HTTP_400_BAD_REQUEST)
            try:
                user_lat = float(user_lat)
                user_lon = float(user_lon)
            except (TypeError, ValueError):
                return _Resp({
                    'status': 'location_required',
                    'message': 'A valid GPS location is required.',
                }, status=_status.HTTP_400_BAD_REQUEST)
            if (
                not math.isfinite(user_lat)
                or not math.isfinite(user_lon)
                or not -90 <= user_lat <= 90
                or not -180 <= user_lon <= 180
            ):
                return _Resp({
                    'status': 'location_required',
                    'message': 'A valid GPS location is required.',
                }, status=_status.HTTP_400_BAD_REQUEST)
            if session.latitude is None or session.longitude is None:
                _log_failure(
                    session,
                    'error',
                    'Permanent QR has no configured geofence.',
                )
                return _Resp({
                    'status': 'error',
                    'message': 'This permanent QR is not configured safely.',
                }, status=_status.HTTP_409_CONFLICT)
            distance = haversine_distance(
                user_lat,
                user_lon,
                session.latitude,
                session.longitude,
            )
            if distance > session.radius_meters:
                _log_failure(
                    session,
                    'outside_geofence',
                    f'Outside geofence by {round(distance - session.radius_meters)} metres.',
                )
                return _Resp({
                    'status': 'outside_geofence',
                    'message': (
                        f'You are {round(distance)} metres from '
                        f'{session.location_name or "the attendance location"}. '
                        f'Move within {session.radius_meters} metres and scan again.'
                    ),
                    'distance_meters': round(distance),
                }, status=_status.HTTP_403_FORBIDDEN)
        elif (
            session.status == 'expired'
            or not session.expires_at
            or now > session.expires_at
            or session.date != today
        ):
            if session.status == 'active':
                session.status = 'expired'
                session.save(update_fields=['status'])
            _log_failure(session, 'expired', 'QR session has expired or is for another date.')
            return _Resp({'status': 'expired', 'message': 'QR expired. Please ask admin to generate a new QR.'}, status=_status.HTTP_410_GONE)

        if now < session.valid_from:
            _log_failure(session, 'error', 'QR session is not active yet.')
            return _Resp({'status': 'not_active', 'message': 'This QR session is not active yet.'}, status=_status.HTTP_409_CONFLICT)

        from handle.attendance_writes import (
            DuplicateAttendancePunch,
            create_attendance_punch,
        )
        try:
            record, already_marked = create_attendance_punch(
                memb=memb,
                org=org,
                attendance_method='qr',
                scanned_time=now,
            )
        except DuplicateAttendancePunch as duplicate:
            _log_failure(session, 'duplicate', 'Repeated attendance inside the 60-second cooldown.')
            return _Resp(
                {
                    'status': 'duplicate',
                    'message': 'Attendance was already recorded. Please wait one minute before scanning again.',
                    'retry_after_seconds': duplicate.retry_after,
                },
                status=_status.HTTP_429_TOO_MANY_REQUESTS,
            )
        QRAttendanceScanLog.objects.create(
            session=session,
            member=memb,
            org=org,
            attendance_record=record,
            status='success',
            ip_address=ip,
            user_agent=ua,
        )
        QRAttendanceSession.objects.filter(pk=session.pk).update(
            total_scans=_F('total_scans') + 1,
            successful_scans=_F('successful_scans') + 1,
        )

    if already_marked:
        return _Resp({
            'status': 'check_out',
            'message': 'Check-out marked via QR Attendance.',
            'attendance_time': _tz.localtime(record.scanned_time).strftime('%H:%M:%S'),
        }, status=_status.HTTP_200_OK)

    return _Resp({
        'status': 'success',
        'message': 'Attendance marked successfully via QR.',
        'attendance_time': _tz.localtime(record.scanned_time).strftime('%H:%M:%S'),
        'member_name': memb.name,
    }, status=_status.HTTP_201_CREATED)


# ─── Timesheet Staff Views ────────────────────────────────────────────────────

import nepali_datetime as _ts_nepali
from handle.models import Timesheet as _TS, TimesheetEntry as _TSEntry
from django.utils import timezone as _ts_tz
from django.db.models import Sum as _Sum


def _ts_get_member(request):
    """Return (member, org) or raise."""
    try:
        return request.user.staff.member, request.user.staff.org
    except Exception:
        return None, None


def _ts_to_ad(date_str, nepali_enabled):
    """Convert a date string (AD or BS) to a Python date. Returns None on failure."""
    import datetime as _dt
    if not date_str:
        return None
    date_str = date_str.strip().replace('/', '-')
    try:
        if nepali_enabled:
            y, m, d = map(int, date_str.split('-'))
            return _ts_nepali.date(y, m, d).to_datetime_date()
        return _dt.date.fromisoformat(date_str)
    except Exception:
        return None


class StaffTimesheetListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_view_timesheets'
    template_name = 'staff/timesheet_list.html'

    def get(self, request):
        memb, org = _ts_get_member(request)
        if not memb:
            messages.error(request, "No member profile found.")
            return redirect('staff:dashboard')
        if not org or not org.feature_timesheet:
            messages.error(request, "Timesheet module is not enabled.")
            return redirect('staff:dashboard')

        qs = _TS.objects.filter(member=memb, org=org)
        status_f = request.GET.get('status', '')
        if status_f:
            qs = qs.filter(status=status_f)
        date_from = request.GET.get('date_from', '')
        date_to = request.GET.get('date_to', '')
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)

        nepali_enabled = getattr(org, 'nepali_date', False)
        timesheets = list(qs)
        if nepali_enabled:
            for ts in timesheets:
                ts.date_np = to_bs_display(ts.date)
        return render(request, self.template_name, {
            'org': org, 'timesheets': timesheets,
            'status_f': status_f, 'date_from': date_from, 'date_to': date_to,
            'nepali_enabled': nepali_enabled,
        })


class StaffTimesheetCreateView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_submit_timesheets'
    template_name = 'staff/timesheet_create.html'

    def get(self, request):
        memb, org = _ts_get_member(request)
        if not memb or not org or not org.feature_timesheet:
            return redirect('staff:dashboard')
        nepali_enabled = getattr(org, 'nepali_date', False)
        return render(request, self.template_name, {
            'org': org, 'nepali_enabled': nepali_enabled,
        })

    def post(self, request):
        memb, org = _ts_get_member(request)
        if not memb or not org or not org.feature_timesheet:
            return redirect('staff:dashboard')

        nepali_enabled = getattr(org, 'nepali_date', False)
        date_ad = _ts_to_ad(request.POST.get('date'), nepali_enabled)
        title   = request.POST.get('title', '').strip()

        if not date_ad:
            messages.error(request, "Invalid date. Please check and try again.")
            return render(request, self.template_name, {'org': org, 'nepali_enabled': nepali_enabled})

        if _TS.objects.filter(member=memb, org=org, date=date_ad).exists():
            messages.error(request, "A timesheet already exists for this date. Edit the existing one instead.")
            return render(request, self.template_name, {'org': org, 'nepali_enabled': nepali_enabled})

        ts = _TS.objects.create(
            member=memb, org=org, date=date_ad,
            title=title or f"Timesheet — {date_ad}",
        )
        messages.success(request, "Timesheet created. Add your entries below.")
        return redirect('staff:timesheet_detail', pk=ts.pk)


class StaffTimesheetDetailView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_view_timesheets'
    template_name = 'staff/timesheet_detail.html'

    def get(self, request, pk):
        memb, org = _ts_get_member(request)
        if not memb:
            return redirect('staff:dashboard')
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        nepali_enabled = getattr(org, 'nepali_date', False)
        if nepali_enabled:
            ts.date_np = to_bs_display(ts.date)
        entries = ts.entries.all()
        return render(request, self.template_name, {
            'org': org, 'ts': ts, 'entries': entries,
            'nepali_enabled': nepali_enabled,
        })


class StaffTimesheetEntryAddView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_submit_timesheets'
    """HTMX: POST → add entry row; GET → return add-entry inline form."""

    def get(self, request, pk):
        memb, org = _ts_get_member(request)
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        nepali_enabled = getattr(org, 'nepali_date', False)
        if request.GET.get('cancel'):
            return render(request, 'staff/partials/_ts_add_trigger.html', {
                'ts': ts, 'nepali_enabled': nepali_enabled,
            })
        return render(request, 'staff/partials/_ts_entry_form.html', {
            'ts': ts, 'entry': None, 'nepali_enabled': nepali_enabled,
        })

    def post(self, request, pk):
        memb, org = _ts_get_member(request)
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        if not ts.can_edit():
            from django.http import HttpResponse
            return HttpResponse('<div class="alert alert-warning m-2">Timesheet is locked.</div>')

        nepali_enabled = getattr(org, 'nepali_date', False)
        task    = request.POST.get('task', '').strip()
        hours   = request.POST.get('hours', '').strip()
        notes   = request.POST.get('notes', '').strip()

        errors = []
        if not task:
            errors.append("Task/project name is required.")
        try:
            hours_val = float(hours)
            if hours_val <= 0 or hours_val > 24:
                errors.append("Hours must be between 0 and 24.")
        except (ValueError, TypeError):
            errors.append("Enter a valid number of hours.")
            hours_val = 0

        if errors:
            return render(request, 'staff/partials/_ts_entry_form.html', {
                'ts': ts, 'entry': None, 'nepali_enabled': nepali_enabled,
                'errors': errors,
                'prev': {'task': task, 'hours': hours, 'notes': notes},
            })

        from decimal import Decimal
        entry = _TSEntry.objects.create(
            timesheet=ts, task=task,
            hours=Decimal(str(hours_val)), notes=notes,
        )

        return render(request, 'staff/partials/_ts_entry_row.html', {
            'entry': entry, 'ts': ts, 'nepali_enabled': nepali_enabled,
            'new': True,
        })


class StaffTimesheetEntryEditView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_submit_timesheets'
    """HTMX: GET → inline edit form; POST → save and return updated row."""

    def get(self, request, pk, entry_pk):
        memb, org = _ts_get_member(request)
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        entry = get_object_or_404(_TSEntry, pk=entry_pk, timesheet=ts)
        nepali_enabled = getattr(org, 'nepali_date', False)

        if request.GET.get('cancel'):
            return render(request, 'staff/partials/_ts_entry_row.html', {
                'entry': entry, 'ts': ts, 'nepali_enabled': nepali_enabled,
            })

        return render(request, 'staff/partials/_ts_entry_form.html', {
            'ts': ts, 'entry': entry, 'nepali_enabled': nepali_enabled,
            'prev': {'task': entry.task, 'hours': entry.hours, 'notes': entry.notes},
        })

    def post(self, request, pk, entry_pk):
        memb, org = _ts_get_member(request)
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        entry = get_object_or_404(_TSEntry, pk=entry_pk, timesheet=ts)
        if not ts.can_edit():
            from django.http import HttpResponse
            return HttpResponse('<div class="alert alert-warning m-2">Timesheet is locked.</div>')

        nepali_enabled = getattr(org, 'nepali_date', False)
        task    = request.POST.get('task', '').strip()
        hours   = request.POST.get('hours', '').strip()
        notes   = request.POST.get('notes', '').strip()

        errors = []
        if not task:
            errors.append("Task/project name is required.")
        try:
            hours_val = float(hours)
            if hours_val <= 0 or hours_val > 24:
                errors.append("Hours must be between 0 and 24.")
        except (ValueError, TypeError):
            errors.append("Enter a valid number of hours.")
            hours_val = 0

        if errors:
            return render(request, 'staff/partials/_ts_entry_form.html', {
                'ts': ts, 'entry': entry, 'nepali_enabled': nepali_enabled,
                'errors': errors,
                'prev': {'task': task, 'hours': hours, 'notes': notes},
            })

        from decimal import Decimal
        entry.task  = task
        entry.hours = Decimal(str(hours_val))
        entry.notes = notes
        entry.save()

        return render(request, 'staff/partials/_ts_entry_row.html', {
            'entry': entry, 'ts': ts, 'nepali_enabled': nepali_enabled,
        })


class StaffTimesheetEntryDeleteView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_submit_timesheets'
    def post(self, request, pk, entry_pk):
        memb, org = _ts_get_member(request)
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        if ts.can_edit():
            _TSEntry.objects.filter(pk=entry_pk, timesheet=ts).delete()
        from django.http import HttpResponse
        return HttpResponse('')


class StaffTimesheetSubmitView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'timesheet'
    required_perm = 'can_submit_timesheets'
    def post(self, request, pk):
        memb, org = _ts_get_member(request)
        ts = get_object_or_404(_TS, pk=pk, member=memb, org=org)
        if not ts.can_edit():
            if request.headers.get('HX-Request'):
                return render(request, 'staff/partials/_ts_status_bar.html', {'ts': ts})
            messages.warning(request, "Timesheet cannot be submitted in its current state.")
            return redirect('staff:timesheet_detail', pk=pk)
        if not ts.entries.exists():
            if request.headers.get('HX-Request'):
                from django.http import HttpResponse
                return HttpResponse('<div class="alert alert-warning mb-0">Add at least one entry before submitting.</div>')
            messages.error(request, "Add at least one entry before submitting.")
            return redirect('staff:timesheet_detail', pk=pk)

        ts.status = 'submitted'
        ts.submitted_at = _ts_tz.now()
        ts.admin_comment = ''
        ts.save()

        if request.headers.get('HX-Request'):
            return render(request, 'staff/partials/_ts_status_bar.html', {'ts': ts})
        messages.success(request, "Timesheet submitted for approval.")
        return redirect('staff:timesheet_detail', pk=pk)


# ─── Live Location Tracking (marketer trail) ─────────────────────────────────────

from handle.models import LocationPing


class StaffLiveTrackingView(
    LoginRequiredMixin,
    FeatureRequiredMixin,
    PermRequiredMixin,
    View,
):
    template_name = 'staff/live_tracking.html'
    required_feature = 'field_visits'
    required_perm = 'can_send_location'

    def get(self, request, *args, **kwargs):
        memb = request.user.staff.member
        enabled = bool(getattr(memb, 'live_tracking_enabled', False))
        last = LocationPing.objects.filter(member=memb).order_by('-tracked_at').first()
        return render(request, self.template_name, {'enabled': enabled, 'last': last})

    def post(self, request, *args, **kwargs):
        """Receive a single location ping (called repeatedly by the browser)."""
        memb = request.user.staff.member
        org = request.user.staff.org
        if not getattr(memb, 'live_tracking_enabled', False):
            return JsonResponse({'ok': False, 'error': 'Live tracking is not enabled for you.'}, status=403)
        try:
            lat = float(request.POST.get('latitude'))
            lon = float(request.POST.get('longitude'))
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': 'Invalid coordinates.'}, status=400)
        acc = request.POST.get('accuracy')
        try:
            acc = float(acc) if acc else None
        except (TypeError, ValueError):
            acc = None
        LocationPing.objects.create(member=memb, org=org, latitude=lat, longitude=lon, accuracy_meters=acc)
        return JsonResponse({'ok': True})


class StaffDynamicFeatureView(LoginRequiredMixin, View):
    """
    Generic landing page for any superadmin-defined DynamicFeature — the
    zero-code fallback so a brand new feature is reachable from the staff
    sidebar immediately, before (if ever) a bespoke module is built for it.
    """
    template_name = 'staff/dynamic_feature.html'

    def get(self, request, feature_key):
        from handle.models import DynamicFeature
        from school.features import has_feature, has_perm
        org = request.user.staff.org
        feature = get_object_or_404(DynamicFeature, key=feature_key, is_active=True)
        if not has_feature(org, feature_key):
            return render(request, '403.html', {
                'reason': f"The '{feature.label}' module is not enabled for your organization.",
            }, status=403)
        flags = list(feature.permissions.values_list('flag', flat=True))
        if flags and not any(has_perm(request.user, f) for f in flags):
            return render(request, '403.html', {
                'reason': "You don't have permission to access this page.",
            }, status=403)
        return render(request, self.template_name, {
            'org': org, 'feature': feature, 'permissions': feature.permissions.all(),
        })


# ═══════════════════════════════════════════════════════════════════════════
# NOTICE BOARD (staff / student side)
# ═══════════════════════════════════════════════════════════════════════════

def notices_for_member(memb, org, limit=None, unread_only=False):
    """Live notices addressed to `memb`, newest first, each annotated with
    `has_read`. Resolving audience per-notice (rather than one giant OR query)
    keeps the targeting logic in exactly one place — Notice.recipient_members."""
    from handle.models import Notice, NoticeRead
    from django.utils import timezone as _tz
    from django.db.models import Q

    if memb is None or org is None:
        return []

    now = _tz.now()
    candidates = Notice.objects.filter(org=org, publish_at__lte=now).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).select_related('branch', 'classification', 'section', 'course', 'shift', 'target_member')

    read_ids = set(
        NoticeRead.objects.filter(member=memb).values_list('notice_id', flat=True)
    )

    out = []
    for n in candidates:
        if not n.recipient_members().filter(id=memb.id).exists():
            continue
        has_read = n.id in read_ids
        if unread_only and has_read:
            continue
        n.has_read = has_read
        out.append(n)
        if limit and len(out) >= limit:
            break
    return out


def unread_notice_count(memb, org):
    return len(notices_for_member(memb, org, unread_only=True))


class StaffNoticeListView(LoginRequiredMixin, FeatureRequiredMixin, PermRequiredMixin, View):
    required_feature = 'notices'
    required_perm = 'can_view_notices'
    template_name = 'staff/notices.html'

    def get(self, request, *args, **kwargs):
        memb = getattr(request.user.staff, 'member', None)
        org = request.user.staff.org
        notices = notices_for_member(memb, org)

        show = request.GET.get('show', '')
        if show == 'unread':
            notices = [n for n in notices if not n.has_read]

        return render(request, self.template_name, {
            'org': org,
            'memb': memb,
            'notices': notices,
            'unread_count': sum(1 for n in notices_for_member(memb, org) if not n.has_read),
            'selected_show': show,
        })

    def post(self, request, *args, **kwargs):
        """Toggle read / unread for one notice, or mark every one read."""
        from handle.models import Notice, NoticeRead
        memb = getattr(request.user.staff, 'member', None)
        org = request.user.staff.org
        action = request.POST.get('action')

        if action == 'mark_all_read':
            for n in notices_for_member(memb, org, unread_only=True):
                NoticeRead.objects.get_or_create(notice=n, member=memb)
            messages.success(request, "All notices marked as read.")
            return redirect('staff:notices')

        notice_id = request.POST.get('notice_id')
        notice = Notice.objects.filter(id=notice_id, org=org).first()
        # Re-check audience so a tampered id can't mark a notice the member
        # was never sent.
        if notice is None or not notice.is_for_member(memb):
            messages.error(request, "That notice isn't available to you.")
            return redirect('staff:notices')

        if action == 'mark_unread':
            NoticeRead.objects.filter(notice=notice, member=memb).delete()
            messages.success(request, "Marked as unread.")
        else:
            NoticeRead.objects.get_or_create(notice=notice, member=memb)
            messages.success(request, "Marked as read.")
        return redirect('staff:notices')


# =============================================================
# ACADEMIC MANAGEMENT — assigned-teacher workflows
# =============================================================

def _academic_teacher_context(request):
    if request.user.user_type != '3':
        return None, None
    staff_profile = getattr(request.user, 'staff', None)
    memb = getattr(staff_profile, 'member', None)
    org = getattr(staff_profile, 'org', None)
    if not org or not memb or memb.member_type != 'teacher':
        return None, None
    return org, memb


def _teacher_scopes(request):
    from handle.academics import active_subject_assignments_for_teacher

    org, memb = _academic_teacher_context(request)
    if not org:
        return org, memb, None
    return org, memb, active_subject_assignments_for_teacher(
        org, request.user,
    )


class TeacherAssignmentListView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/teacher_assignment_list.html'

    def get(self, request):
        from handle.models import Assignment

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        scope_ids = scopes.values_list('pk', flat=True)
        assignments = Assignment.objects.filter(
            org=org,
        ).filter(
            Q(teacher_assignment_id__in=scope_ids) | Q(assigned_by=request.user)
        ).select_related(
            'teacher_assignment', 'subject', 'classification', 'section',
        ).prefetch_related('submissions').order_by('-due_date', '-pk')
        return render(request, self.template_name, {
            'org': org,
            'memb': memb,
            'assignments': assignments,
            'active_scope_count': scopes.count(),
        })


class TeacherAssignmentCreateView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/teacher_assignment_form.html'

    def get(self, request):
        from handle.forms import TeacherAssignmentForm

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        form = TeacherAssignmentForm(org=org, teacher=request.user)
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'form': form,
            'active_scope_count': scopes.count(),
        })

    def post(self, request):
        from django.db import transaction
        from handle.academics import roster_for_subject
        from handle.forms import TeacherAssignmentForm
        from handle.models import AssignmentAttachment
        from handle.notifications import notify_many

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        form = TeacherAssignmentForm(
            request.POST, org=org, teacher=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                assignment = form.save()
                for uploaded in request.FILES.getlist('attachments'):
                    AssignmentAttachment.objects.create(
                        assignment=assignment, file=uploaded,
                    )
                if assignment.visibility == 'published':
                    scope = assignment.teacher_assignment
                    students = roster_for_subject(
                        org,
                        assignment.subject,
                        assignment.classification,
                        assignment.section,
                        academic_year=scope.academic_year,
                    )
                    notify_many(
                        students,
                        'assignment_assigned',
                        f"New Assignment: {assignment.title}",
                        body=f"{assignment.subject.name} · Due {assignment.due_date}",
                        link_url=f'/staff/assignments/{assignment.pk}/submit/',
                    )
            messages.success(request, f"Assignment '{assignment.title}' published.")
            return redirect('staff:teacher_assignment_detail', pk=assignment.pk)
        messages.error(request, "Please correct the assignment errors below.")
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'form': form,
            'active_scope_count': scopes.count(),
        })


class TeacherAssignmentDetailView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/teacher_assignment_detail.html'

    def _assignment(self, request, pk, org, scopes):
        from handle.models import Assignment

        return get_object_or_404(
            Assignment.objects.filter(org=org).filter(
                Q(teacher_assignment__in=scopes) | Q(assigned_by=request.user)
            ).select_related(
                'teacher_assignment', 'subject', 'classification', 'section',
            ),
            pk=pk,
        )

    def get(self, request, pk):
        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        assignment = self._assignment(request, pk, org, scopes)
        submissions = assignment.submissions.select_related(
            'student',
        ).prefetch_related('attachments').order_by('-submitted_at')
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'assignment': assignment,
            'submissions': submissions,
        })

    def post(self, request, pk):
        from django.db import transaction
        from django.urls import reverse
        from handle.forms import AssignmentGradeForm
        from handle.models import (
            AssignmentSubmission, AssignmentSubmissionHistory,
        )
        from handle.notifications import notify

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        assignment = self._assignment(request, pk, org, scopes)
        submission = get_object_or_404(
            AssignmentSubmission,
            pk=request.POST.get('submission_id'),
            assignment=assignment,
        )
        form = AssignmentGradeForm(request.POST, instance=submission)
        if form.is_valid():
            with transaction.atomic():
                submission = form.save(commit=False)
                submission.graded_by = request.user
                submission.graded_at = timezone.now()
                submission.save()
                AssignmentSubmissionHistory.objects.create(
                    submission=submission,
                    action='graded',
                    status=submission.status,
                    obtained_marks=submission.obtained_marks,
                    remarks=submission.teacher_remarks,
                    performed_by=request.user,
                )
                notify(
                    submission.student,
                    'marks_published',
                    f"Graded: {assignment.title}",
                    body=f"Marks: {submission.obtained_marks}/{assignment.total_marks}",
                    link_url=reverse(
                        'staff:assignment_submit', args=(assignment.pk,)
                    ),
                )
            messages.success(request, f"Graded {submission.student.name}.")
        else:
            messages.error(request, "Enter valid marks and grading status.")
        return redirect('staff:teacher_assignment_detail', pk=assignment.pk)


class TeacherHomeworkListView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/teacher_homework_list.html'

    def get(self, request):
        from handle.models import Homework

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        homeworks = Homework.objects.filter(
            org=org,
        ).filter(
            Q(teacher_assignment__in=scopes) | Q(assigned_by=request.user)
        ).select_related(
            'teacher_assignment', 'subject', 'classification', 'section',
        ).order_by('-due_date', '-pk')
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'homeworks': homeworks,
            'active_scope_count': scopes.count(),
        })


class TeacherHomeworkCreateView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/teacher_homework_form.html'

    def get(self, request):
        from handle.forms import TeacherHomeworkForm

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        form = TeacherHomeworkForm(org=org, teacher=request.user)
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'form': form,
            'active_scope_count': scopes.count(),
        })

    def post(self, request):
        from django.db import transaction
        from handle.academics import roster_for_subject
        from handle.forms import TeacherHomeworkForm
        from handle.models import HomeworkAttachment, HomeworkStatus
        from handle.notifications import notify_many

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        form = TeacherHomeworkForm(
            request.POST, org=org, teacher=request.user,
        )
        if form.is_valid():
            with transaction.atomic():
                homework = form.save()
                for uploaded in request.FILES.getlist('attachments'):
                    HomeworkAttachment.objects.create(
                        homework=homework, file=uploaded,
                    )
                scope = homework.teacher_assignment
                students = roster_for_subject(
                    org,
                    homework.subject,
                    homework.classification,
                    homework.section,
                    academic_year=scope.academic_year,
                )
                HomeworkStatus.objects.bulk_create(
                    [
                        HomeworkStatus(homework=homework, student=student)
                        for student in students
                    ],
                    ignore_conflicts=True,
                )
                notify_many(
                    students,
                    'homework_assigned',
                    f"New Homework: {homework.subject.name}",
                    body=f"Due {homework.due_date}",
                    link_url='/staff/homework/',
                )
            messages.success(request, "Homework assigned to the validated roster.")
            return redirect('staff:teacher_homework_detail', pk=homework.pk)
        messages.error(request, "Please correct the homework errors below.")
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'form': form,
            'active_scope_count': scopes.count(),
        })


class TeacherHomeworkDetailView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/teacher_homework_detail.html'

    def _homework(self, request, pk, org, scopes):
        from handle.models import Homework

        return get_object_or_404(
            Homework.objects.filter(org=org).filter(
                Q(teacher_assignment__in=scopes) | Q(assigned_by=request.user)
            ).select_related(
                'teacher_assignment', 'subject', 'classification', 'section',
            ),
            pk=pk,
        )

    def get(self, request, pk):
        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        homework = self._homework(request, pk, org, scopes)
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'homework': homework,
            'statuses': homework.statuses.select_related(
                'student',
            ).order_by('student__name'),
        })

    def post(self, request, pk):
        from handle.models import HomeworkStatus

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        homework = self._homework(request, pk, org, scopes)
        status_obj = get_object_or_404(
            HomeworkStatus,
            pk=request.POST.get('status_id'),
            homework=homework,
            student__org=org,
        )
        if status_obj.status != 'completed':
            messages.error(request, "Only completed homework can be verified.")
        else:
            status_obj.verified_by_teacher = True
            status_obj.verified_at = timezone.now()
            status_obj.save(update_fields=[
                'verified_by_teacher', 'verified_at',
            ])
            messages.success(request, f"Verified {status_obj.student.name}.")
        return redirect('staff:teacher_homework_detail', pk=homework.pk)


class TeacherExamListView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'results'
    template_name = 'staff/academic/teacher_exam_list.html'

    def get(self, request):
        from handle.models import ExamTerm

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        scopes = list(scopes.order_by(
            'classification__name', 'section__name', 'subject__name',
        ))
        exams = list(ExamTerm.objects.filter(
            org=org,
            classification_id__in={scope.classification_id for scope in scopes},
        ).select_related(
            'classification', 'section',
        ).order_by('-start_date', '-pk'))
        for exam in exams:
            exam.teacher_scopes = [
                scope for scope in scopes
                if scope.classification_id == exam.classification_id
                and (
                    not exam.section_id
                    or not scope.section_id
                    or scope.section_id == exam.section_id
                )
            ]
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'exams': exams,
        })


class TeacherExamMarksView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'results'
    template_name = 'staff/academic/teacher_exam_marks.html'

    def _context_objects(self, request, exam_pk, scope_pk):
        from handle.models import ExamTerm

        org, memb, scopes = _teacher_scopes(request)
        if not org:
            return None, None, None, None
        scope = get_object_or_404(scopes, pk=scope_pk)
        exam = get_object_or_404(
            ExamTerm,
            pk=exam_pk,
            org=org,
            classification_id=scope.classification_id,
        )
        if (
            exam.section_id
            and scope.section_id
            and exam.section_id != scope.section_id
        ):
            from django.http import Http404
            raise Http404("Exam section does not match this teaching assignment.")
        return org, memb, exam, scope

    def _roster_and_results(self, org, exam, scope):
        from handle.academics import roster_for_subject
        from handle.models import ResultRecord

        section = exam.section or scope.section
        students = list(roster_for_subject(
            org,
            scope.subject,
            scope.classification,
            section,
            academic_year=scope.academic_year,
        ))
        existing = {
            record.student_id: record
            for record in ResultRecord.objects.filter(
                exam=exam,
                subject=scope.subject,
                student_id__in=[student.pk for student in students],
            )
        }
        return [
            {'student': student, 'result': existing.get(student.pk)}
            for student in students
        ]

    def get(self, request, exam_pk, scope_pk):
        org, memb, exam, scope = self._context_objects(
            request, exam_pk, scope_pk,
        )
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'exam': exam, 'scope': scope,
            'rows': self._roster_and_results(org, exam, scope),
            'can_edit': not exam.is_published and exam.status != 'archived',
        })

    def post(self, request, exam_pk, scope_pk):
        from decimal import Decimal, InvalidOperation
        from django.db import transaction
        from handle.models import ResultRecord

        org, memb, exam, scope = self._context_objects(
            request, exam_pk, scope_pk,
        )
        if not org:
            messages.error(request, "This page is only available to teaching staff.")
            return redirect('staff:dashboard')
        if exam.is_published or exam.status == 'archived':
            messages.error(request, "Published or archived exam marks are read-only.")
            return redirect(
                'staff:teacher_exam_marks',
                exam_pk=exam.pk,
                scope_pk=scope.pk,
            )

        rows = self._roster_and_results(org, exam, scope)
        pending = []
        errors = []
        for row in rows:
            student = row['student']
            raw_marks = request.POST.get(f'marks_{student.pk}', '').strip()
            is_absent = request.POST.get(f'absent_{student.pk}') == 'on'
            remarks = request.POST.get(f'remarks_{student.pk}', '').strip()
            if not raw_marks and not is_absent:
                continue
            try:
                marks = Decimal('0') if is_absent else Decimal(raw_marks)
            except InvalidOperation:
                errors.append(f"{student.name}: enter valid marks.")
                continue
            if marks < 0 or marks > scope.subject.full_marks:
                errors.append(
                    f"{student.name}: marks must be between 0 and "
                    f"{scope.subject.full_marks}."
                )
                continue
            pending.append((student, marks, is_absent, remarks))

        if errors:
            for error in errors[:5]:
                messages.error(request, error)
            return render(request, self.template_name, {
                'org': org, 'memb': memb, 'exam': exam, 'scope': scope,
                'rows': rows, 'can_edit': True,
            })

        with transaction.atomic():
            locked_exam = type(exam).objects.select_for_update().get(pk=exam.pk)
            if locked_exam.is_published or locked_exam.status == 'archived':
                messages.error(request, "This exam became read-only.")
                return redirect(
                    'staff:teacher_exam_marks',
                    exam_pk=exam.pk,
                    scope_pk=scope.pk,
                )
            for student, marks, is_absent, remarks in pending:
                result, created = ResultRecord.objects.update_or_create(
                    student=student,
                    exam=locked_exam,
                    subject=scope.subject,
                    defaults={
                        'obtained_marks': marks,
                        'is_absent': is_absent,
                        'remarks': remarks or ('Absent' if is_absent else None),
                        'updated_by': request.user,
                    },
                )
                if created:
                    result.created_by = request.user
                    result.save(update_fields=['created_by'])
            if pending and locked_exam.status == 'draft':
                locked_exam.status = 'marks_entry'
                locked_exam.save(update_fields=['status'])
        messages.success(request, f"Saved marks for {len(pending)} students.")
        return redirect(
            'staff:teacher_exam_marks',
            exam_pk=exam.pk,
            scope_pk=scope.pk,
        )


# =============================================================
# ACADEMIC MANAGEMENT — student-facing views
# (premium — required_feature = 'academic_management')
# =============================================================

from django.db.models import Q
from handle.models import HomeworkStatus
from handle.forms import AssignmentSubmissionForm


def _student_context(request):
    """Returns (org, member) for the logged-in student, or (None, None)
    if this account isn't a student. Mirrors Dashboard()'s own resolution."""
    if request.user.user_type != '3':
        return None, None
    try:
        org = request.user.staff.org
    except Exception:
        return None, None
    memb = getattr(request.user.staff, 'member', None)
    if not memb or memb.member_type not in ('student', 'trainee'):
        return None, None
    return org, memb


def _student_scope_q(org, memb, *, course_path, classification_path, section_path):
    """Build an exact enrollment scope for student-facing academic queries."""
    from handle.models import StudentCourseEnrollment

    today = timezone.localdate()
    enrollments = StudentCourseEnrollment.objects.filter(
        org=org, student=memb, start_date__lte=today,
    ).exclude(status='cancelled').filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    ).select_related('course', 'classification', 'section', 'academic_year')

    scope = Q(pk__in=[])
    for enrollment in enrollments:
        course_scope = (
            Q(**{f'{course_path}_id': enrollment.course_id})
            | Q(**{f'{course_path}__isnull': True})
        )
        exact = course_scope & Q(**{
            f'{classification_path}_id': enrollment.classification_id,
        })
        section_scope = Q(**{f'{section_path}__isnull': True})
        if enrollment.section_id:
            section_scope |= Q(**{f'{section_path}_id': enrollment.section_id})
        scope |= exact & section_scope

    if not enrollments.exists():
        current_course_ids = memb.courses.filter(org=org).values_list('pk', flat=True)
        course_scope = (
            Q(**{f'{course_path}_id__in': current_course_ids})
            | Q(**{f'{course_path}__isnull': True})
        )
        scope = course_scope & Q(**{
            f'{classification_path}_id': memb.classification_id,
        })
        section_scope = Q(**{f'{section_path}__isnull': True})
        if memb.section_id:
            section_scope |= Q(**{f'{section_path}_id': memb.section_id})
        scope &= section_scope
    return scope, enrollments


class StudentAssignmentListView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/assignment_list.html'

    def get(self, request):
        from handle.models import Assignment, AssignmentSubmission
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')

        scope, enrollments = _student_scope_q(
            org, memb, course_path='course',
            classification_path='classification', section_path='section',
        )
        qs = Assignment.objects.filter(scope, org=org, visibility='published')
        qs = qs.select_related('subject').order_by('-due_date')

        submitted_ids = set(
            AssignmentSubmission.objects.filter(student=memb, assignment__in=qs).values_list('assignment_id', flat=True)
        )
        assignments = list(qs)
        for a in assignments:
            a.is_submitted = a.id in submitted_ids

        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'assignments': assignments,
            'student_enrollments': enrollments,
        })


class AssignmentSubmitView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/assignment_submit.html'

    def get(self, request, pk):
        from handle.models import Assignment, AssignmentSubmission
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')
        scope, _ = _student_scope_q(
            org, memb, course_path='course',
            classification_path='classification', section_path='section',
        )
        assignment = get_object_or_404(
            Assignment.objects.filter(scope, visibility='published'),
            pk=pk,
            org=org,
        )
        submission = AssignmentSubmission.objects.filter(assignment=assignment, student=memb).first()
        form = AssignmentSubmissionForm(instance=submission)
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'assignment': assignment, 'submission': submission, 'form': form,
        })

    def post(self, request, pk):
        from handle.models import (
            Assignment, AssignmentSubmission, AssignmentSubmissionAttachment,
            AssignmentSubmissionHistory,
        )
        from django.utils import timezone as _tz
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')
        scope, _ = _student_scope_q(
            org, memb, course_path='course',
            classification_path='classification', section_path='section',
        )
        assignment = get_object_or_404(
            Assignment.objects.filter(
                scope, visibility='published', status='open',
            ),
            pk=pk,
            org=org,
        )

        submission, created = AssignmentSubmission.objects.get_or_create(
            assignment=assignment,
            student=memb,
        )
        if not created and submission.status == 'graded':
            messages.error(
                request,
                "This assignment is already graded and cannot be resubmitted.",
            )
            return redirect('staff:assignment_submit', pk=assignment.pk)
        form = AssignmentSubmissionForm(request.POST, instance=submission)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.submitted_at = _tz.now()
            submission.status = 'submitted'
            submission.save()
            for f in request.FILES.getlist('attachments'):
                AssignmentSubmissionAttachment.objects.create(submission=submission, file=f)
            AssignmentSubmissionHistory.objects.create(
                submission=submission, action='submitted' if created else 'resubmitted',
                status=submission.status, performed_by=request.user,
            )
            if assignment.assigned_by:
                from handle.notifications import notify
                # Notify the assigning teacher's own member profile, if linked.
                teacher_member = getattr(getattr(assignment.assigned_by, 'staff', None), 'member', None)
                if teacher_member:
                    from django.urls import reverse
                    notify(
                        teacher_member, 'submission_received', f"Submission: {assignment.title}",
                        body=f"{memb.name} submitted",
                        link_url=reverse(
                            'staff:teacher_assignment_detail',
                            args=(assignment.pk,),
                        ),
                    )
            messages.success(request, "Assignment submitted.")
            return redirect('staff:student_assignments')
        messages.error(request, "Please correct the errors below.")
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'assignment': assignment, 'submission': submission, 'form': form,
        })


class StudentHomeworkListView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/homework_list.html'

    def get(self, request):
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')
        statuses = HomeworkStatus.objects.filter(student=memb, homework__org=org).select_related('homework__subject').order_by('-homework__due_date')
        return render(request, self.template_name, {'org': org, 'memb': memb, 'statuses': statuses})


@login_required(login_url='/login/')
@feature_required('academic_management')
def mark_homework_status(request, pk):
    org, memb = _student_context(request)
    if not memb:
        messages.error(request, "This page is only available to students.")
        return redirect('staff:dashboard')
    status_obj = get_object_or_404(HomeworkStatus, pk=pk, student=memb, homework__org=org)
    from django.utils import timezone as _tz
    if status_obj.verified_by_teacher:
        messages.error(request, "Verified homework cannot be changed.")
        return redirect('staff:student_homework')
    if status_obj.status == 'pending':
        status_obj.status = 'completed'
        status_obj.completed_at = _tz.now()
    else:
        status_obj.status = 'pending'
        status_obj.completed_at = None
        status_obj.verified_by_teacher = False
        status_obj.verified_at = None
    status_obj.save()
    messages.success(request, "Homework status updated.")
    return redirect('staff:student_homework')


class StudentCourseMaterialListView(LoginRequiredMixin, FeatureRequiredMixin, View):
    required_feature = 'academic_management'
    template_name = 'staff/academic/course_material_list.html'

    def get(self, request):
        from handle.models import CourseMaterial
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')
        scope, enrollments = _student_scope_q(
            org, memb, course_path='subject__course',
            classification_path='subject__classification', section_path='subject__section',
        )
        materials = CourseMaterial.objects.filter(
            scope, org=org, is_active=True,
        ).select_related('subject__course').order_by('-created_at')
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'materials': materials,
            'student_enrollments': enrollments,
        })


@login_required(login_url='/login/')
@feature_required('academic_management')
def track_material_access(request, pk):
    """Called via a small bit of JS when a student opens/downloads a material."""
    from handle.models import CourseMaterial, CourseMaterialAccess
    org, memb = _student_context(request)
    if not memb:
        return JsonResponse({'error': 'not a student'}, status=403)
    scope, _ = _student_scope_q(
        org, memb, course_path='subject__course',
        classification_path='subject__classification', section_path='subject__section',
    )
    material = get_object_or_404(CourseMaterial.objects.filter(scope), pk=pk, org=org)
    access_type = request.GET.get('type', 'view')
    if access_type not in ('view', 'download'):
        access_type = 'view'
    CourseMaterialAccess.objects.create(material=material, student=memb, access_type=access_type)
    return JsonResponse({'status': 'ok'})


class StudentTeachingLogView(LoginRequiredMixin, FeatureRequiredMixin, View):
    """Read-only — only approved logs for the student's own classification/section."""
    required_feature = 'academic_management'
    template_name = 'staff/academic/teaching_logs.html'

    def get(self, request):
        from handle.models import TeachingLog
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')
        scope, enrollments = _student_scope_q(
            org, memb, course_path='course',
            classification_path='classification', section_path='section',
        )
        qs = TeachingLog.objects.filter(scope, org=org, status='approved')
        logs = qs.select_related('teacher', 'subject__course').order_by('-date')[:30]
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'logs': logs,
            'student_enrollments': enrollments,
        })


class StudentSubjectAttendanceView(LoginRequiredMixin, FeatureRequiredMixin, View):
    """Read-only per-subject attendance for the logged-in student only."""
    required_feature = 'academic_management'
    template_name = 'staff/academic/subject_attendance.html'

    def get(self, request):
        from handle.models import Course, Subject, SubjectAttendanceRecord

        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')

        today = timezone.localdate()
        month_start = today.replace(day=1)

        def parse_date(value, default):
            try:
                return datetime.datetime.strptime(value, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                return default

        date_from = parse_date(request.GET.get('date_from'), month_start)
        date_to = parse_date(request.GET.get('date_to'), today)
        if date_from > date_to:
            date_from, date_to = date_to, date_from

        records = SubjectAttendanceRecord.objects.filter(
            org=org,
            member=memb,
            teaching_log__date__gte=date_from,
            teaching_log__date__lte=date_to,
        ).select_related(
            'teaching_log__academic_year', 'teaching_log__course',
            'teaching_log__subject', 'teaching_log__classification',
            'teaching_log__section', 'teaching_log__teacher',
        )
        course_id = request.GET.get('course', '')
        subject_id = request.GET.get('subject', '')
        attendance_status = request.GET.get('status', '')
        if course_id:
            records = records.filter(teaching_log__course_id=course_id)
        if subject_id:
            records = records.filter(teaching_log__subject_id=subject_id)
        if attendance_status in dict(SubjectAttendanceRecord.STATUS_CHOICES):
            records = records.filter(status=attendance_status)
        records = records.order_by('-teaching_log__date', '-teaching_log__period')

        counts = {
            row['status']: row['total']
            for row in records.values('status').annotate(total=Count('pk'))
        }
        total = sum(counts.values())
        present_like = counts.get('present', 0) + counts.get('late', 0)
        percentage = round(present_like / total * 100, 1) if total else 0
        course_ids = set(
            records.values_list('teaching_log__course_id', flat=True)
        )
        course_ids.update(memb.courses.filter(org=org).values_list('pk', flat=True))

        return render(request, self.template_name, {
            'org': org,
            'memb': memb,
            'records': records,
            'counts': counts,
            'total': total,
            'percentage': percentage,
            'date_from': date_from,
            'date_to': date_to,
            'courses': Course.objects.filter(org=org, pk__in=course_ids).order_by('name'),
            'subjects': Subject.objects.filter(
                org=org, teaching_logs__attendance_records__member=memb,
            ).distinct().order_by('name'),
            'status_choices': SubjectAttendanceRecord.STATUS_CHOICES,
            'selected_course': course_id,
            'selected_subject': subject_id,
            'selected_status': attendance_status,
        })


class StudentRoutineView(LoginRequiredMixin, FeatureRequiredMixin, View):
    """A student's own weekly timetable, read-only."""
    required_feature = 'academic_management'
    template_name = 'staff/academic/routine.html'

    def get(self, request):
        from handle.models import RoutinePeriod
        org, memb = _student_context(request)
        if not memb:
            messages.error(request, "This page is only available to students.")
            return redirect('staff:dashboard')
        scope, enrollments = _student_scope_q(
            org, memb, course_path='subject__course',
            classification_path='classification', section_path='section',
        )
        qs = RoutinePeriod.objects.filter(
            scope, org=org, is_active=True,
        ).select_related(
            'subject__course', 'teacher', 'classification', 'section',
        )
        from handle.academics import student_routine_reminders
        routine_data = student_routine_reminders(qs)
        days = list(RoutinePeriod.DAY_CHOICES)
        grid = {
            day[0]: [
                period for period in routine_data['periods']
                if period.day_of_week == day[0]
            ]
            for day in days
        }
        return render(request, self.template_name, {
            'org': org, 'memb': memb, 'days': days, 'grid': grid,
            'student_enrollments': enrollments,
            'current_day': routine_data['current_day'],
            'routine_reminder': routine_data['attention'],
            'active_routine': routine_data['active'],
            'next_routine': routine_data['next_period'],
        })


class NotificationListView(LoginRequiredMixin, View):
    """Compatibility redirect to the shared premium notification centre."""

    def get(self, request):
        return redirect('handle:notifications')


@login_required(login_url='/login/')
def mark_notification_read(request, pk):
    from handle.notifications import mark_read, notifications_for_user
    org = getattr(getattr(request.user, 'staff', None), 'org', None)
    notification = get_object_or_404(
        notifications_for_user(request.user, org), pk=pk,
    )
    mark_read(notification)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok'})
    return redirect('handle:notifications')
