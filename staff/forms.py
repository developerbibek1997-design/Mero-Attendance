from django import forms

from handle.models import member


class PortalProfileForm(forms.ModelForm):
    """Safe self-service fields shared by staff, teachers, and students."""

    class Meta:
        model = member
        fields = (
            "name",
            "gender",
            "phone",
            "address",
            "date_of_birth",
            "blood_group",
            "photo",
            "guardian_name",
            "guardian_phone",
            "guardian_email",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Full name"}
            ),
            "gender": forms.Select(attrs={"class": "form-select"}),
            "phone": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Mobile number"}
            ),
            "address": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Current address"}
            ),
            "date_of_birth": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "form-control", "type": "date"},
            ),
            "blood_group": forms.Select(attrs={"class": "form-select"}),
            "photo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "guardian_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Guardian name"}
            ),
            "guardian_phone": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Guardian phone"}
            ),
            "guardian_email": forms.EmailInput(
                attrs={"class": "form-control", "placeholder": "Guardian email"}
            ),
        }

    def __init__(self, *args, portal_role="staff", **kwargs):
        super().__init__(*args, **kwargs)
        self.portal_role = portal_role
        self.fields["photo"].required = False
        if portal_role != "student":
            for field_name in (
                "guardian_name",
                "guardian_phone",
                "guardian_email",
            ):
                self.fields.pop(field_name, None)

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Full name is required.")
        return name
