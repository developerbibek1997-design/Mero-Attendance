
from django import forms
from django.contrib import messages
from django.http.response import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.views import View
from django.contrib.auth import authenticate, login, logout
from .models import Organization, Pricing
from .forms import ContactForm, LeaveForm, SignForm
from handle.models import member, CustomUser
from django.db.models import Q
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.forms import PasswordResetForm
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.conf import settings
from django.core.mail import send_mail, BadHeaderError
from django.http import HttpResponse
from django.conf import settings
from django.template.loader import render_to_string

def password_reset_request(request):
    password_reset_form = PasswordResetForm()
    if request.method == "POST":
        password_reset_form = PasswordResetForm(request.POST)
        if password_reset_form.is_valid():
            data = password_reset_form.cleaned_data['email']
            associated_users = CustomUser.objects.filter(Q(email=data))

        if associated_users.exists():
            for user in associated_users:
                subject = "Password Reset Requested"
                email_template_name = "password/password_reset_email.txt"
                c = {
                "email":user.email,
                'domain':'meroattendance.com',
                'site_name': 'Website',
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "user": user,
                'token': default_token_generator.make_token(user),
                'protocol': 'https',
                }
                
                email = render_to_string(email_template_name, c)
                try:
                    send_mail(subject, email, settings.EMAIL_HOST_USER , [user.email], fail_silently=False)
                except BadHeaderError:
                    return HttpResponse('Invalid header found.')
                return redirect ("/password_reset/done/")

    return render(request=request, template_name="password/password_reset.html", context={"password_reset_form":password_reset_form})

def askVerify(request): 
    if request.method == "POST":
        code = request.POST['code']

        try:
            if '@' in code:
                mem = member.objects.get(email =code)
            else:
                mem = member.objects.get(phone = code)

            
            return HttpResponseRedirect(reverse("management:leaveReport", args=[mem.id]))
        except member.DoesNotExist:
            if "@" in code:
                ca = "email"
            else:
                ca ="number"
        
            messages.error(request, f"We couln't find a member with this {ca}")

    return render(request, "basic/askSerial.html")


# Create your views here.
class Homepage(TemplateView):
    template_name = 'basic/index.html'
    
    def get(self, request, *agrs, **kwargs):
        form = SignForm()
        if request.user.is_authenticated:
            if request.user.user_type == '1':
                return HttpResponseRedirect(reverse('superadmin:dashboard'))
            elif request.user.user_type == '2':
                return HttpResponseRedirect(reverse('schooladmin:dashboard'))
            else:
                return HttpResponseRedirect(reverse('staff:dashboard'))
        else:
            return render(request, self.template_name, {'form':form})


    def post(self,request, *args, **kwargs):
            email = request.POST['email']
            password = request.POST['password']
            user = authenticate(request, username=email, password=password)
            if user != None:
                login(request, user)
                if user.user_type == '1':
                    return HttpResponseRedirect(reverse('superadmin:dashboard'))
                elif user.user_type == '2':
                    return HttpResponseRedirect(reverse('schooladmin:dashboard'))
                else:
                    return HttpResponseRedirect(reverse('staff:dashboard'))
            else:
                
                form = SignForm()
                form.fields['email'].initial = email
                messages.error(request, 'Email or Password Doesnot match')
                return render(request, self.template_name, {'form':form})
        


class Documentation(TemplateView):
    template_name = 'basic/documentation.html'


class PricingView(TemplateView):
    template_name = 'basic/pricing.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pricing_list'] = Pricing.objects.all()  # Fetch all pricing data
        return context

def completeLeave(request):
    return render(request, "basic/complete.html")

def Contact(request):
   
    form = ContactForm(request.POST or None)

    dist={
        'form':form,
        
    }
    if request.method == "POST":
        if form.is_valid():
            form.save()
    
            messages.success(request, "Successfully sent message")
            return HttpResponseRedirect(reverse('management:contact'))

        else:
            messages.error(request, "Something went wrong "+ form.errors.as_text())
            print(form.errors.as_text)

    return render(request, "basic/contact.html", dist)



class About(TemplateView):
    template_name = 'basic/about.html'


class Privacy(TemplateView):
    template_name = 'basic/privacy.html'



class Terms(TemplateView):
    template_name = 'basic/terms.html'



class Pullar(TemplateView):
    template_name = 'basic/pullar.html'

def logoutUser(request):
    logout(request)
    return HttpResponseRedirect(reverse('management:homepage'))



class LeaveReportView(View):
    template_name = "basic/leaveReport.html"
    
    def get(self, request, *args, **kwargs):
        mem = member.objects.get(id=self.kwargs['id'])
      
        form = LeaveForm()
        return render(request, self.template_name, {'form': form, 'mem': mem})
    
    def post(self, request, *args, **kwargs):
        form = LeaveForm(request.POST)
       
        try:
            
            memb = member.objects.get(id=self.kwargs['id'])
            organization = memb.org
            
            if form.is_valid():
                leave_report = form.save(commit=False)
                leave_report.org = organization
                leave_report.gap_start = request.POST['gap_start']
                if request.POST['gap_end']:
                    leave_report.gap_end = request.POST['gap_end']
                
                leave_report.member = memb
                leave_report.save()
                messages.success(request, "Successfully Sent your Leave Request")
                return HttpResponseRedirect(reverse('management:completeLeave'))
            else:
                messages.error(request, "Something went wrong with the form submission")
        
        except Organization.DoesNotExist:
            messages.error(request, "Serial Code does not match any organization")
        
        return HttpResponseRedirect(reverse('management:leaveReport', args=(memb.id,)))
    
                
    