from django import forms
from django.db.models import Q
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
            'card', 'gender', 'email', 'phone', 'date_of_birth', 'address',
            'salary_type', 'salary_amount', 'tax_percentage', 'staff_type',
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
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'shift_start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'shift_end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            
            # Payroll configurations
            'salary_type': forms.Select(attrs={'class': 'form-select'}),
            'salary_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
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
        super(MemberForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
            self.fields['classification'].queryset = Classification.objects.filter(org=org, status='active')
            self.fields['section'].queryset = Section.objects.filter(org=org, status='active')
            self.fields['courses'].queryset = Course.objects.filter(org=org, status='active')
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

    def clean_card(self):
        card = self.cleaned_data.get('card')
        if not card:
            return None  # empty string → NULL, avoids unique constraint on blank cards
        if member.objects.filter(card=card).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This card is already in use.')
        return card


class ClassificationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        org = kwargs.pop('org', None)
        super(ClassificationForm, self).__init__(*args, **kwargs)
        if org:
            self.fields['branch'].queryset = Branch.objects.filter(org=org, status='active')
        self.fields['branch'].required = False

    class Meta:
        model = Classification
        fields = ('name', 'branch', 'status')
        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Classification / Department / Class'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ('name', 'code', 'address', 'phone', 'email', 'manager', 'status')
        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class': 'form-control', 'placeholder': 'Branch name'}),
            'code': forms.TextInput(attrs={'required': True, 'class': 'form-control', 'placeholder': 'Branch code'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'}),
            'manager': forms.Select(attrs={'class': 'form-select'}),
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
            'probation_reminder_days'
        )
        widgets = {
            'pf_employee_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'pf_employer_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ssf_employee_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ssf_employer_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'probation_salary_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'probation_leave_cut_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'probation_reminder_days': forms.NumberInput(attrs={'class': 'form-control'}),
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
        fields =('name','ip_address', 'port_no')
        widgets = {
            'name': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Name of the Device'}),
            'ip_address': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Ip Address'}),
            'port_no': forms.TextInput(attrs={'required': True, 'class':'form-control', 'placeholder':'Port No.'})
        }


from django.contrib.auth.forms import PasswordChangeForm

class FormChangePassword(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super(FormChangePassword, self).__init__(*args, **kwargs)
        for field in ('old_password', 'new_password1', 'new_password2'):
            self.fields['old_password'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"Old Password"}
            self.fields['new_password1'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"New Password"}
            self.fields['new_password2'].widget.attrs = {'class':'form-control ps-0 form-control-line', 'placeholder':"Re New Password"}
