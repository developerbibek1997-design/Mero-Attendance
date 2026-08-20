from django import forms
from django.core.exceptions import ValidationError
from management.models import AgentProfile, Organization, CustomUser


class AgentProfileForm(forms.ModelForm):
    class Meta:
        model = AgentProfile
        fields = [
            'full_name', 'phone', 'address', 'photo',
            'company_name', 'pan_number',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-control'}),
        }


class AgentAddOrgForm(forms.ModelForm):
    admin_first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Admin First Name'})
    )
    admin_last_name = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Admin Last Name'})
    )
    admin_email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Admin Email'})
    )
    admin_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Admin Password'})
    )

    class Meta:
        model = Organization
        fields = [
            'name', 'address', 'category', 'member_limit',
            'expire_on', 'serial_key', 'image',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'member_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'expire_on': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'serial_key': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_admin_email(self):
        email = self.cleaned_data['admin_email']
        if CustomUser.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email


class AgentEditOrgForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = [
            'name', 'address', 'category', 'member_limit',
            'expire_on', 'activate', 'image',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'member_limit': forms.NumberInput(attrs={'class': 'form-control'}),
            'expire_on': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'activate': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class SuperAdminAgentForm(forms.ModelForm):
    first_name = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    class Meta:
        model = AgentProfile
        fields = [
            'full_name', 'phone', 'address', 'company_name', 'pan_number',
            'commission_type', 'commission_value', 'max_organizations_allowed',
            'allowed_to_create_org', 'allowed_to_manage_billing',
            'allowed_to_manage_features', 'allowed_to_view_reports',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-control'}),
            'commission_type': forms.Select(attrs={'class': 'form-control'}),
            'commission_value': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_organizations_allowed': forms.NumberInput(attrs={'class': 'form-control'}),
            'allowed_to_create_org': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allowed_to_manage_billing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allowed_to_manage_features': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'allowed_to_view_reports': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data['email']
        if CustomUser.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email
