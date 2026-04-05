from django import forms
from django.forms import ModelForm
from .models import LeaveReport, ContactUs

class SignForm(forms.Form):
    email = forms.EmailField(label = 'Email', max_length = 200, widget = forms.TextInput(attrs={'class':'form-control m-2', 'placeholder' : 'Email/Username'}))
    password = forms.CharField(label = 'Password', widget = forms.PasswordInput(attrs={'class':'form-control m-2', 'placeholder':'Password'} ))

class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveReport
        fields = ('reason',)
        
        labels = {

            'reason': 'Reason for Leave'
        }
        
        widgets = {
          
            'reason': forms.Textarea(attrs={'class': 'form-control mb-3 mt-3', 'placeholder': 'Reason for Leave'}),
        }



class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactUs
        fields = ("__all__")
       

        widgets ={
            'fullname':forms.TextInput(attrs={'class':'form-control mt-2 create-icon' , 'placeholder':'Your Full Name'}),
            'email':forms.TextInput(attrs={'class':'form-control mt-2 create-icon' , 'placeholder':'Your email address'}),
            'number':forms.NumberInput(attrs={'class':'form-control mt-2 create-icon', 'placeholder':'Phone Number'}),
            
            'message':forms.Textarea(attrs={'class':'form-control mt-2 create-icon', 'placeholder':'Write your message', 'style':'height:80px;'}),
        

        }
