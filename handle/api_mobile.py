import math

from django.forms import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from management.models import *
from .serializers import (
    AttendanceReportSerializer,
    AttendingClassificationSerializer,
    BranchSerializer,
    ClassificationSerializer,
    CourseAttendanceSerializer,
    CourseSerializer,
    BirthdayMemberSerializer,
    FinancialTransactionSerializer,
    LeaveHistorySerializer,
    LeaveTypeSerializer,
    LocationBasedSerializer,
    OrgSerializer,
    PaySlipSerializer,
    PayrollAdjustmentSerializer,
    PayrollPolicySerializer,
    ProbationReviewSerializer,
    ProvidentFundRecordSerializer,
    SectionSerializer,
    SocialSecurityFundRecordSerializer,
    StockCategorySerializer,
    StockItemSerializer,
    StockMovementSerializer,
    TransactionCategorySerializer,
    UserLoginSerializer, 
    UserRegistrationSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer
)


from rest_framework.generics import (
    ListCreateAPIView, 
    RetrieveUpdateDestroyAPIView,
    ListAPIView
)
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    AttendanceRecord,
    AttendingClassification,
    Branch,
    Classification,
    Course,
    CourseAttendance,
    FinancialTransaction,
    PaySlip,
    PayrollAdjustment,
    PayrollPolicy,
    ProbationReview,
    ProvidentFundRecord,
    Section,
    SocialSecurityFundRecord,
    StockCategory,
    StockItem,
    StockMovement,
    TransactionCategory,
    member,
)
from .serializers import MemberDetailSerializer, MemberCreateSerializer
from datetime import datetime, timedelta
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.forms import PasswordResetForm


def get_request_org_id(request):
    try:
        if hasattr(request.user, 'schooladmin') and request.user.schooladmin:
            return request.user.schooladmin.org.id
        if hasattr(request.user, 'staff') and request.user.staff:
            return request.user.staff.org.id
    except (AttributeError, ObjectDoesNotExist):
        return None
    return None


# Add this underneath your existing api_apply_leave view

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_leaves(request):
    try:
        if hasattr(request.user, 'staff') and request.user.staff:
            memb = request.user.staff.member
        else:
            return Response({"error": "Only staff members can view their leaves."}, status=status.HTTP_403_FORBIDDEN)

        # Fetch all leave reports for this specific member, newest first
        leaves = LeaveReport.objects.filter(member=memb).order_by('-gap_start')
        serializer = LeaveHistorySerializer(leaves, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        

# 1. API to get the Leave Types for the Dropdown
@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_leave_types(request):
    try:
        # Safely get the organization
        if hasattr(request.user, 'schooladmin') and request.user.schooladmin:
            org = request.user.schooladmin.org
        elif hasattr(request.user, 'staff') and request.user.staff:
            org = request.user.staff.org
        else:
            return Response({"error": "No valid profile found."}, status=status.HTTP_404_NOT_FOUND)

        leave_types = LeaveType.objects.filter(org=org)
        serializer = LeaveTypeSerializer(leave_types, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        # Catch any unexpected crashes and return them as JSON
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# 2. API to submit the Leave Application
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_apply_leave(request):
    try:
        # Safely get the organization and member
        if hasattr(request.user, 'staff') and request.user.staff:
            org = request.user.staff.org
            memb = request.user.staff.member
        else:
            return Response({"error": "Only staff members can apply for leave."}, status=status.HTTP_403_FORBIDDEN)
        
        leave_type_id = request.data.get('leave_type_id')
        gap_start = request.data.get('gap_start')
        gap_end = request.data.get('gap_end')
        reason = request.data.get('reason')
        
        if not all([leave_type_id, gap_start, gap_end, reason]):
            return Response({"error": "All fields are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        leave_type = LeaveType.objects.get(id=leave_type_id, org=org)
        
        LeaveReport.objects.create(
            member=memb,
            org=org,
            leave_type=leave_type,
            gap_start=gap_start,
            gap_end=gap_end,
            reason=reason,
            approved=False,
            rejected=False,
            seen=False
        )
        
        return Response({"message": "Leave application submitted successfully!"}, status=status.HTTP_201_CREATED)
        
    except LeaveType.DoesNotExist:
        return Response({"error": "Invalid Leave Type selected."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    


class AttendanceReportAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        member_id = request.query_params.get('member_id')
        
        if not start_date or not end_date:
            return Response(
                {'error': 'Both start_date and end_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        members = member.objects.filter(org_id=org_id)
        if member_id:
            members = members.filter(id=member_id)
            
        report_data = []
        
        for member_obj in members:
            current_date = start_date
            while current_date <= end_date:
                records = AttendanceRecord.objects.filter(
                    mem=member_obj,
                    scanned_time__date=current_date
                ).order_by('scanned_time')
                
                first_checkin = records.first().scanned_time if records.exists() else None
                last_checkout = records.last().scanned_time if records.count() > 1 else None
                
                total_hours = None
                if first_checkin and last_checkout:
                    total_hours = last_checkout - first_checkin
                
                # status = 'Present' if records.exists() else 'Absent'
                
                report_data.append({
                    'member_id': member_obj.id,
                    'member_name': member_obj.name,
                    'date': current_date,
                    'first_checkin': first_checkin,
                    'last_checkout': last_checkout,
                    'total_hours': total_hours,
                    # 'status': status
                })
                
                current_date += timedelta(days=1)
                
        serializer = AttendanceReportSerializer(report_data, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_wifi_checkin(request):
    try:
        # Securely get the logged-in staff member
        if hasattr(request.user, 'staff') and request.user.staff:
            memb = request.user.staff.member
            org = request.user.staff.org
        else:
            return Response({"error": "Only staff members can use WiFi check-in."}, status=status.HTTP_403_FORBIDDEN)

        # Get WiFi details from Flutter
        ssid = request.data.get('ssid')
        bssid = request.data.get('bssid')

        if not ssid:
            return Response({"error": "Could not detect WiFi network. Ensure location permissions are granted."}, status=status.HTTP_400_BAD_REQUEST)

        # ⚠️ CRITICAL: Mobile OSs often wrap the SSID in quotes (e.g., '"Office_WiFi"'). 
        # We must strip them to match your database cleanly.
        clean_ssid = ssid.strip('"')

        # Check if this WiFi is registered for this organization
        # Note: We check by SSID (Name). BSSID (MAC Address) can sometimes change based on 2.4Ghz vs 5Ghz bands, so SSID is safer to check!
        valid_wifi = WifiBased.objects.filter(
            org=org,
            ssid__iexact=clean_ssid
        ).exists()

        if not valid_wifi:
            return Response(
                {"error": f"Network '{clean_ssid}' is not an authorized office WiFi."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Ensure they haven't already marked attendance today
        today = timezone.localtime().date()
        already_marked = AttendanceRecord.objects.filter(
            mem=memb,
            org=org,
            scanned_time__date=today
        ).exists()
        
       
        
        # Mark Present!
        AttendanceRecord.objects.create(
            mem=memb,
            org=org,
            scanned_time=timezone.now()
        )
        if already_marked:
            return Response(
                {"status": "already_marked", "message": "WiFi Check-Out successful!"},
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"status": "success", "message": "WiFi Check-in successful!"},
                status=status.HTTP_201_CREATED
            )
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_payslips(request):
    try:
        # Safely determine the logged-in staff member
        if hasattr(request.user, 'staff') and request.user.staff:
            memb = request.user.staff.member
        else:
            return Response(
                {"error": "Only staff members can view payslips."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Fetch payslips for this specific member, newest first
        # We order by 'id' descending as a fallback, or by 'from_date' if you prefer
        payslips = PaySlip.objects.filter(member=memb).order_by('-id')
        
        serializer = PaySlipSerializer(payslips, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        # Catch unexpected errors and send them to Flutter safely
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



class OrgListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrgSerializer
    
    def get_queryset(self):
        # 1. Safely determine the organization ID without crashing
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                return Organization.objects.none()
        except ObjectDoesNotExist:
            return Organization.objects.none()
            
        # 2. Filter by 'id' (the primary key), not 'org_id'
        return Organization.objects.filter(id=org_id)
        
    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                return
            serializer.save(id=org_id)
        except ObjectDoesNotExist:
            pass


class OrgDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrgSerializer
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                return Organization.objects.none()
        except ObjectDoesNotExist:
            return Organization.objects.none()
            
        return Organization.objects.filter(id=org_id)





class BranchListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'code', 'phone', 'email']
    ordering_fields = ['name', 'code', 'status']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Branch.objects.filter(org_id=org_id) if org_id else Branch.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request))


class BranchDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Branch.objects.filter(org_id=org_id) if org_id else Branch.objects.none()


class SectionListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectionSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'classification', 'status']
    search_fields = ['name', 'code', 'classification__name', 'branch__name']
    ordering_fields = ['name', 'code', 'status']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Section.objects.filter(org_id=org_id).select_related('branch', 'classification') if org_id else Section.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request))


class SectionDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SectionSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Section.objects.filter(org_id=org_id).select_related('branch', 'classification') if org_id else Section.objects.none()


class StockCategoryListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StockCategorySerializer
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return StockCategory.objects.filter(org_id=org_id) if org_id else StockCategory.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request))


class StockCategoryDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StockCategorySerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return StockCategory.objects.filter(org_id=org_id) if org_id else StockCategory.objects.none()


class StockItemListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StockItemSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'category', 'status']
    search_fields = ['name', 'sku', 'supplier']
    ordering_fields = ['name', 'quantity', 'purchase_date']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return StockItem.objects.filter(org_id=org_id).select_related('branch', 'category') if org_id else StockItem.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request))


class StockItemDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StockItemSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return StockItem.objects.filter(org_id=org_id).select_related('branch', 'category') if org_id else StockItem.objects.none()


class StockMovementListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StockMovementSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'item', 'movement_type', 'movement_date']
    search_fields = ['item__name', 'note']
    ordering_fields = ['movement_date', 'quantity']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return StockMovement.objects.filter(org_id=org_id).select_related('branch', 'item', 'created_by') if org_id else StockMovement.objects.none()

    def perform_create(self, serializer):
        item = serializer.validated_data.get('item')
        serializer.save(
            org_id=get_request_org_id(self.request),
            branch=serializer.validated_data.get('branch') or item.branch,
            created_by=self.request.user,
        )


class StockMovementDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return StockMovement.objects.filter(org_id=org_id).select_related('branch', 'item', 'created_by') if org_id else StockMovement.objects.none()


class TransactionCategoryListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionCategorySerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['transaction_type']
    search_fields = ['name']
    ordering_fields = ['name', 'transaction_type']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return TransactionCategory.objects.filter(org_id=org_id) if org_id else TransactionCategory.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request))


class TransactionCategoryDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionCategorySerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return TransactionCategory.objects.filter(org_id=org_id) if org_id else TransactionCategory.objects.none()


class FinancialTransactionListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FinancialTransactionSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'category', 'transaction_type', 'payment_method', 'transaction_date']
    search_fields = ['title', 'reference_number', 'note']
    ordering_fields = ['transaction_date', 'amount']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return FinancialTransaction.objects.filter(org_id=org_id).select_related('branch', 'category', 'created_by') if org_id else FinancialTransaction.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request), created_by=self.request.user)


class FinancialTransactionDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FinancialTransactionSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return FinancialTransaction.objects.filter(org_id=org_id).select_related('branch', 'category', 'created_by') if org_id else FinancialTransaction.objects.none()


class BirthdayReportAPIView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BirthdayMemberSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        if not org_id:
            return member.objects.none()

        queryset = member.objects.filter(org_id=org_id, date_of_birth__isnull=False).select_related('branch', 'classification', 'section')
        branch = self.request.query_params.get('branch')
        if branch:
            queryset = queryset.filter(branch_id=branch)

        scope = self.request.query_params.get('scope', 'upcoming')
        today = timezone.localdate()
        if scope == 'today':
            return queryset.filter(date_of_birth__month=today.month, date_of_birth__day=today.day)
        return sorted(
            queryset,
            key=lambda item: self.next_birthday_date(item.date_of_birth, today)
        )

    def next_birthday_date(self, birthday, today):
        try:
            candidate = birthday.replace(year=today.year)
        except ValueError:
            candidate = birthday.replace(year=today.year, day=28)
        if candidate < today:
            try:
                candidate = birthday.replace(year=today.year + 1)
            except ValueError:
                candidate = birthday.replace(year=today.year + 1, day=28)
        return candidate


class PayrollPolicyListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayrollPolicySerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        if not org_id:
            return PayrollPolicy.objects.none()
        PayrollPolicy.objects.get_or_create(org_id=org_id)
        return PayrollPolicy.objects.filter(org_id=org_id)

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request))


class PayrollPolicyDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayrollPolicySerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return PayrollPolicy.objects.filter(org_id=org_id) if org_id else PayrollPolicy.objects.none()


class PayrollAdjustmentListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayrollAdjustmentSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['member', 'adjustment_type', 'status', 'effective_date']
    search_fields = ['member__name', 'title', 'notes']
    ordering_fields = ['effective_date', 'amount']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return PayrollAdjustment.objects.filter(org_id=org_id).select_related('member', 'created_by') if org_id else PayrollAdjustment.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request), created_by=self.request.user)


class PayrollAdjustmentDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayrollAdjustmentSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return PayrollAdjustment.objects.filter(org_id=org_id).select_related('member', 'created_by') if org_id else PayrollAdjustment.objects.none()


class ProbationReviewListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProbationReviewSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['member', 'status', 'review_date']
    search_fields = ['member__name', 'notes']
    ordering_fields = ['review_date']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return ProbationReview.objects.filter(org_id=org_id).select_related('member', 'reviewer') if org_id else ProbationReview.objects.none()

    def perform_create(self, serializer):
        serializer.save(org_id=get_request_org_id(self.request), reviewer=self.request.user)


class ProbationReviewDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProbationReviewSerializer

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return ProbationReview.objects.filter(org_id=org_id).select_related('member', 'reviewer') if org_id else ProbationReview.objects.none()


class ProvidentFundRecordListAPIView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProvidentFundRecordSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['member', 'month_name']
    search_fields = ['member__name', 'month_name']
    ordering_fields = ['recorded_on']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return ProvidentFundRecord.objects.filter(org_id=org_id).select_related('member', 'payslip') if org_id else ProvidentFundRecord.objects.none()


class SocialSecurityFundRecordListAPIView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SocialSecurityFundRecordSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['member', 'month_name']
    search_fields = ['member__name', 'month_name']
    ordering_fields = ['recorded_on']

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return SocialSecurityFundRecord.objects.filter(org_id=org_id).select_related('member', 'payslip') if org_id else SocialSecurityFundRecord.objects.none()


class CourseListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'classifications', 'sections', 'teacher', 'status']
    search_fields = ['name', 'code', 'description']
    ordering_fields = ['name', 'code', 'status']
    
    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        if not org_id:
            return Course.objects.none()
        return Course.objects.filter(org_id=org_id).select_related('branch', 'teacher').prefetch_related('classifications', 'sections')
        
    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        serializer.save(org_id=org_id)

class CourseDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseSerializer
    
    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Course.objects.filter(org_id=org_id).select_related('branch', 'teacher').prefetch_related('classifications', 'sections') if org_id else Course.objects.none()


class CourseAttendanceListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseAttendanceSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'classification', 'section', 'course', 'staff', 'attendance_date']
    search_fields = ['course__name', 'classification__name', 'section__name', 'topic_taught']
    ordering_fields = ['attendance_date']
    

    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        if not org_id:
            return CourseAttendance.objects.none()
        queryset = CourseAttendance.objects.filter(org_id=org_id).select_related('staff', 'course', 'branch', 'classification', 'section')
        if hasattr(self.request.user, 'staff') and self.request.user.staff:
            queryset = queryset.filter(staff=self.request.user)
        return queryset
        

    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        serializer.save(org_id=org_id)

class CourseAttendanceDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CourseAttendanceSerializer
    
    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return CourseAttendance.objects.filter(org_id=org_id).select_related('staff', 'course', 'branch', 'classification', 'section') if org_id else CourseAttendance.objects.none()




class AttendingClassificationListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AttendingClassificationSerializer
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                staff_id = self.request.user
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                staff_id = self.request.user
            else:
                staff_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            staff_id = None

        print("All Classification attendance")
        print(AttendingClassification.objects.filter(staff=staff_id))
        return AttendingClassification.objects.filter(staff = staff_id)
        
    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        serializer.save(org_id=org_id)

class AttendingClassificationDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AttendingClassificationSerializer
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        return AttendingClassification.objects.filter(org_id=org_id)


class LocationBasedListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LocationBasedSerializer
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        return LocationBased.objects.filter(org_id=org_id)
        
    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        serializer.save(org_id=org_id)

class LocationBasedDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LocationBasedSerializer
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        return LocationBased.objects.filter(org_id=org_id)




def calculate_distance_in_meters(lat1, lon1, lat2, lon2):
    R = 6371000  # Radius of Earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi_1) * math.cos(phi_2) * \
        math.sin(delta_lambda / 2.0) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_location_checkin(request):
    try:
        # 1. SECURELY IDENTIFY THE USER (No member_id needed from Flutter!)
        if hasattr(request.user, 'staff') and request.user.staff:
            memb = request.user.staff.member
            org = request.user.staff.org
        else:
            return Response(
                {"error": "Only staff members can use GPS check-in."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Get only the GPS coordinates from Flutter
        lat = request.data.get('latitude')
        lon = request.data.get('longitude')

        if lat is None or lon is None:
            return Response(
                {"error": "Latitude and longitude are required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        user_lat = float(lat)
        user_lon = float(lon)

        # 3. Get all allowed office locations for this organization
        allowed_locations = LocationBased.objects.filter(org=org)
        
        if not allowed_locations.exists():
            return Response(
                {"error": "No office locations have been set up by the admin."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        # 4. Check if the user is inside ANY of the allowed locations
        is_within_range = False
        matched_location = None

        for loc in allowed_locations:
            distance = calculate_distance_in_meters(
                user_lat, user_lon, 
                float(loc.latitude), float(loc.longitude)
            )
            
            # Checks if distance is within the allowed radius (in meters)
            if distance <= float(loc.radius):
                is_within_range = True
                matched_location = loc
                break

        if not is_within_range:
            return Response(
                {"error": "You are not within the allowed radius of any office location."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 5. Check for duplicate check-ins today
        today = timezone.localtime().date()
        already_marked = AttendanceRecord.objects.filter(
            mem=memb,
            org=org,
            scanned_time__date=today
        ).exists()
        
        
        
        # 6. Mark Present!
        AttendanceRecord.objects.create(
            mem=memb,
            org=org,
            scanned_time=timezone.now()
        )
        if already_marked:
            return Response(
                {"status": "success", "message": f"Successfully checked out from {matched_location.name}!"},
                status=status.HTTP_200_OK
            )
        else:
        
            return Response(
                {"status": "success", "message": f"Successfully checked in at {matched_location.name}!"},
                status=status.HTTP_201_CREATED
            )

    except ValueError:
        return Response({"error": "Invalid GPS coordinates received."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_undo_attendance(request):
    try:
        # 1. Securely verify the user is a staff member
        if hasattr(request.user, 'staff') and request.user.staff:
            staff_org = request.user.staff.org
        else:
            return Response(
                {"error": "Only staff members can manage attendance."}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Get the member_id sent from the Flutter app
        member_id = request.data.get('member_id')
        
        if not member_id:
            return Response(
                {"error": "Member ID is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Get Today's Date in the local timezone
        today = timezone.localtime().date()

        # 4. Find the attendance records for THIS member, in THIS organization, for TODAY.
        # (Filtering by staff_org ensures a staff member can't hack the API to delete attendance for a different school/company)
        records_to_delete = AttendanceRecord.objects.filter(
            mem_id=member_id,
            org=staff_org,
            scanned_time__date=today
        )

        # 5. Delete it if it exists
        if records_to_delete.exists():
            records_to_delete.delete()
            return Response(
                {"message": "Attendance successfully undone."}, 
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {"error": "No attendance record found for this member today."}, 
                status=status.HTTP_404_NOT_FOUND
            )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_attendance_report(request):
    try:
        if hasattr(request.user, 'staff') and request.user.staff:
            memb = request.user.staff.member
        else:
            return Response({"error": "Only staff members can view reports."}, status=status.HTTP_403_FORBIDDEN)

        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')

        if not start_date_str:
            start_date_str = timezone.localtime().date().isoformat()
        if not end_date_str:
            end_date_str = start_date_str

        # Parse the dates
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # 1. Fetch ALL records for this date range, ordered from oldest to newest time
        records = AttendanceRecord.objects.filter(
            mem=memb,
            scanned_time__date__gte=start_date,
            scanned_time__date__lte=end_date
        ).order_by('scanned_time')

        # 2. Group records by Date
        grouped_data = {}
        for rec in records:
            local_t = timezone.localtime(rec.scanned_time)
            date_str = local_t.strftime("%Y-%m-%d")
            
            if date_str not in grouped_data:
                grouped_data[date_str] = []
            
            grouped_data[date_str].append(local_t)

        # 3. Process the grouped data (Merge In and Out times)
        final_data = []
        for date_str, times in grouped_data.items():
            # First scan of the day is Check-In
            check_in_time = times[0]
            
            # If there is more than 1 scan, the last scan is Check-Out
            check_out_time = times[-1] if len(times) > 1 else None

            total_hours = None
            if check_out_time:
                # Calculate time difference
                diff = check_out_time - check_in_time
                hours = diff.total_seconds() / 3600
                total_hours = f"{hours:.2f}" # Format to 2 decimal places (e.g., 8.50)

            # Determine Status (You can adjust this logic based on your office hours!)
            status_text = "On Time"
            # Example: If checked in after 10:15 AM, mark as Late
            if check_in_time.hour >= 10 and check_in_time.minute > 15:
                status_text = "Late In"

            final_data.append({
                "id": int(check_in_time.timestamp()), # Create a unique ID for Flutter
                "date": date_str,
                "check_in": check_in_time.strftime("%I:%M %p"),
                "check_out": check_out_time.strftime("%I:%M %p") if check_out_time else None,
                "total_hours": total_hours,
                "status": status_text
            })

        # 4. Sort the final list so the newest dates show at the top of the app
        final_data.sort(key=lambda x: x['date'], reverse=True)

        return Response(final_data, status=status.HTTP_200_OK)

    except ValueError:
        return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ClassificationListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClassificationSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'status']
    search_fields = ['name', 'branch__name']
    ordering_fields = ['name', 'status']
    
    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Classification.objects.filter(org_id=org_id).select_related('branch') if org_id else Classification.objects.none()
        
    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        serializer.save(org_id=org_id)


class ClassificationDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClassificationSerializer
    
    def get_queryset(self):
        org_id = get_request_org_id(self.request)
        return Classification.objects.filter(org_id=org_id).select_related('branch') if org_id else Classification.objects.none()


class MemberListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['branch', 'classification', 'section', 'courses', 'member_type', 'status', 'black_list', 'gender']
    search_fields = ['name', 'email', 'phone', 'card']
    ordering_fields = ['name', 'created_date']
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        return member.objects.filter(org_id=org_id).select_related('branch', 'classification', 'section').prefetch_related('courses')
        
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MemberCreateSerializer
        return MemberDetailSerializer
        
    def perform_create(self, serializer):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        serializer.save(org_id=org_id)


class MemberDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MemberDetailSerializer
    
    def get_queryset(self):
        try:
            if hasattr(self.request.user, 'schooladmin') and self.request.user.schooladmin:
                org_id = self.request.user.schooladmin.org.id
            elif hasattr(self.request.user, 'staff') and self.request.user.staff:
                org_id = self.request.user.staff.org.id
            else:
                org_id = None  # or raise an error/log it based on your need
        except (AttributeError, ObjectDoesNotExist):
            org_id = None
        return member.objects.filter(org_id=org_id).select_related('branch', 'classification', 'section').prefetch_related('courses')


class LoginAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)
    

class RegisterAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'message': 'User registered successfully',
                'user_id': user.id
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'error': 'Wrong password'}, status=status.HTTP_400_BAD_REQUEST)
                
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'message': 'Password updated successfully'}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from django.template.loader import render_to_string

class PasswordResetRequestAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            # Strip invisible whitespace added by phone autocomplete
            email = serializer.validated_data['email'].strip()
            
            try:
                # Ignore case-sensitivity (Capital 'B' vs lowercase 'b')
                user = CustomUser.objects.get(email__iexact=email)
                
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Setup the exact reset link 
                reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
                
                # 1. Build the context exactly like your standard Django view
                context = {
                    "email": user.email,
                    'domain': 'meroattendance.com',
                    'site_name': 'Mero Attendance',
                    "uid": uid,
                    "user": user,
                    'token': token,
                    'protocol': 'https',
                    'reset_link': reset_link, # Passed in case your HTML template wants to use it directly
                }
                
                # 2. Render the HTML template
                html_email = render_to_string("password/password_reset_email.html", context)
                
                # 3. Create the plain-text fallback
                text_fallback = f"Please click this link to reset your password: {reset_link}"
                
                # 4. Send the email with BOTH text and HTML
                send_mail(
                    subject='Password Reset Requested',
                    message=text_fallback,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[user.email],
                    fail_silently=False,
                    html_message=html_email  # <-- This tells Gmail/Apple Mail to show the pretty version!
                )
                
            except CustomUser.DoesNotExist:
                # TEMPORARY DEBUG: Shows exactly what the Flutter app sent if it fails
                return Response(
                    {"error": f"DEBUG: The exact email sent from phone was [{email}]"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            return Response({'message': 'Password reset link sent to email'}, 
                           status=status.HTTP_200_OK)
                           
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            try:
                # FIX: Decode the 'uid', not the 'token'
                uid = force_str(urlsafe_base64_decode(serializer.validated_data['uid']))
                user = CustomUser.objects.get(pk=uid)
            except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
                user = None
                
            if user is not None and default_token_generator.check_token(user, serializer.validated_data['token']):
                user.set_password(serializer.validated_data['new_password'])
                user.save()
                return Response({'message': 'Password reset successfully'}, 
                              status=status.HTTP_200_OK)
            return Response({'error': 'Invalid token or user ID'}, 
                           status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# For Straff Dashboard API

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist
import datetime
from .models import AttendingClassification, Classification, member, AttendanceRecord, Organization

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_staff_classes(request):
    try:
        # Get classifications assigned to this staff user
        staff_classes = AttendingClassification.objects.filter(staff=request.user)
        
        # Format for Flutter
        classes_data = [
            {"id": sc.classification.id, "name": sc.classification.name} 
            for sc in staff_classes
        ]
        
        # Get organization info safely
        org = request.user.staff.org
        
        return Response({
            "org_id": org.id,
            "org_name": org.name,
            "classes": classes_data
        }, status=status.HTTP_200_OK)
        
    except ObjectDoesNotExist:
        return Response({"error": "Staff profile not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_class_members(request, class_id):
    try:
        clas = Classification.objects.get(id=class_id)
        org = request.user.staff.org
        
        # Get all members in this classification and organization
        members = member.objects.filter(classification=clas, org=org)
        
        # Get today's attendance for these members
        today = datetime.datetime.today().date()
        attended_member_ids = AttendanceRecord.objects.filter(
            mem__in=members, 
            org=org,
            scanned_time__date=today
        ).values_list('mem_id', flat=True)
        
        attended_set = set(attended_member_ids)
        
        # Format data for Flutter
        members_data = []
        for m in members:
            members_data.append({
                "id": m.id,
                "name": m.name,
                "phone": m.phone,
                "is_present": m.id in attended_set
            })
            
        return Response({
            "class_name": clas.name,
            "date": today.strftime("%Y-%m-%d"),
            "members": members_data
        }, status=status.HTTP_200_OK)
        
    except Classification.DoesNotExist:
        return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_mark_present(request):
    member_id = request.data.get('member_id')
    organization_id = request.data.get('organization_id')
    
    if not member_id or not organization_id:
        return Response({"error": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)
        
    try:
        memb = member.objects.get(id=member_id)
        org = Organization.objects.get(id=organization_id)
        
        # Create the attendance record
        AttendanceRecord.objects.create(
            mem=memb,
            org=org,
            scanned_time=datetime.datetime.now()
        )
        
        return Response({"status": "success", "message": f"{memb.name} marked present."}, status=status.HTTP_201_CREATED)
        
    except (member.DoesNotExist, Organization.DoesNotExist):
        return Response({"error": "Member or Organization not found."}, status=status.HTTP_404_NOT_FOUND)




@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_my_profile(request):
    try:
        user = request.user
        # Safely get the member profile
        if hasattr(user, 'staff') and user.staff:
            member = user.staff.member
        else:
            return Response({"error": "Only staff members can access this profile."}, status=status.HTTP_403_FORBIDDEN)

        if request.method == 'GET':
            # Send current data to Flutter
            # Adjust these fields if your Member model has different names!
            return Response({
                "name": member.name,
                "email": user.email,
                "phone": getattr(member, 'phone', ''), # Uses getattr safely in case field doesn't exist
                "address": getattr(member, 'address', '')
            }, status=status.HTTP_200_OK)

        elif request.method == 'PUT':
            # Update the data
            data = request.data
            
            # Update Member fields
            if 'name' in data:
                member.name = data['name']
            if 'phone' in data and hasattr(member, 'phone'):
                member.phone = data['phone']
            if 'address' in data and hasattr(member, 'address'):
                member.address = data['address']
            member.save()

            # Update Django User email if provided
            if 'email' in data:
                user.email = data['email']
                user.save()

            return Response({"message": "Profile updated successfully!"}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def api_change_password(request):
    try:
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not old_password or not new_password:
            return Response({"error": "Both old and new passwords are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Verify the current password
        if not user.check_password(old_password):
            return Response({"error": "Incorrect current password."}, status=status.HTTP_400_BAD_REQUEST)

        # Hash and save the new password
        user.set_password(new_password)
        user.save()

        return Response({"message": "Password changed successfully! Please log in again."}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



from django.contrib .auth import get_user_model

# Use this to safely get your CustomUser model
User = get_user_model() 

@api_view(['POST'])
@permission_classes([AllowAny])
def api_forgot_password(request):
    try:
        email = request.data.get('email')
        
        if not email:
            return Response({"error": "Email is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Try to find the user by email
            user = User.objects.get(email=email)
            
            # 1. Generate the secure token and UID
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            
            # 2. Build the exact URL for your frontend web app
            reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
            
            # 3. Send the custom email
            send_mail(
                subject='Password Reset Request',
                message=f'Click the link to reset your password: {reset_link}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            
        except User.DoesNotExist:
            # SECURITY FEATURE: If the email isn't in the database, we do NOTHING.
            # However, we still pass down to the success message below so hackers 
            # cannot use this API to guess which emails are registered!
            pass

        # We always return a generic success message to prevent "Email Enumeration"
        return Response(
            {"message": "If an account with this email exists, a reset link has been sent."}, 
            status=status.HTTP_200_OK
        )

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
