from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django import forms
from management.models import Organization, Schooladmin
from management.models import CustomUser
from handle.models import Staff






class SchooladminForm(forms.ModelForm):
    first_name = forms.CharField(label = 'First Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'First Name'}))
    last_name = forms.CharField(label = 'Last Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'Last Name'}))
    email = forms.EmailField(label = 'Email', max_length = 200, widget = forms.TextInput(attrs={'class':'form-control', 'placeholder' : 'Email'}))
    password = forms.CharField(label = 'Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Password'}))
    re_password = forms.CharField(label = 'Repeat Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Repeat Password'}))
    class Meta:
       model = Schooladmin 
       fields = ('first_name', 'last_name','email', 'number','password','re_password','org')
       labels = {
           'number' :'Phone Number',
           'org':'Organization'
           
       }
       widgets = {
        'org': forms.Select(attrs={'class':'form-control', 'placeholder' : 'Organization'}),
        'number': forms.NumberInput(attrs={'class':'form-control', 'placeholder' : 'Your Phone Number'}),
   }
       
    def clean_email(self):
        email = self.cleaned_data['email']
        try:
            match = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Unable to find a user, this is fine
            return email
        # A user was found with this as a username, raise an error.
        raise forms.ValidationError('This email address is already in use.')
    def clean_number(self):
        data = self.cleaned_data['number']
        d = str(data)
        if len(d) > 10 or len(d) < 10 :
            raise ValidationError("Number can not be less or more than 10 digits")
        if not d.startswith('98' or '97'):
            raise ValidationError("Nepali number should start with 98")
        return data
    def clean_password(self):
        data = self.cleaned_data['password']
        d = str(data)
        if len(d) < 6:
            raise ValidationError("Password must be greater than 6 digits")
        return data
    def clean_re_password(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('re_password')
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError('Password Did not Match')
        return password2
    

class StaffadminForm(forms.ModelForm):
    first_name = forms.CharField(label = 'First Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'First Name'}))
    last_name = forms.CharField(label = 'Last Name', widget = forms.TextInput(attrs={'class':'form-control', 'placeholder':'Last Name'}))
    email = forms.EmailField(label = 'Email', max_length = 200, widget = forms.TextInput(attrs={'class':'form-control', 'placeholder' : 'Email'}))
    password = forms.CharField(label = 'Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Password'}))
    re_password = forms.CharField(label = 'Repeat Password', widget = forms.PasswordInput(attrs={'class':'form-control', 'placeholder':'Repeat Password'}))
    class Meta:
       model = Staff 
       fields = ('first_name', 'last_name','email', 'number','password','re_password','org')
       labels = {
           'number' :'Phone Number',
           'org':'Organization'
           
       }
       widgets = {
        'org': forms.Select(attrs={'class':'form-control', 'placeholder' : 'Organization'}),
        'number': forms.NumberInput(attrs={'class':'form-control', 'placeholder' : 'Your Phone Number'}),
   }
       
    def clean_email(self):
        email = self.cleaned_data['email']
        try:
            match = CustomUser.objects.get(email=email)
        except CustomUser.DoesNotExist:
            # Unable to find a user, this is fine
            return email
        # A user was found with this as a username, raise an error.
        raise forms.ValidationError('This email address is already in use.')
    def clean_number(self):
        data = self.cleaned_data['number']
        d = str(data)
        if len(d) > 10 or len(d) < 10 :
            raise ValidationError("Number can not be less or more than 10 digits")
        if not d.startswith('98' or '97'):
            raise ValidationError("Nepali number should start with 98")
        return data
    def clean_password(self):
        data = self.cleaned_data['password']
        d = str(data)
        if len(d) < 6:
            raise ValidationError("Password must be greater than 6 digits")
        return data
    def clean_re_password(self):
        password1 = self.cleaned_data.get('password')
        password2 = self.cleaned_data.get('re_password')
        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError('Password Did not Match')
        return password2

class OrgForm(ModelForm):
    class Meta:
        model = Organization
        fields = (
            'name', 'category', 'expire_on', 'address', 'member_limit',
            'mutifeature_enable', 'location_based', 'qr_based', 'rfid_based',
            'manual_attendance', 'auto_checkin', 'serial_key', 'new_serial_key',
            'activate', 'nepali_date', 'free_demo', 'course_based_attendance',
            # Module feature flags
            'feature_finance', 'feature_billing', 'feature_stock', 'feature_tasks',
            'feature_results', 'feature_hrms', 'feature_payroll', 'feature_complaints',
            'feature_events', 'feature_branches', 'feature_leave',
            # Extended feature flags
            'feature_study_gap', 'feature_bulk_export', 'feature_notifications',
            'feature_courses', 'feature_student_mgmt', 'feature_member_mgmt',
        )

        labels = {
            'name': "Name",
            'category': "Organization Type",
            'expire_on': "Date of Expire",
            'mutifeature_enable': 'Allow staff to do attendance without device',
            'serial_key': "Organization Key",
            'new_serial_key': 'Activation Number',
            'member_limit': 'Member Limitation',
            'activate': 'Activated',
            'location_based': 'Location Based Attendance',
            'qr_based': 'QR Based Attendance',
            'rfid_based': 'RFID Based Attendance',
            'manual_attendance': 'Manual Attendance',
            'auto_checkin': 'Auto Checkin',
            'nepali_date': 'Use Nepali Date (BS)',
            'free_demo': 'Free Demo Account',
            'course_based_attendance': 'Course Based Attendance Logic',
            # Module labels
            'feature_finance': 'Finance — Income & Expense',
            'feature_billing': 'Billing — Student Invoices',
            'feature_stock': 'Stock Management',
            'feature_tasks': 'Task Management',
            'feature_results': 'Results & Exams',
            'feature_hrms': 'HR Module — Resignation, Documents',
            'feature_payroll': 'Payroll & Payslips',
            'feature_complaints': 'Complaints',
            'feature_events': 'Events',
            'feature_branches': 'Branch Management',
            'feature_leave': 'Leave Management',
            # Extended labels
            'feature_study_gap': 'Study Gap / Teaching Log',
            'feature_bulk_export': 'Bulk Data Export',
            'feature_notifications': 'Notifications / SMS Alerts',
            'feature_courses': 'Course Management',
            'feature_student_mgmt': 'Student Management',
            'feature_member_mgmt': 'Member / Staff Management',
        }

        _cb = {'class': 'form-check-input'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Organization Name'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'member_limit': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 100'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Address'}),
            'serial_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Serial Key'}),
            'expire_on': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'new_serial_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Activation Key'}),
            'activate': forms.CheckboxInput(attrs=_cb),
            'mutifeature_enable': forms.CheckboxInput(attrs=_cb),
            'location_based': forms.CheckboxInput(attrs=_cb),
            'qr_based': forms.CheckboxInput(attrs=_cb),
            'rfid_based': forms.CheckboxInput(attrs=_cb),
            'manual_attendance': forms.CheckboxInput(attrs=_cb),
            'auto_checkin': forms.CheckboxInput(attrs=_cb),
            'nepali_date': forms.CheckboxInput(attrs=_cb),
            'free_demo': forms.CheckboxInput(attrs=_cb),
            'course_based_attendance': forms.CheckboxInput(attrs=_cb),
            'feature_finance': forms.CheckboxInput(attrs=_cb),
            'feature_billing': forms.CheckboxInput(attrs=_cb),
            'feature_stock': forms.CheckboxInput(attrs=_cb),
            'feature_tasks': forms.CheckboxInput(attrs=_cb),
            'feature_results': forms.CheckboxInput(attrs=_cb),
            'feature_hrms': forms.CheckboxInput(attrs=_cb),
            'feature_payroll': forms.CheckboxInput(attrs=_cb),
            'feature_complaints': forms.CheckboxInput(attrs=_cb),
            'feature_events': forms.CheckboxInput(attrs=_cb),
            'feature_branches': forms.CheckboxInput(attrs=_cb),
            'feature_leave': forms.CheckboxInput(attrs=_cb),
            'feature_study_gap': forms.CheckboxInput(attrs=_cb),
            'feature_bulk_export': forms.CheckboxInput(attrs=_cb),
            'feature_notifications': forms.CheckboxInput(attrs=_cb),
            'feature_courses': forms.CheckboxInput(attrs=_cb),
            'feature_student_mgmt': forms.CheckboxInput(attrs=_cb),
            'feature_member_mgmt': forms.CheckboxInput(attrs=_cb),
        }