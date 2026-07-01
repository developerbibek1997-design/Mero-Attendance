from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from management.models import *
from .models import *


def serializer_org_id(serializer):
    request = serializer.context.get('request')
    user = getattr(request, 'user', None)
    if not user:
        return None
    if hasattr(user, 'schooladmin') and user.schooladmin:
        return user.schooladmin.org.id
    if hasattr(user, 'staff') and user.staff:
        return user.staff.org.id
    return None



class AttendanceReportSerializer(serializers.Serializer):
    member_id = serializers.IntegerField()
    member_name = serializers.CharField()
    date = serializers.DateField()
    first_checkin = serializers.DateTimeField(allow_null=True)
    last_checkout = serializers.DateTimeField(allow_null=True)
    total_hours = serializers.DurationField(allow_null=True)
    status = serializers.CharField()


class OrgSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        # Make sure these fields are actually listed here!
        fields = ['id', 'name', 'location_based', 'wifi_based', 'qr_based', 'auto_checkin']



class PaySlipSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.name', read_only=True)
    
    class Meta:
        model = PaySlip
        fields = [
            'id', 
            'member_name', 
            'from_date', 
            'to_date', 
            'month_name', 
            'total_days', 
            'present_days', 
            'paid_leaves', 
            'holidays', 
            'unpaid_absences',
            'salary_type', 
            'gross_salary', 
            'allowance_total',
            'bonus_total',
            'advance_deduction',
            'loan_deduction',
            'other_deduction',
            'tax_deduction', 
            'pf_employee',
            'pf_employer',
            'ssf_employee',
            'ssf_employer',
            'probation_adjustment',
            'net_payable', 
            'generated_on'
        ]


class PayrollPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollPolicy
        fields = [
            'id', 'pf_employee_percentage', 'pf_employer_percentage',
            'ssf_employee_percentage', 'ssf_employer_percentage',
            'probation_salary_percentage', 'probation_leave_cut_enabled',
            'probation_reminder_days', 'org'
        ]
        read_only_fields = ['org']


class PayrollAdjustmentSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.name', read_only=True)

    class Meta:
        model = PayrollAdjustment
        fields = [
            'id', 'member', 'member_name', 'adjustment_type', 'title',
            'amount', 'effective_date', 'notes', 'status', 'created_by', 'org'
        ]
        read_only_fields = ['org', 'created_by']


class ProbationReviewSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.name', read_only=True)
    reviewer_name = serializers.CharField(source='reviewer.get_full_name', read_only=True)

    class Meta:
        model = ProbationReview
        fields = [
            'id', 'member', 'member_name', 'review_date',
            'status', 'reviewer', 'reviewer_name', 'notes', 'org'
        ]
        read_only_fields = ['org', 'reviewer']


class ProvidentFundRecordSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.name', read_only=True)

    class Meta:
        model = ProvidentFundRecord
        fields = [
            'id', 'member', 'member_name', 'payslip', 'month_name',
            'employee_contribution', 'employer_contribution', 'recorded_on', 'org'
        ]
        read_only_fields = ['org']


class SocialSecurityFundRecordSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source='member.name', read_only=True)

    class Meta:
        model = SocialSecurityFundRecord
        fields = [
            'id', 'member', 'member_name', 'payslip', 'month_name',
            'employee_contribution', 'employer_contribution', 'recorded_on', 'org'
        ]
        read_only_fields = ['org']

class CourseSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.get_full_name', read_only=True)
    classification_names = serializers.SerializerMethodField()
    section_names = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'name', 'code', 'description', 'credit_hour', 'status',
            'branch', 'branch_name', 'classifications', 'classification_names',
            'sections', 'section_names', 'teacher', 'teacher_name', 'org'
        ]
        read_only_fields = ['org']

    def get_classification_names(self, obj):
        return [item.name for item in obj.classifications.all()]

    def get_section_names(self, obj):
        return [item.name for item in obj.sections.all()]
        
    def validate_name(self, value):
        org_id = serializer_org_id(self)
        qs = Course.objects.filter(name=value, org_id=org_id)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Course with this name already exists")
        return value


class BranchSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.get_full_name', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id', 'name', 'code', 'address', 'phone', 'email',
            'manager', 'manager_name', 'status', 'org'
        ]
        read_only_fields = ['org']

    def validate_code(self, value):
        org_id = serializer_org_id(self)
        qs = Branch.objects.filter(code=value, org_id=org_id)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Branch code already exists for this organization")
        return value


class SectionSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    classification_name = serializers.CharField(source='classification.name', read_only=True)

    class Meta:
        model = Section
        fields = [
            'id', 'name', 'code', 'status', 'branch', 'branch_name',
            'classification', 'classification_name', 'org'
        ]
        read_only_fields = ['org']


class StockCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StockCategory
        fields = ['id', 'name', 'description', 'org']
        read_only_fields = ['org']


class StockItemSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = [
            'id', 'name', 'sku', 'unit', 'quantity', 'low_stock_threshold',
            'supplier', 'purchase_cost', 'purchase_date', 'status',
            'branch', 'branch_name', 'category', 'category_name',
            'is_low_stock', 'org'
        ]
        read_only_fields = ['org']


class StockMovementSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'item_name', 'branch', 'branch_name',
            'movement_type', 'quantity', 'unit_cost', 'total_cost',
            'movement_date', 'note', 'created_by', 'org'
        ]
        read_only_fields = ['org', 'created_by']

    def validate(self, attrs):
        item = attrs.get('item') or getattr(self.instance, 'item', None)
        movement_type = attrs.get('movement_type') or getattr(self.instance, 'movement_type', None)
        quantity = attrs.get('quantity') or getattr(self.instance, 'quantity', None)
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        if item and movement_type in ('out', 'damage') and quantity and quantity > item.quantity:
            raise serializers.ValidationError("Stock out/damage quantity cannot exceed available stock.")
        return attrs


class TransactionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionCategory
        fields = ['id', 'name', 'transaction_type', 'org']
        read_only_fields = ['org']


class FinancialTransactionSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = FinancialTransaction
        fields = [
            'id', 'transaction_type', 'title', 'amount', 'transaction_date',
            'payment_method', 'reference_number', 'note', 'attachment',
            'branch', 'branch_name', 'category', 'category_name',
            'created_by', 'org'
        ]
        read_only_fields = ['org', 'created_by']

    def validate(self, attrs):
        category = attrs.get('category') or getattr(self.instance, 'category', None)
        transaction_type = attrs.get('transaction_type') or getattr(self.instance, 'transaction_type', None)
        amount = attrs.get('amount') or getattr(self.instance, 'amount', None)
        if amount is not None and amount <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        if category and transaction_type and category.transaction_type != transaction_type:
            raise serializers.ValidationError("Category type must match the transaction type.")
        return attrs


class BirthdayMemberSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    classification_name = serializers.CharField(source='classification.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)

    class Meta:
        model = member
        fields = [
            'id', 'name', 'date_of_birth', 'phone', 'email',
            'branch_name', 'classification_name', 'section_name'
        ]


class AttendingClassificationSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    staff_email = serializers.CharField(source='staff.email', read_only=True)
    classification_name = serializers.CharField(source='classification.name', read_only=True)
    org_id = serializers.IntegerField(source='classification.org.id', read_only=True)
    org_name = serializers.CharField(source='classification.org.name', read_only=True)
    
    class Meta:
        model = AttendingClassification
        fields = [
            'id', 
            'staff', 'staff_name', 'staff_email',
            'classification', 'classification_name',
            'org_id', 'org_name'
        ]

class CourseAttendanceSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source='staff.get_full_name', read_only=True)
    staff_email = serializers.CharField(source='staff.email', read_only=True)
    course_name = serializers.CharField(source='course.name', read_only=True)
    course_org_name = serializers.CharField(source='course.org.name', read_only=True)
    classification_name = serializers.CharField(source='classification.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    org_id = serializers.IntegerField(source='org.id', read_only=True)
    org_name = serializers.CharField(source='org.name', read_only=True)
    
    class Meta:
        model = CourseAttendance
        fields = [
            'id',
            'staff', 'staff_name', 'staff_email',
            'course', 'course_name', 'course_org_name',
            'branch', 'branch_name',
            'classification', 'classification_name',
            'section', 'section_name',
            'attendance_date', 'topic_taught', 'gap_note',
            'org_id', 'org_name'
        ]

class LocationBasedSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationBased
        fields = ['id', 'name', 'latitude', 'longitude', 'radius', 'org']
        read_only_fields = ['org']
        
    def validate(self, attrs):
        org_id = self.context['request'].user.schooladmin.org.id
        if LocationBased.objects.filter(name=attrs['name'], org_id=org_id).exists():
            raise serializers.ValidationError("Location with this name already exists")
        return attrs

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        print("Got email and password from API")
        print(email)
        print(password)
        
        user = authenticate(request=self.context.get('request'), 
                          username=email, password=password)
        
        print(user)
        if not user:
            raise serializers.ValidationError('Invalid credentials')
        
        if not user.is_active:
            raise serializers.ValidationError('Account disabled')
            
        refresh = RefreshToken.for_user(user)
        
        return {
            'email': user.email,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user_type': user.user_type,
            'org_id': user.schooladmin.org.id if hasattr(user, 'schooladmin') else  user.staff.org.id
        }

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    org_id = serializers.IntegerField(write_only=True, required=True)
    
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name', 'password', 'org_id')
        
    def validate(self, attrs):
        try:
            org = Organization.objects.get(id=attrs['org_id'])
        except Organization.DoesNotExist:
            raise serializers.ValidationError('Organization does not exist')
            
        return attrs
        
    def create(self, validated_data):
        org_id = validated_data.pop('org_id')
        org = Organization.objects.get(id=org_id)
        
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
            user_type='2'  # School admin
        )
        
        Schooladmin.objects.create(admin=user, org=org)
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
    
    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
        return value


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    new_password = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    
    def validate_new_password(self, value):
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(str(e))
        return value
    


class MemberDetailSerializer(serializers.ModelSerializer):
    classification_name = serializers.CharField(source='classification.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    course_names = serializers.SerializerMethodField()
    
    class Meta:
        model = member
        fields = [
            'id', 'name', 'member_type', 'status', 'privilege', 'card', 'gender', 'address',
            'email', 'phone', 'date_of_birth', 'created_date', 'updated_date',
            'sms_enabled', 'black_list', 'salary_per_hour',
            'staff_type', 'probation_start_date', 'probation_end_date',
            'probation_salary_percentage', 'probation_leave_cut_enabled',
            'probation_review_status', 'pf_enabled', 'ssf_enabled',
            'branch', 'branch_name', 'classification', 'classification_name',
            'section', 'section_name', 'courses', 'course_names', 'device_id'
        ]
        read_only_fields = ['created_date', 'updated_date']

    def get_course_names(self, obj):
        return [course.name for course in obj.courses.all()]

class MemberCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = member
        fields = [
            'id', 'name', 'member_type', 'status', 'privilege', 'card', 'gender', 'address',
            'email', 'phone', 'date_of_birth', 'sms_enabled', 'black_list',
            'salary_per_hour', 'staff_type', 'probation_start_date', 'probation_end_date',
            'probation_salary_percentage', 'probation_leave_cut_enabled',
            'probation_review_status', 'pf_enabled', 'ssf_enabled',
            'branch', 'classification', 'section', 'courses', 'device_id', 'org'
        ]
        
    def validate_email(self, value):
        if member.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already exists")
        return value
        
    def validate_phone(self, value):
        if member.objects.filter(phone=value).exists():
            raise serializers.ValidationError("Phone number already exists")
        return value
    

class ClassificationSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    section_count = serializers.IntegerField(source='sections.count', read_only=True)

    class Meta:
        model = Classification
        fields = ['id', 'name', 'branch', 'branch_name', 'status', 'section_count', 'org']
        read_only_fields = ['org']
        
    def validate_name(self, value):
        org_id = serializer_org_id(self)
        qs = Classification.objects.filter(name=value, org_id=org_id)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Classification with this name already exists")
        return value
    

class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        # We send ID (for the database) and Name (for the Flutter dropdown)
        fields = ['id', 'name', 'annual_allocation']


class LeaveHistorySerializer(serializers.ModelSerializer):
    # This automatically grabs the name from the linked LeaveType model!
    leave_type_name = serializers.CharField(source='leave_type.name', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = LeaveReport
        fields = ['id', 'leave_type_name', 'gap_start', 'gap_end', 'reason', 'status']

    def get_status(self, obj):
        if obj.approved:
            return 'Approved'
        if obj.rejected:
            return 'Rejected'
        return 'Pending'
