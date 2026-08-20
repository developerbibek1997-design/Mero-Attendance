import datetime
from html import escape
from html.parser import HTMLParser
import re

from django import forms
from django.db.models import Q
from django.forms.models import BaseInlineFormSet
from management.models import CustomUser
from .models import (
    Branch,
    Classification,
    Course,
    Device,
    FinancialTransaction,
    Section,
    PayrollAdjustment,
    PayrollPolicy,
    StockCategory,
    StockItem,
    StockMovement,
    ProbationReview,
    TransactionCategory,
    member,
    PaySlip,
    IDCardTemplate,
    CertificateTemplate,
    Book,
    BookIssue,
    LibraryCategory,
    LibraryAuthor,
    LibraryPublisher,
    LibraryRack,
    LibraryShelf,
    LibrarySettings,
    Account,
    JournalEntry,
    JournalEntryLine,
    AcademicYear,
    Faculty,
    Semester,
    Assignment,
    AssignmentSubmission,
    Homework,
    CourseMaterial,
    TeachingLog,
    RoutinePeriod,
    Subject,
    SubjectTeacherAssignment,
    StudentCourseEnrollment,
    Supplier,
    SupplierDocument,
    SupplierPayment,
    Purchase,
    PurchaseItem,
    PurchaseReturn,
    PurchaseReturnItem,
    Sale,
    SaleItem,
    SalePayment,
    SalesReturn,
    SalesReturnItem,
    AssetPurchase,
    Client,
)

class PaySlipForm(forms.ModelForm):
    class Meta:
        model = PaySlip
        # Updated to match the new PaySlip model fields exactly
        fields = (
            'member', 'from_date', 'to_date', 'month_name', 
            'total_days', 'present_days', 'paid_leaves', 
            'holidays', 'unpaid_absences', 'salary_type',
            'gross_salary', 'allowance_total', 'bonus_total',
            'advance_deduction', 'loan_deduction', 'other_deduction',
            'tax_deduction', 'pf_employee', 'pf_employer',
            'ssf_employee', 'ssf_employer', 'probation_adjustment',
            'net_payable'
        )

        widgets = {
            'member': forms.Select(attrs={'class': 'form-control', 'hidden': True}),
            'from_date': forms.DateInput(attrs={'class': 'form-control', 'hidden': True}),
            'to_date': forms.DateInput(attrs={'class': 'form-control', 'hidden': True}),
            'month_name': forms.TextInput(attrs={'class': 'form-control', 'hidden': True}),
            
            # New Stat Tracking Fields
            'total_days': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'present_days': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'paid_leaves': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'holidays': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'unpaid_absences': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'salary_type': forms.TextInput(attrs={'class': 'form-control', 'hidden': True}),
            
            # Financials
            'gross_salary': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'allowance_total': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'bonus_total': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'advance_deduction': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'loan_deduction': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'other_deduction': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'tax_deduction': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'pf_employee': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'pf_employer': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'ssf_employee': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'ssf_employer': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'probation_adjustment': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
            'net_payable': forms.NumberInput(attrs={'class': 'form-control', 'hidden': True}),
        }


class MemberForm(forms.ModelForm):
    class Meta:
        model = member
        # Replaced 'salary_amount' with the new 'salary_amount' & 'tax_percentage'
        fields = (
            'name', 'member_type', 'status', 'branch', 'classification', 'section', 'courses',
            'card', 'gender', 'email', 'phone', 'date_of_birth', 'admission_date', 'address',
            'photo', 'roll_number',
            'salary_type', 'salary_amount', 'overtime_rate_multiplier_override', 'tax_percentage', 'staff_type',
            'probation_start_date', 'probation_end_date', 'probation_salary_percentage',
            'probation_leave_cut_enabled', 'probation_review_status', 'pf_enabled', 'ssf_enabled',
            'make_staff', 'shift_start_time', 'shift_end_time'
        )

        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'member_type': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select', 'id': 'id_branch'}),
            'classification': forms.Select(attrs={'class': 'form-select', 'id': 'id_classification'}),
            'section': forms.Select(attrs={'class': 'form-select', 'id': 'id_section'}),
            'courses': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
            'card': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'RFID/Device Card ID'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'phone': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
                'data-year-span-back': '100', 'data-year-span-forward': '5',
            }),
            'admission_date': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
                'data-year-span-back': '60', 'data-year-span-forward': '10',
            }),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'roll_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Roll / Registration No.'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'shift_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'shift_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            
            # Payroll configurations
            'salary_type': forms.Select(attrs={'class': 'form-select'}),
            'salary_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
            'overtime_rate_multiplier_override': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Org default'}),
            'tax_percentage': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 1.0'}),
            'staff_type': forms.Select(attrs={'class': 'form-select'}),
            'probation_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'probation_end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'probation_salary_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'probation_leave_cut_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'probation_review_status': forms.Select(attrs={'class': 'form-select'}),
            'pf_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'ssf_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            
            'make_staff': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'staffCheckToggle'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        user = kwargs.pop('user', None)
        self.org = org
        self.user = user
        super(MemberForm, self).__init__(*args, **kwargs)
        if org:
            from school.hierarchy import get_accessible_branches
            self.fields['branch'].queryset = get_accessible_branches(user, org) if user else Branch.objects.filter(org=org, status='active')
            self.fields['classification'].queryset = Classification.objects.filter(org=org, status='active')
            self.fields['section'].queryset = Section.objects.filter(org=org, status='active')
            self.fields['courses'].queryset = Course.objects.filter(org=org, status='active')
            if not self.instance.pk:
                # New member: pre-fill with the org's company-wide default shift
                # rather than the model's hardcoded 9-5. Editing an existing
                # member never touches their already-saved value.
                self.fields['shift_start_time'].initial = org.default_shift_start_time
                self.fields['shift_end_time'].initial = org.default_shift_end_time
        self.fields['branch'].required = False
        self.fields['classification'].required = False
        self.fields['section'].required = False
        self.fields['courses'].required = False
        checkbox_fields = {'make_staff', 'probation_leave_cut_enabled', 'pf_enabled', 'ssf_enabled'}
        for field in self.fields:
            if field not in checkbox_fields:  # Don't apply form-control to checkboxes
                self.fields[field].widget.attrs.update({'class': 'form-control'})
            self.fields[field].widget.attrs.update({'placeholder': field.capitalize()})

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            return None  # empty string → NULL, avoids unique constraint on blank emails
        if member.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This email address is already in use.')
        return email

    def clean(self):
        cleaned = super().clean()
        if not self.org:
            return cleaned
        card = (cleaned.get('card') or '').strip()
        branch = cleaned.get('branch')
        classification = cleaned.get('classification')
        section = cleaned.get('section')
        courses = cleaned.get('courses')
        if classification and branch and not classification.is_available_to_branch(branch.id):
            self.add_error('classification', 'Classification is not available to the selected branch.')
        if section and classification and section.classification_id != classification.id:
            self.add_error('section', 'Section does not belong to the selected classification.')
        if section and branch and section.branch_id and section.branch_id != branch.id:
            self.add_error('section', 'Section does not belong to the selected branch.')
        if courses:
            for course in courses:
                if classification and course.classifications.exists() and not course.classifications.filter(pk=classification.pk).exists():
                    self.add_error('courses', f'{course.name} is not linked to the selected classification.')
                if section and course.sections.exists() and not course.sections.filter(pk=section.pk).exists():
                    self.add_error('courses', f'{course.name} is not linked to the selected section.')
        return cleaned

   

class ClassificationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        self.org = org
        super(ClassificationForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branches'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branches'].required = False

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get('name') or '').strip()
        if self.org and name and Classification.objects.filter(
            org=self.org, name__iexact=name,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error('name', 'This classification already exists in this organization.')
        return cleaned

    class Meta:
        model = Classification
        fields = ('name', 'branches', 'default_shift_start_time', 'default_shift_end_time', 'status')
        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Classification / Department / Class'}),
            'branches': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
            'default_shift_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'default_shift_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = (
            'name', 'code', 'address', 'phone', 'email', 'manager',
            'default_shift_start_time', 'default_shift_end_time', 'status',
        )
        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class': 'form-control', 'placeholder': 'Branch name'}),
            'code': forms.TextInput(attrs={'required': True, 'class': 'form-control', 'placeholder': 'Branch code'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'manager': forms.Select(attrs={'class': 'form-select'}),
            'default_shift_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'default_shift_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(BranchForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['manager'].queryset = CustomUser.objects.filter(
                Q(schooladmin__org=org) | Q(staff__org=org)
            ).distinct()
        self.fields['manager'].required = False


class SectionForm(forms.ModelForm):
    class Meta:
        model = Section
        fields = ('branch', 'classification', 'name', 'code', 'status')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'classification': forms.Select(attrs={'required': True, 'class': 'form-select'}),
            'name': forms.TextInput(attrs={'required': True, 'class': 'form-control', 'placeholder': 'Section name'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Section code'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(SectionForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['classification'].queryset = Classification.objects.filter(org=org, status='active')
        self.fields['branch'].required = False

    def clean(self):
        cleaned = super().clean()
        branch = cleaned.get('branch')
        classification = cleaned.get('classification')
        if branch and classification and not classification.is_available_to_branch(branch.id):
            self.add_error('branch', f'"{classification.name}" is not available to this branch.')
        return cleaned


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ('branch', 'classifications', 'sections', 'teacher', 'code', 'name', 'description', 'credit_hour', 'status')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'classifications': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
            'sections': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Course code'}),
            'name': forms.TextInput(attrs={'required': True, 'class': 'form-control', 'placeholder': 'Course / Subject title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Short description'}),
            'credit_hour': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        self.org = org
        super(CourseForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['classifications'].queryset = Classification.objects.filter(org=org, status='active')
            self.fields['sections'].queryset = Section.objects.filter(org=org, status='active')
            self.fields['teacher'].queryset = CustomUser.objects.filter(
                Q(schooladmin__org=org) | Q(staff__org=org)
            ).distinct()
        self.fields['branch'].required = False
        self.fields['classifications'].required = False
        self.fields['sections'].required = False
        self.fields['teacher'].required = False

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get('name') or '').strip()
        code = (cleaned.get('code') or '').strip()
        scope = Course.objects.filter(org=self.org, branch=cleaned.get('branch')).exclude(pk=self.instance.pk) if self.org else Course.objects.none()
        if name and scope.filter(name__iexact=name).exists():
            self.add_error('name', 'A course with this name already exists in the selected branch.')
        if code and scope.filter(code__iexact=code).exists():
            self.add_error('code', 'A course with this code already exists in the selected branch.')
        return cleaned


class StockCategoryForm(forms.ModelForm):
    class Meta:
        model = StockCategory
        fields = ('name', 'description')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional description'}),
        }


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = (
            'branch', 'category', 'name', 'sku', 'unit', 'quantity',
            'low_stock_threshold', 'supplier', 'purchase_cost', 'purchase_date', 'status'
        )
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item name'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SKU / code'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'pcs, kg, box'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'low_stock_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(StockItemForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['category'].queryset = StockCategory.objects.filter(org=org)
        self.fields['branch'].required = False
        self.fields['category'].required = False


class StockMovementForm(forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ('branch', 'item', 'movement_type', 'quantity', 'unit_cost', 'movement_date', 'note')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'item': forms.Select(attrs={'class': 'form-select'}),
            'movement_type': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'movement_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason or note'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(StockMovementForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['item'].queryset = StockItem.objects.filter(org=org, status='active')
        self.fields['branch'].required = False

    def clean(self):
        cleaned_data = super().clean()
        movement_type = cleaned_data.get('movement_type')
        quantity = cleaned_data.get('quantity')
        item = cleaned_data.get('item')
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError('Quantity must be greater than zero.')
        if item and movement_type in ('out', 'damage') and quantity and quantity > item.quantity:
            raise forms.ValidationError('Stock out/damage quantity cannot exceed available stock.')
        return cleaned_data


class TransactionCategoryForm(forms.ModelForm):
    class Meta:
        model = TransactionCategory
        fields = ('name', 'transaction_type')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
        }


class FinancialTransactionForm(forms.ModelForm):
    class Meta:
        model = FinancialTransaction
        fields = (
            'branch', 'category', 'transaction_type', 'title', 'amount',
            'transaction_date', 'payment_method', 'reference_number', 'note', 'attachment'
        )
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Title'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'transaction_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Receipt/ref no.'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional note'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(FinancialTransactionForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['category'].queryset = TransactionCategory.objects.filter(org=org)
        self.fields['branch'].required = False
        self.fields['category'].required = False

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        transaction_type = cleaned_data.get('transaction_type')
        amount = cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        if category and transaction_type and category.transaction_type != transaction_type:
            raise forms.ValidationError('Category type must match the transaction type.')
        return cleaned_data


class PayrollPolicyForm(forms.ModelForm):
    class Meta:
        model = PayrollPolicy
        fields = (
            'pf_employee_percentage', 'pf_employer_percentage',
            'ssf_employee_percentage', 'ssf_employer_percentage',
            'probation_salary_percentage', 'probation_leave_cut_enabled',
            'probation_reminder_days', 'overtime_rate_multiplier',
            'late_grace_minutes',
        )
        widgets = {
            'pf_employee_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'pf_employer_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ssf_employee_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ssf_employer_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'probation_salary_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'probation_leave_cut_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'probation_reminder_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'overtime_rate_multiplier': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '1.0'}),
            'late_grace_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
        }


class PayrollAdjustmentForm(forms.ModelForm):
    class Meta:
        model = PayrollAdjustment
        fields = ('member', 'adjustment_type', 'title', 'amount', 'effective_date', 'notes', 'status')
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'adjustment_type': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Allowance, advance, loan, bonus...'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(PayrollAdjustmentForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['member'].queryset = member.objects.filter(org=org).order_by('name')

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= 0:
            raise forms.ValidationError('Amount must be greater than zero.')
        return amount


class ProbationReviewForm(forms.ModelForm):
    class Meta:
        model = ProbationReview
        fields = ('member', 'review_date', 'status', 'notes')
        widgets = {
            'member': forms.Select(attrs={'class': 'form-select'}),
            'review_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(ProbationReviewForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['member'].queryset = member.objects.filter(org=org).order_by('name')


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        fields = (
            'name', 'connection_mode', 'serial_number',
            'ip_address', 'port_no',
        )
        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Name of the Device'}),
            'connection_mode': forms.Select(attrs={'class': 'form-select'}),
            'serial_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Example: CQZK241260123',
                'autocomplete': 'off',
            }),
            'ip_address': forms.TextInput(attrs={'class':'form-control', 'placeholder':'Local IP (puller only)'}),
            'port_no': forms.NumberInput(attrs={'class':'form-control', 'placeholder':'4370'})
        }

    def clean_serial_number(self):
        value = (self.cleaned_data.get('serial_number') or '').strip().upper()
        mode = self.cleaned_data.get('connection_mode')
        if mode == 'adms' and not value:
            raise forms.ValidationError(
                'Serial number is required for an ADMS cloud device.'
            )
        return value or None


class IDCardTemplateForm(forms.ModelForm):
    # `name` (the design key) is NOT a form field: the settings page selects the
    # design via the ?design= query param / hidden "design" input, and the view
    # assigns it. Including it here made it a required field that the template
    # never rendered, so every save failed with "name: This field is required".
    #
    # The custom_* sizes only matter when card_size == 'custom', but the template
    # always shows them — so treat a blank box as "use the model default" rather
    # than a validation error.
    _OPTIONAL_WITH_DEFAULT = (
        'primary_color', 'secondary_color', 'text_color',
        'font_family', 'base_font_size', 'name_font_size', 'org_font_size', 'line_height',
        'custom_width_mm', 'custom_height_mm', 'custom_photo_size_mm',
    )

    class Meta:
        model = IDCardTemplate
        fields = (
            'is_default', 'primary_color', 'secondary_color', 'text_color',
            'font_family', 'base_font_size', 'name_font_size', 'org_font_size',
            'line_height', 'card_title', 'footer_text',
            'card_size', 'custom_width_mm', 'custom_height_mm',
            'photo_size', 'custom_photo_size_mm',
            'front_background', 'back_background',
            'show_logo', 'show_org_name', 'show_photo', 'show_member_id',
            'show_roll_number', 'show_address', 'show_phone', 'show_email',
            'show_classification', 'show_qr_code', 'show_barcode',
            'show_designation',
        )
        widgets = {
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'text_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'font_family': forms.Select(attrs={'class': 'form-select'}),
            'base_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 7, 'max': 22}),
            'name_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 9, 'max': 30}),
            'org_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 8, 'max': 26}),
            'line_height': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 2.5, 'step': .05}),
            'card_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. STUDENT ID CARD'}),
            'footer_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional verification or return instruction'}),
            'card_size': forms.Select(attrs={'class': 'form-select'}),
            'custom_width_mm': forms.NumberInput(attrs={'class': 'form-control'}),
            'custom_height_mm': forms.NumberInput(attrs={'class': 'form-control'}),
            'photo_size': forms.Select(attrs={'class': 'form-select'}),
            'custom_photo_size_mm': forms.NumberInput(attrs={'class': 'form-control'}),
            'front_background': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'back_background': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'show_logo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_org_name': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_photo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_member_id': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_roll_number': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_address': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_phone': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_classification': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_qr_code': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_barcode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_designation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fname in self._OPTIONAL_WITH_DEFAULT:
            self.fields[fname].required = False

    def clean(self):
        cleaned = super().clean()
        # Fall back to the model's own default when a size box is left blank.
        for fname in self._OPTIONAL_WITH_DEFAULT:
            if cleaned.get(fname) in (None, ''):
                current_value = getattr(self.instance, fname, None)
                cleaned[fname] = (
                    current_value
                    if current_value not in (None, '')
                    else IDCardTemplate._meta.get_field(fname).get_default()
                )
        for field_name, low, high in (
            ('base_font_size', 7, 22),
            ('name_font_size', 9, 30),
            ('org_font_size', 8, 26),
        ):
            value = cleaned.get(field_name)
            if value is not None and not low <= value <= high:
                self.add_error(field_name, f'Choose a size between {low} and {high}px.')
        line_height = cleaned.get('line_height')
        if line_height is not None and not 1 <= line_height <= 2.5:
            self.add_error('line_height', 'Choose line spacing between 1.00 and 2.50.')
        return cleaned


class _CertificateHTMLSanitizer(HTMLParser):
    """Small allow-list sanitizer for the certificate rich-text editor."""

    allowed_tags = {'p', 'div', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'ul', 'ol', 'li'}
    void_tags = {'br'}
    alignment = re.compile(r'^\s*text-align\s*:\s*(left|center|right|justify)\s*;?\s*$', re.I)

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag not in self.allowed_tags:
            return
        style_value = ''
        for key, value in attrs:
            if key.lower() == 'style' and value:
                match = self.alignment.match(value)
                if match:
                    style_value = f' style="text-align:{match.group(1).lower()}"'
        self.parts.append(f'<{tag}{style_value}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.allowed_tags and tag not in self.void_tags:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        self.parts.append(escape(data))

    def sanitized(self):
        return ''.join(self.parts).strip()


def sanitize_certificate_html(value):
    parser = _CertificateHTMLSanitizer()
    parser.feed(value or '')
    parser.close()
    return parser.sanitized()


class CertificateTemplateForm(forms.ModelForm):
    class Meta:
        model = CertificateTemplate
        fields = (
            'name', 'certificate_type', 'orientation', 'is_default', 'is_active',
            'title', 'subtitle', 'body_html', 'footer_text', 'serial_prefix',
            'primary_color', 'secondary_color', 'text_color', 'border_style',
            'font_family', 'title_font_size', 'recipient_font_size',
            'body_font_size', 'line_height', 'background_image', 'letterhead_image',
            'show_logo', 'show_issue_date', 'show_certificate_number',
            'signature_one_name', 'signature_one_title', 'signature_one_image',
            'signature_two_name', 'signature_two_title', 'signature_two_image',
        )
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Grade 10 Completion 2026'}),
            'certificate_type': forms.Select(attrs={'class': 'form-select'}),
            'orientation': forms.Select(attrs={'class': 'form-select'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'subtitle': forms.TextInput(attrs={'class': 'form-control'}),
            'body_html': forms.HiddenInput(),
            'footer_text': forms.TextInput(attrs={'class': 'form-control'}),
            'serial_prefix': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 20}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'text_color': forms.TextInput(attrs={'class': 'form-control form-control-color', 'type': 'color'}),
            'border_style': forms.Select(attrs={'class': 'form-select'}),
            'font_family': forms.Select(attrs={'class': 'form-select'}),
            'title_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 22, 'max': 72}),
            'recipient_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 20, 'max': 64}),
            'body_font_size': forms.NumberInput(attrs={'class': 'form-control', 'min': 11, 'max': 32}),
            'line_height': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 2.5, 'step': .05}),
            'background_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'letterhead_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'show_logo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_issue_date': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_certificate_number': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'signature_one_name': forms.TextInput(attrs={'class': 'form-control'}),
            'signature_one_title': forms.TextInput(attrs={'class': 'form-control'}),
            'signature_one_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'signature_two_name': forms.TextInput(attrs={'class': 'form-control'}),
            'signature_two_title': forms.TextInput(attrs={'class': 'form-control'}),
            'signature_two_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, org=None, **kwargs):
        self.org = org
        super().__init__(*args, **kwargs)

    def clean_name(self):
        value = (self.cleaned_data.get('name') or '').strip()
        if self.org and CertificateTemplate.objects.filter(org=self.org, name__iexact=value).exclude(
            pk=self.instance.pk
        ).exists():
            raise forms.ValidationError('A certificate template with this name already exists.')
        return value

    def clean_body_html(self):
        value = sanitize_certificate_html(self.cleaned_data.get('body_html'))
        if not value:
            raise forms.ValidationError('Add certificate body text.')
        return value

    def clean_serial_prefix(self):
        value = re.sub(r'[^A-Za-z0-9_-]', '', self.cleaned_data.get('serial_prefix') or '').upper()
        return value or 'CERT'

    def clean(self):
        cleaned = super().clean()
        for field_name, low, high in (
            ('title_font_size', 22, 72),
            ('recipient_font_size', 20, 64),
            ('body_font_size', 11, 32),
        ):
            value = cleaned.get(field_name)
            if value is not None and not low <= value <= high:
                self.add_error(field_name, f'Choose a size between {low} and {high}px.')
        line_height = cleaned.get('line_height')
        if line_height is not None and not 1 <= line_height <= 2.5:
            self.add_error('line_height', 'Choose line spacing between 1.00 and 2.50.')
        return cleaned


# =============================================================
# LIBRARY MANAGEMENT
# =============================================================

class LibraryCategoryForm(forms.ModelForm):
    class Meta:
        model = LibraryCategory
        fields = ('name', 'description')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional description'}),
        }


class LibraryAuthorForm(forms.ModelForm):
    class Meta:
        model = LibraryAuthor
        fields = ('name', 'bio')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Author name'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional bio'}),
        }


class LibraryPublisherForm(forms.ModelForm):
    class Meta:
        model = LibraryPublisher
        fields = ('name', 'address', 'contact')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Publisher name'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone / email'}),
        }


class LibraryRackForm(forms.ModelForm):
    class Meta:
        model = LibraryRack
        fields = ('branch', 'code', 'name')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. R1'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional label'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branch'].required = False


class LibraryShelfForm(forms.ModelForm):
    class Meta:
        model = LibraryShelf
        fields = ('rack', 'code', 'name')
        widgets = {
            'rack': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. S1'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional label'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['rack'].queryset = LibraryRack.objects.filter(org=org)


class LibrarySettingsForm(forms.ModelForm):
    class Meta:
        model = LibrarySettings
        fields = ('loan_period_days', 'fine_per_day', 'max_books_per_member')
        widgets = {
            'loan_period_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'fine_per_day': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_books_per_member': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = (
            'branch', 'book_code', 'isbn', 'title', 'subtitle', 'category', 'subject',
            'author', 'publisher', 'edition', 'language', 'rack', 'shelf',
            'purchase_date', 'purchase_price', 'quantity', 'cover_image', 'description', 'status',
        )
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'book_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Accession / book code'}),
            'isbn': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ISBN'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Book title'}),
            'subtitle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subtitle (optional)'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject'}),
            'author': forms.Select(attrs={'class': 'form-select'}),
            'publisher': forms.Select(attrs={'class': 'form-select'}),
            'edition': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Edition'}),
            'language': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Language'}),
            'rack': forms.Select(attrs={'class': 'form-select'}),
            'shelf': forms.Select(attrs={'class': 'form-select'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'purchase_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'cover_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['category'].queryset = LibraryCategory.objects.filter(org=org)
            self.fields['author'].queryset = LibraryAuthor.objects.filter(org=org)
            self.fields['publisher'].queryset = LibraryPublisher.objects.filter(org=org)
            self.fields['rack'].queryset = LibraryRack.objects.filter(org=org)
            self.fields['shelf'].queryset = LibraryShelf.objects.filter(org=org)
        for f in ('branch', 'category', 'subject', 'author', 'publisher', 'edition',
                   'language', 'rack', 'shelf', 'isbn', 'subtitle', 'purchase_date',
                   'purchase_price', 'cover_image', 'description'):
            self.fields[f].required = False

    def clean_book_code(self):
        code = self.cleaned_data['book_code'].strip()
        if not code:
            raise forms.ValidationError('Book code is required.')
        return code


class BookIssueForm(forms.ModelForm):
    """Issue a copy to a member/student/staff. `book`/`member` querysets are
    scoped to the org and to books currently available."""

    class Meta:
        model = BookIssue
        fields = ('book', 'member', 'branch', 'issue_date', 'due_date', 'remarks')
        widgets = {
            'book': forms.Select(attrs={'class': 'form-select'}),
            'member': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'issue_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional remarks'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['book'].queryset = Book.objects.filter(org=org, status='active', available_quantity__gt=0)
            self.fields['member'].queryset = member.objects.filter(org=org, status='active').order_by('name')
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branch'].required = False
        self.fields['remarks'].required = False

    def clean(self):
        cleaned = super().clean()
        book = cleaned.get('book')
        if book and book.available_quantity <= 0:
            raise forms.ValidationError('No copies of this book are currently available.')
        return cleaned


# =============================================================
# ACCOUNTING CORE
# =============================================================

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ('parent', 'code', 'name', 'account_type', 'is_group', 'opening_balance', 'description', 'is_active')
        widgets = {
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional, e.g. 1000'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account name'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'is_group': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self.fields['parent'].required = False
        self.fields['description'].required = False
        if org:
            qs = Account.objects.filter(org=org, is_group=True)
            if self.instance.pk:
                # Exclude self and descendants — prevents a parent-cycle.
                descendant_ids = self._descendant_ids(self.instance)
                qs = qs.exclude(pk__in=[self.instance.pk] + descendant_ids)
            self.fields['parent'].queryset = qs

    def _descendant_ids(self, account):
        ids = []
        for child in account.children.all():
            ids.append(child.pk)
            ids.extend(self._descendant_ids(child))
        return ids


class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = ('entry_date', 'reference', 'description', 'attachment', 'branch')
        widgets = {
            'entry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional reference'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self.fields['branch'].required = False
        self.fields['reference'].required = False
        self.fields['description'].required = False
        self.fields['attachment'].required = False
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')


JournalEntryLineFormSet = forms.inlineformset_factory(
    JournalEntry, JournalEntryLine,
    fields=('account', 'debit', 'credit', 'remarks'),
    widgets={
        'account': forms.Select(attrs={'class': 'form-select account-select'}),
        'debit': forms.NumberInput(attrs={'class': 'form-control debit-input', 'step': '0.01', 'placeholder': '0.00'}),
        'credit': forms.NumberInput(attrs={'class': 'form-control credit-input', 'step': '0.01', 'placeholder': '0.00'}),
        'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
    },
    extra=2, min_num=2, validate_min=True, can_delete=True,
)


# =============================================================
# ACADEMIC MANAGEMENT
# =============================================================

class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ('name', 'start_date', 'end_date', 'is_current', 'status')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2082/83'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_current': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self.fields['start_date'].required = False
        self.fields['end_date'].required = False


class FacultyForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = ('name', 'code', 'description', 'status')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Faculty name'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional code'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self.fields['code'].required = False
        self.fields['description'].required = False


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ('faculty', 'academic_year', 'name', 'order', 'start_date', 'end_date', 'status')
        widgets = {
            'faculty': forms.Select(attrs={'class': 'form-select'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Semester 1'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['faculty'].queryset = Faculty.objects.filter(org=org, status='active')
            self.fields['academic_year'].queryset = AcademicYear.objects.filter(org=org)
        self.fields['faculty'].required = False
        self.fields['academic_year'].required = False
        self.fields['start_date'].required = False
        self.fields['end_date'].required = False


class TeachingScopeChoiceField(forms.ModelChoiceField):
    """Readable, exact subject/class/section authority for teacher workflows."""

    def label_from_instance(self, assignment):
        course = f"{assignment.course.name} / " if assignment.course_id else ""
        section = f" / {assignment.section.name}" if assignment.section_id else " / All sections"
        year = f" · {assignment.academic_year.name}" if assignment.academic_year_id else ""
        return (
            f"{course}{assignment.classification.name}{section}"
            f" → {assignment.subject.name}{year}"
        )


def _active_teacher_scope_queryset(org, teacher, *, include_pk=None):
    today = datetime.date.today()
    qs = SubjectTeacherAssignment.objects.filter(
        org=org,
        teacher=teacher,
        subject__status='active',
        status='active',
        start_date__lte=today,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )
    if include_pk:
        qs = SubjectTeacherAssignment.objects.filter(
            Q(pk=include_pk) | Q(pk__in=qs),
            org=org,
            teacher=teacher,
        )
    return qs.select_related(
        'academic_year', 'course', 'classification', 'section', 'subject',
    ).distinct().order_by(
        'classification__name', 'section__name', 'subject__name',
    )


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = (
            'classification', 'section', 'subject', 'course', 'semester',
            'title', 'description', 'instructions', 'start_date', 'due_date',
            'total_marks', 'passing_marks', 'visibility', 'status',
        )
        widgets = {
            'classification': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'course': forms.Select(attrs={'class': 'form-select'}),
            'semester': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Assignment title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'passing_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'visibility': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self._org = org
        if org:
            self.instance.org = org
            self.fields['classification'].queryset = Classification.objects.filter(org=org, status='active')
            self.fields['section'].queryset = Section.objects.filter(org=org, status='active')
            self.fields['subject'].queryset = Subject.objects.filter(org=org, status='active')
            self.fields['course'].queryset = Course.objects.filter(org=org, status='active')
            self.fields['semester'].queryset = Semester.objects.filter(org=org)
        for f in ('section', 'course', 'semester', 'description', 'instructions'):
            self.fields[f].required = False

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get('subject')
        classification = cleaned.get('classification')
        section = cleaned.get('section')
        course = cleaned.get('course')
        start_date = cleaned.get('start_date')
        due_date = cleaned.get('due_date')
        total_marks = cleaned.get('total_marks')
        passing_marks = cleaned.get('passing_marks')
        if not subject:
            return cleaned
        if self._org and subject.org_id != self._org.pk:
            self.add_error('subject', "Select a subject from this organization.")
        if classification and classification.pk != subject.classification_id:
            self.add_error('classification', "Classification must match the selected subject.")
        if course != subject.course:
            self.add_error('course', "Course must match the selected subject.")
        if subject.section_id and section != subject.section:
            self.add_error('section', "Section must match the selected subject.")
        elif section and section.classification_id != subject.classification_id:
            self.add_error('section', "Section must belong to the subject classification.")
        if start_date and due_date and due_date < start_date:
            self.add_error('due_date', "Due date cannot be before the start date.")
        if total_marks is not None and total_marks <= 0:
            self.add_error('total_marks', "Total marks must be greater than zero.")
        if passing_marks is not None and total_marks is not None and not (
            0 <= passing_marks <= total_marks
        ):
            self.add_error('passing_marks', "Passing marks must be between zero and total marks.")
        return cleaned


class TeacherAssignmentForm(forms.ModelForm):
    teaching_scope = TeachingScopeChoiceField(
        queryset=SubjectTeacherAssignment.objects.none(),
        label='Assigned class / subject',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = Assignment
        fields = (
            'teaching_scope', 'title', 'description', 'instructions',
            'start_date', 'due_date', 'total_marks', 'passing_marks',
            'visibility', 'status',
        )
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Assignment title'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 1}),
            'passing_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': 0}),
            'visibility': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop('org')
        self.teacher = kwargs.pop('teacher')
        super().__init__(*args, **kwargs)
        self.instance.org = self.org
        include_pk = self.instance.teacher_assignment_id if self.instance.pk else None
        self.fields['teaching_scope'].queryset = _active_teacher_scope_queryset(
            self.org, self.teacher, include_pk=include_pk,
        )
        if include_pk:
            self.fields['teaching_scope'].initial = include_pk
        for field in ('description', 'instructions'):
            self.fields[field].required = False

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get('teaching_scope')
        start_date = cleaned.get('start_date')
        due_date = cleaned.get('due_date')
        total_marks = cleaned.get('total_marks')
        passing_marks = cleaned.get('passing_marks')
        if not scope:
            return cleaned
        if scope.org_id != self.org.pk or scope.teacher_id != self.teacher.pk:
            raise forms.ValidationError("Select one of your active assigned subjects.")
        if not scope.is_active_on():
            self.add_error('teaching_scope', "This teaching assignment is not active.")
        if start_date and due_date and due_date < start_date:
            self.add_error('due_date', "Due date cannot be before the start date.")
        if total_marks is not None and total_marks <= 0:
            self.add_error('total_marks', "Total marks must be greater than zero.")
        if passing_marks is not None and total_marks is not None and not (
            0 <= passing_marks <= total_marks
        ):
            self.add_error('passing_marks', "Passing marks must be between zero and total marks.")

        self.instance.teacher_assignment = scope
        self.instance.subject = scope.subject
        self.instance.classification = scope.classification
        self.instance.section = scope.section
        self.instance.course = scope.course
        self.instance.branch = scope.branch
        self.instance.assigned_by = self.teacher
        return cleaned


class AssignmentSubmissionForm(forms.ModelForm):
    """Student-facing: file + comments only."""
    class Meta:
        model = AssignmentSubmission
        fields = ('student_comments',)
        widgets = {
            'student_comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional comments'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self.fields['student_comments'].required = False


class AssignmentGradeForm(forms.ModelForm):
    """Teacher-facing: marks + remarks + status."""
    class Meta:
        model = AssignmentSubmission
        fields = ('obtained_marks', 'teacher_remarks', 'status')
        widgets = {
            'obtained_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'teacher_remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self.fields['obtained_marks'].required = False
        self.fields['teacher_remarks'].required = False

    def clean(self):
        cleaned = super().clean()
        marks = cleaned.get('obtained_marks')
        status = cleaned.get('status')
        assignment = getattr(self.instance, 'assignment', None)
        if marks is not None:
            if marks < 0:
                self.add_error('obtained_marks', "Marks cannot be negative.")
            elif assignment and marks > assignment.total_marks:
                self.add_error(
                    'obtained_marks',
                    f"Marks cannot exceed {assignment.total_marks}.",
                )
        if status == 'graded' and marks is None:
            self.add_error('obtained_marks', "Enter marks before grading.")
        return cleaned


class HomeworkForm(forms.ModelForm):
    class Meta:
        model = Homework
        fields = (
            'classification', 'section', 'subject', 'description', 'due_date',
            'priority', 'estimated_time_minutes', 'frequency', 'status',
        )
        widgets = {
            'classification': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'estimated_time_minutes': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'minutes'}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self._org = org
        if org:
            self.instance.org = org
            self.fields['classification'].queryset = Classification.objects.filter(org=org, status='active')
            self.fields['section'].queryset = Section.objects.filter(org=org, status='active')
            self.fields['subject'].queryset = Subject.objects.filter(org=org, status='active')
        self.fields['section'].required = False
        self.fields['estimated_time_minutes'].required = False

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get('subject')
        classification = cleaned.get('classification')
        section = cleaned.get('section')
        if not subject:
            return cleaned
        if self._org and subject.org_id != self._org.pk:
            self.add_error('subject', "Select a subject from this organization.")
        if classification and classification.pk != subject.classification_id:
            self.add_error('classification', "Classification must match the selected subject.")
        if subject.section_id and section != subject.section:
            self.add_error('section', "Section must match the selected subject.")
        elif section and section.classification_id != subject.classification_id:
            self.add_error('section', "Section must belong to the subject classification.")
        return cleaned


class TeacherHomeworkForm(forms.ModelForm):
    teaching_scope = TeachingScopeChoiceField(
        queryset=SubjectTeacherAssignment.objects.none(),
        label='Assigned class / subject',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = Homework
        fields = (
            'teaching_scope', 'description', 'due_date', 'priority',
            'estimated_time_minutes', 'frequency', 'status',
        )
        widgets = {
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'estimated_time_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'frequency': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop('org')
        self.teacher = kwargs.pop('teacher')
        super().__init__(*args, **kwargs)
        self.instance.org = self.org
        include_pk = self.instance.teacher_assignment_id if self.instance.pk else None
        self.fields['teaching_scope'].queryset = _active_teacher_scope_queryset(
            self.org, self.teacher, include_pk=include_pk,
        )
        if include_pk:
            self.fields['teaching_scope'].initial = include_pk
        self.fields['estimated_time_minutes'].required = False

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get('teaching_scope')
        if not scope:
            return cleaned
        if scope.org_id != self.org.pk or scope.teacher_id != self.teacher.pk:
            raise forms.ValidationError("Select one of your active assigned subjects.")
        if not scope.is_active_on():
            self.add_error('teaching_scope', "This teaching assignment is not active.")

        self.instance.teacher_assignment = scope
        self.instance.subject = scope.subject
        self.instance.classification = scope.classification
        self.instance.section = scope.section
        self.instance.branch = scope.branch
        self.instance.assigned_by = self.teacher
        return cleaned


class CourseMaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = (
            'faculty', 'course', 'semester', 'subject', 'chapter', 'unit',
            'title', 'material_type', 'file', 'external_link', 'is_active',
        )
        widgets = {
            'faculty': forms.Select(attrs={'class': 'form-select'}),
            'course': forms.Select(attrs={'class': 'form-select'}),
            'semester': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'chapter': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'material_type': forms.Select(attrs={'class': 'form-select'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'external_link': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['faculty'].queryset = Faculty.objects.filter(org=org, status='active')
            self.fields['course'].queryset = Course.objects.filter(org=org, status='active')
            self.fields['semester'].queryset = Semester.objects.filter(org=org)
            self.fields['subject'].queryset = Subject.objects.filter(org=org, status='active')
        for f in ('faculty', 'course', 'semester', 'chapter', 'unit', 'file', 'external_link'):
            self.fields[f].required = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('file') and not cleaned.get('external_link') and not self.instance.pk:
            raise forms.ValidationError("Provide either a file or an external link.")
        return cleaned


class TeachingLogForm(forms.ModelForm):
    class Meta:
        model = TeachingLog
        fields = (
            'subject', 'classification', 'section', 'date', 'period',
            'topic_covered', 'chapter', 'learning_objectives', 'remarks',
        )
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'classification': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'period': forms.NumberInput(attrs={'class': 'form-control'}),
            'topic_covered': forms.TextInput(attrs={'class': 'form-control'}),
            'chapter': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'learning_objectives': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['subject'].queryset = Subject.objects.filter(org=org, status='active')
            self.fields['classification'].queryset = Classification.objects.filter(org=org, status='active')
            self.fields['section'].queryset = Section.objects.filter(org=org, status='active')
        for f in ('section', 'period', 'chapter', 'learning_objectives', 'remarks'):
            self.fields[f].required = False


class SubjectTeacherAssignmentForm(forms.ModelForm):
    class Meta:
        model = SubjectTeacherAssignment
        fields = (
            'teacher', 'academic_year', 'section', 'start_date', 'end_date',
            'status', 'is_primary', 'notes',
        )
        widgets = {
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop('org')
        self.subject = kwargs.pop('subject')
        super().__init__(*args, **kwargs)
        self.instance.org = self.org
        self.instance.subject = self.subject
        self.fields['teacher'].queryset = CustomUser.objects.filter(
            staff__org=self.org
        ).distinct().order_by('first_name', 'last_name', 'email')
        self.fields['academic_year'].queryset = AcademicYear.objects.filter(
            org=self.org, status='active'
        )
        self.fields['section'].queryset = Section.objects.filter(
            org=self.org,
            classification=self.subject.classification,
            status='active',
        )
        if self.subject.section_id:
            self.fields['section'].queryset = self.fields['section'].queryset.filter(
                pk=self.subject.section_id
            )
            self.fields['section'].initial = self.subject.section_id
            self.fields['section'].disabled = True
        self.fields['academic_year'].required = False
        self.fields['section'].required = bool(self.subject.section_id)
        self.fields['end_date'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned = super().clean()
        teacher = cleaned.get('teacher')
        academic_year = cleaned.get('academic_year')
        section = cleaned.get('section')
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        status = cleaned.get('status')
        if not teacher or not start_date or status != 'active':
            return cleaned

        overlaps = SubjectTeacherAssignment.objects.filter(
            subject=self.subject,
            teacher=teacher,
            section=section,
            status='active',
            start_date__lte=end_date or datetime.date.max,
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=start_date)
        )
        if academic_year:
            overlaps = overlaps.filter(academic_year=academic_year)
        else:
            overlaps = overlaps.filter(academic_year__isnull=True)
        if self.instance.pk:
            overlaps = overlaps.exclude(pk=self.instance.pk)
        if overlaps.exists():
            raise forms.ValidationError(
                "This teacher already has an overlapping active assignment for this exact subject scope."
            )
        return cleaned

    def save(self, commit=True):
        assignment = super().save(commit=False)
        assignment.subject = self.subject
        assignment.org = self.org
        if commit:
            assignment.save()
            self.save_m2m()
        return assignment


class StudentCourseEnrollmentForm(forms.ModelForm):
    class Meta:
        model = StudentCourseEnrollment
        fields = (
            'student', 'academic_year', 'classification', 'section',
            'start_date', 'end_date', 'status', 'notes',
        )
        widgets = {
            'student': forms.Select(attrs={'class': 'form-select'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'classification': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        self.org = kwargs.pop('org')
        self.course = kwargs.pop('course')
        super().__init__(*args, **kwargs)
        self.instance.org = self.org
        self.instance.course = self.course
        self.fields['student'].queryset = member.objects.filter(
            org=self.org,
            status='active',
            member_type__in=('student', 'trainee'),
        ).order_by('name')
        self.fields['academic_year'].queryset = AcademicYear.objects.filter(
            org=self.org, status='active'
        )
        self.fields['classification'].queryset = self.course.classifications.filter(
            org=self.org, status='active'
        )
        self.fields['section'].queryset = self.course.sections.filter(
            org=self.org, status='active'
        )
        self.fields['academic_year'].required = False
        self.fields['section'].required = False
        self.fields['end_date'].required = False
        self.fields['notes'].required = False

    def clean(self):
        cleaned = super().clean()
        student = cleaned.get('student')
        academic_year = cleaned.get('academic_year')
        classification = cleaned.get('classification')
        section = cleaned.get('section')
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        status = cleaned.get('status')
        if section and classification and section.classification_id != classification.pk:
            self.add_error('section', "Section must belong to the selected classification.")
        if student and classification and start_date and status == 'active':
            overlaps = StudentCourseEnrollment.objects.filter(
                student=student,
                course=self.course,
                classification=classification,
                section=section,
                status='active',
                start_date__lte=end_date or datetime.date.max,
            ).filter(Q(end_date__isnull=True) | Q(end_date__gte=start_date))
            if academic_year:
                overlaps = overlaps.filter(academic_year=academic_year)
            else:
                overlaps = overlaps.filter(academic_year__isnull=True)
            if self.instance.pk:
                overlaps = overlaps.exclude(pk=self.instance.pk)
            if overlaps.exists():
                raise forms.ValidationError(
                    "This student already has an overlapping active enrollment in this exact course scope."
                )
        return cleaned

    def save(self, commit=True):
        enrollment = super().save(commit=False)
        enrollment.org = self.org
        enrollment.course = self.course
        enrollment.branch = enrollment.student.branch or self.course.branch
        if commit:
            enrollment.save()
            self.save_m2m()
        return enrollment


class RoutineAssignmentChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, assignment):
        teacher_name = (
            assignment.teacher.get_full_name()
            or assignment.teacher.email
            or assignment.teacher.username
        )
        subject = assignment.subject
        scope = subject.classification.name
        if assignment.section_id:
            scope = f"{scope} / {assignment.section.name}"
        else:
            scope = f"{scope} / All sections"
        course = f"{subject.course.name} / " if subject.course_id else ""
        year = f" · {assignment.academic_year.name}" if assignment.academic_year_id else ""
        return f"{teacher_name} → {course}{scope} → {subject.name}{year}"


class RoutinePeriodForm(forms.ModelForm):
    teacher_assignment = RoutineAssignmentChoiceField(
        queryset=SubjectTeacherAssignment.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Assigned Teacher / Subject',
        help_text='The class, section, subject, and teacher come from this assignment.',
    )

    class Meta:
        model = RoutinePeriod
        fields = (
            'teacher_assignment',
            'day_of_week', 'period_number', 'start_time', 'end_time', 'room', 'shift', 'is_active',
        )
        widgets = {
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'period_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'room': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
            'shift': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        self._org = org
        if org:
            today = datetime.date.today()
            assignment_qs = SubjectTeacherAssignment.objects.filter(
                org=org,
                status='active',
                subject__status='active',
                start_date__lte=today,
            ).filter(
                Q(end_date__isnull=True) | Q(end_date__gte=today)
            ).select_related(
                'teacher',
                'academic_year',
                'course',
                'classification',
                'section',
                'subject',
            ).order_by(
                'subject__classification__name',
                'subject__section__name',
                'subject__name',
                'teacher__first_name',
                'teacher__last_name',
            )
            if self.instance.pk and self.instance.teacher_assignment_id:
                assignment_qs = SubjectTeacherAssignment.objects.filter(
                    Q(pk=self.instance.teacher_assignment_id) | Q(pk__in=assignment_qs),
                    org=org,
                ).select_related(
                    'teacher',
                    'academic_year',
                    'course',
                    'classification',
                    'section',
                    'subject',
                ).distinct()
            self.fields['teacher_assignment'].queryset = assignment_qs
        self.fields['room'].required = False
        self.fields['is_active'].required = False

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_time'), cleaned.get('end_time')
        if start and end and start >= end:
            raise forms.ValidationError("End time must be after start time.")
        teacher_assignment = cleaned.get('teacher_assignment')
        if not teacher_assignment:
            return cleaned
        if self._org and teacher_assignment.org_id != self._org.pk:
            raise forms.ValidationError("Select a subject assignment from this organization.")

        subject = teacher_assignment.subject
        teacher = teacher_assignment.teacher
        classification = teacher_assignment.classification
        section = teacher_assignment.section
        self.instance.teacher_assignment = teacher_assignment
        self.instance.subject = subject
        self.instance.teacher = teacher
        self.instance.classification = classification
        self.instance.section = section
        self.instance.academic_year = teacher_assignment.academic_year
        self.instance.branch = (
            teacher_assignment.branch
            or getattr(subject.course, 'branch', None)
            or classification.primary_branch
        )

        day, room = cleaned.get('day_of_week'), cleaned.get('room')
        period_number = cleaned.get('period_number')
        if (
            self._org
            and cleaned.get('is_active')
            and day is not None
            and period_number
        ):
            duplicate_slot = RoutinePeriod.objects.filter(
                org=self._org,
                day_of_week=day,
                period_number=period_number,
                classification=classification,
                is_active=True,
            )
            if section:
                duplicate_slot = duplicate_slot.filter(section=section)
            else:
                duplicate_slot = duplicate_slot.filter(section__isnull=True)
            if self.instance.pk:
                duplicate_slot = duplicate_slot.exclude(pk=self.instance.pk)
            if duplicate_slot.exists():
                raise forms.ValidationError(
                    "This class/section already has a routine for that day and period number."
                )
        if self._org and teacher and classification and start and end and day is not None:
            from handle.academics import check_routine_conflict
            conflicts = check_routine_conflict(
                self._org, teacher=teacher, section=section, room=room,
                day_of_week=day, start_time=start, end_time=end,
                classification=classification, exclude_pk=self.instance.pk,
            )
            if conflicts:
                raise forms.ValidationError(conflicts)
        return cleaned


# =============================================================
# SUPPLIER / PURCHASE / SALE
# =============================================================

class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = (
            'branch', 'name', 'supplier_number', 'contact_person', 'phone', 'mobile', 'email', 'website',
            'pan_vat_number', 'registration_number', 'address', 'country', 'province', 'district', 'municipality',
            'bank_name', 'bank_account_number', 'bank_branch', 'payment_terms', 'credit_limit', 'opening_balance',
            'notes', 'status',
        )
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company name'}),
            'supplier_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier code'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person'}),
            'phone': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}),
            'mobile': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Mobile'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'website': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Website'}),
            'pan_vat_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PAN/VAT number'}),
            'registration_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Registration number'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'country': forms.TextInput(attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control'}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'municipality': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank name'}),
            'bank_account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account number'}),
            'bank_branch': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bank branch'}),
            'payment_terms': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Net 30'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'opening_balance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        for field in (
            'branch', 'supplier_number', 'contact_person', 'phone', 'mobile', 'email', 'website',
            'pan_vat_number', 'registration_number', 'address', 'province', 'district', 'municipality',
            'bank_name', 'bank_account_number', 'bank_branch', 'payment_terms', 'notes',
        ):
            self.fields[field].required = False


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = (
            'branch', 'supplier', 'purchase_date', 'due_date', 'invoice_number',
            'payment_method', 'discount_amount', 'tax_amount', 'notes', 'attachment',
        )
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier invoice #'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'discount_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'attachment': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['supplier'].queryset = Supplier.objects.filter(org=org, status='active')
        self.fields['branch'].required = False
        self.fields['invoice_number'].required = False
        self.fields['notes'].required = False
        self.fields['tax_amount'].required = False
        self.fields['discount_amount'].required = False

    def clean_tax_amount(self):
        tax_amount = self.cleaned_data.get('tax_amount')
        if tax_amount is None:
            return 0
        if tax_amount < 0:
            raise forms.ValidationError('Tax amount cannot be negative.')
        return tax_amount


class BasePurchaseItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        valid_lines = 0
        for form in self.forms:
            data = getattr(form, 'cleaned_data', {})
            if not data or data.get('DELETE'):
                continue
            stock_item = data.get('stock_item')
            description = (data.get('description') or '').strip()
            quantity = data.get('quantity')
            unit_cost = data.get('unit_cost')
            if not stock_item and not description:
                continue
            valid_lines += 1
            if quantity is None or quantity <= 0:
                form.add_error('quantity', 'Quantity must be greater than zero.')
            if unit_cost is None or unit_cost < 0:
                form.add_error('unit_cost', 'Unit cost cannot be negative.')
        if not valid_lines:
            raise forms.ValidationError('Add at least one stock item or description line.')


PurchaseItemFormSet = forms.inlineformset_factory(
    Purchase, PurchaseItem,
    formset=BasePurchaseItemFormSet,
    fields=('stock_item', 'description', 'quantity', 'unit_cost'),
    widgets={
        'stock_item': forms.Select(attrs={'class': 'form-select stock-item-select'}),
        'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional (non-stock line)'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    },
    extra=1, min_num=1, validate_min=True, can_delete=True,
)


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = ('branch', 'client', 'customer_name', 'sale_date', 'invoice_number',
                  'payment_status', 'payment_method', 'tax_amount', 'notes')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'client': forms.Select(attrs={'class': 'form-select'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Walk-in customer name (if no client)'}),
            'sale_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Invoice #'}),
            'payment_status': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'tax_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            # Inquiries remain available in CRM, but cannot be selected for a
            # confirmed stock sale until explicitly converted to a customer.
            self.fields['client'].queryset = Client.objects.filter(
                org=org, is_active=True, status='customer',
            )
        self.fields['branch'].required = False
        self.fields['client'].required = False
        self.fields['customer_name'].required = False
        self.fields['invoice_number'].required = False
        self.fields['notes'].required = False


SaleItemFormSet = forms.inlineformset_factory(
    Sale, SaleItem,
    fields=('stock_item', 'quantity', 'unit_price'),
    widgets={
        'stock_item': forms.Select(attrs={'class': 'form-select stock-item-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    },
    extra=1, min_num=1, validate_min=True, can_delete=True,
)


def clean_sale_item_formset_stock(formset):
    """Validates each line's requested quantity against current on-hand
    stock, mirroring StockMovementForm.clean()'s stock-out guard. Called
    explicitly by the view after formset.is_valid() since cross-form
    (item vs quantity) validation isn't expressible in a single form's clean()."""
    errors = []
    for form in formset.forms:
        if not form.cleaned_data or form.cleaned_data.get('DELETE'):
            continue
        item = form.cleaned_data.get('stock_item')
        qty = form.cleaned_data.get('quantity')
        if item and qty and qty > item.quantity:
            errors.append(f"Only {item.quantity} {item.unit} of '{item.name}' available, but {qty} was requested.")
    return errors


class SupplierDocumentForm(forms.ModelForm):
    class Meta:
        model = SupplierDocument
        fields = ('title', 'doc_type', 'file')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Document title'}),
            'doc_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Contract, PAN Certificate'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['doc_type'].required = False


class SupplierPaymentForm(forms.ModelForm):
    class Meta:
        model = SupplierPayment
        fields = ('branch', 'purchase', 'amount', 'payment_date', 'payment_method', 'reference_number', 'note')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'purchase': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reference #'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        supplier = kwargs.pop('supplier', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        if supplier:
            self.fields['purchase'].queryset = Purchase.objects.filter(
                supplier=supplier,
            ).exclude(status='cancelled').order_by('-purchase_date')
        else:
            self.fields['purchase'].queryset = Purchase.objects.none()
        self.fields['branch'].required = False
        self.fields['purchase'].required = False
        self.fields['purchase'].empty_label = "— General payment (not tied to one bill) —"
        self.fields['reference_number'].required = False
        self.fields['note'].required = False


class PurchaseReturnForm(forms.ModelForm):
    class Meta:
        model = PurchaseReturn
        fields = ('branch', 'return_date', 'reason')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'return_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reason for return'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branch'].required = False
        self.fields['reason'].required = False


PurchaseReturnItemFormSet = forms.inlineformset_factory(
    PurchaseReturn, PurchaseReturnItem,
    fields=('stock_item', 'quantity', 'unit_cost'),
    widgets={
        'stock_item': forms.Select(attrs={'class': 'form-select stock-item-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    },
    extra=1, min_num=1, validate_min=True, can_delete=True,
)


class SalePaymentForm(forms.ModelForm):
    class Meta:
        model = SalePayment
        fields = ('branch', 'amount', 'payment_date', 'payment_method', 'reference_number', 'note')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reference #'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branch'].required = False
        self.fields['reference_number'].required = False
        self.fields['note'].required = False


class SalesReturnForm(forms.ModelForm):
    class Meta:
        model = SalesReturn
        fields = ('branch', 'return_date', 'reason')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'return_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reason': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reason for return'}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branch'].required = False
        self.fields['reason'].required = False


SalesReturnItemFormSet = forms.inlineformset_factory(
    SalesReturn, SalesReturnItem,
    fields=('stock_item', 'quantity', 'unit_price'),
    widgets={
        'stock_item': forms.Select(attrs={'class': 'form-select stock-item-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    },
    extra=1, min_num=1, validate_min=True, can_delete=True,
)


class AssetPurchaseForm(forms.ModelForm):
    class Meta:
        model = AssetPurchase
        fields = ('branch', 'name', 'category', 'cost', 'purchase_date', 'payment_method', 'vendor', 'notes')
        widgets = {
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Asset name'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Furniture, Equipment'}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'vendor': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super().__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['vendor'].queryset = Supplier.objects.filter(org=org, status='active')
        self.fields['branch'].required = False
        self.fields['category'].required = False
        self.fields['vendor'].required = False
        self.fields['notes'].required = False


from django.contrib.auth.forms import PasswordChangeForm

class FormChangePassword(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super(FormChangePassword, self).__init__(*args, **kwargs)
        for field in ('old_password', 'new_password1', 'new_password2'):
            self.fields['old_password'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"Old Password"}
            self.fields['new_password1'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"New Password"}
            self.fields['new_password2'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"Re New Password"}
