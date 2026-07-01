
from django import forms
from django.contrib import messages
from django.http.response import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render, redirect
from django.views.generic import TemplateView
from django.views import View
from django.contrib.auth import authenticate, login, logout
import nepali_datetime
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



def account_deletion_view(request):
    """
    Public-facing view required by Google Play Store for account deletion instructions.
    """
    return render(request, 'basic/deletion.html')

def password_reset_request(request):
    password_reset_form = PasswordResetForm()
    if request.method == "POST":
        password_reset_form = PasswordResetForm(request.POST)
        if password_reset_form.is_valid():
            data = password_reset_form.cleaned_data['email']
            associated_users = CustomUser.objects.filter(Q(email=data))
            print(associated_users)

        if associated_users.exists():
            for user in associated_users:
                subject = "Password Reset Requested"
                email_template_name = "password/password_reset_email.txt"
                c = {
                    "email": user.email,
                    'domain': 'meroattendance.com',
                    'site_name': 'Mero Attendance',
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "user": user,
                    'token': default_token_generator.make_token(user),
                    'protocol': 'https',
                }
                
                html_email = render_to_string("password/password_reset_email.html", c)
                
                # # 2. Create a basic plain-text fallback (for very old email apps)
                text_fallback = f"Please click this link to reset your password: https://meroattendance.com/reset/{c['uid']}/{c['token']}/"
                try:
                    send_mail(subject, message=text_fallback, html_message=html_email, from_email=settings.EMAIL_HOST_USER, recipient_list=[user.email], fail_silently=False)
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
            from management.models import BlogPost as _BlogPost
            blog_posts = _BlogPost.objects.filter(published=True).order_by('-created_at')[:3]
            return render(request, self.template_name, {'form': form, 'blog_posts': blog_posts})


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
    template_name = "basic/leaveReport.html" # वा तपाईंको फाइलको बाटो
    
    def get(self, request, *args, **kwargs):
        mem = member.objects.get(id=self.kwargs['id'])
        form = LeaveForm()
        
        # 🔥 नेपाली मिति अन छ कि छैन
        nepali_enabled = getattr(mem.org, 'nepali_date', False)
        
        context = {
            'form': form, 
            'mem': mem,
            'nepali_enabled': nepali_enabled
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        form = LeaveForm(request.POST)
        memb = member.objects.get(id=self.kwargs['id'])
        organization = memb.org
        nepali_enabled = getattr(organization, 'nepali_date', False)
        
        try:
            if form.is_valid():
                leave_report = form.save(commit=False)
                leave_report.org = organization
                leave_report.member = memb
                
                # HTML बाट आएका मितिहरू तान्ने
                start_date_str = request.POST.get('gap_start', '')
                end_date_str = request.POST.get('gap_end', '')
                start_date_np_str = request.POST.get('gap_start_np', '')
                end_date_np_str = request.POST.get('gap_end_np', '')

                # 🔥 १. Start Date (Gap Start) Parsing
                if nepali_enabled and start_date_np_str:
                    try:
                        y, m, d = map(int, start_date_np_str.replace('/', '-').strip().split('-'))
                        leave_report.gap_start = nepali_datetime.date(y, m, d).to_datetime_date()
                    except Exception:
                        leave_report.gap_start = start_date_str # Fallback
                else:
                    leave_report.gap_start = start_date_str
                
                # 🔥 २. End Date (Gap End) Parsing (यदि छ भने मात्र)
                holiday_type = request.POST.get('holidayType')
                if holiday_type == 'gap':
                    if nepali_enabled and end_date_np_str:
                        try:
                            y, m, d = map(int, end_date_np_str.replace('/', '-').strip().split('-'))
                            leave_report.gap_end = nepali_datetime.date(y, m, d).to_datetime_date()
                        except Exception:
                            leave_report.gap_end = end_date_str if end_date_str else None
                    else:
                        leave_report.gap_end = end_date_str if end_date_str else None
                else:
                    leave_report.gap_end = None # 1-day leave को लागि end date हुँदैन

                leave_report.save()
                messages.success(request, "Successfully Sent your Leave Request")
                return HttpResponseRedirect(reverse('management:completeLeave')) # Adjust URL name if needed
            else:
                messages.error(request, "Something went wrong with the form submission. Please check your inputs.")
        
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")
        
        return HttpResponseRedirect(reverse('management:leaveReport', args=(memb.id,)))


# ── Public Appointment Booking ────────────────────────────────────────────────
import datetime as _dt
from management.models import AppointmentType, Appointment, CustomForm, FormField, FormSubmission, FieldResponse
from django.shortcuts import get_object_or_404


def public_book(request, org_key):
    from management.models import Organization
    org = get_object_or_404(Organization, serial_key=org_key)
    types = AppointmentType.objects.filter(org=org, is_active=True)
    booked = False
    error = None

    if request.method == 'POST':
        apt_type_pk = request.POST.get('appointment_type')
        apt_type = AppointmentType.objects.filter(pk=apt_type_pk, org=org).first() if apt_type_pk else None
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        date_str = request.POST.get('date', '')
        time_str = request.POST.get('time', '')
        message = request.POST.get('message', '')
        try:
            date = _dt.date.fromisoformat(date_str)
            time = _dt.time.fromisoformat(time_str)
            if not name or not email:
                error = 'Name and email are required.'
            else:
                Appointment.objects.create(
                    org=org, appointment_type=apt_type,
                    name=name, email=email, phone=phone,
                    date=date, time=time, message=message,
                )
                booked = True
        except Exception:
            error = 'Invalid date or time. Please check your input.'

    return render(request, 'public/book_appointment.html', {
        'org': org, 'types': types, 'booked': booked, 'error': error,
        'today': _dt.date.today().isoformat(),
    })


# ── Public Form ───────────────────────────────────────────────────────────────

def public_form(request, form_uuid):
    form_obj = get_object_or_404(CustomForm, uuid=form_uuid, is_active=True)
    submitted = False
    errors = {}

    if request.method == 'POST':
        submission = FormSubmission(form=form_obj)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            submission.ip_address = x_forwarded_for.split(',')[0]
        else:
            submission.ip_address = request.META.get('REMOTE_ADDR')
        submission.save()

        for field in form_obj.fields.all():
            val = request.POST.get(f'field_{field.pk}', '')
            if field.required and not val:
                errors[field.pk] = 'This field is required.'
            FieldResponse.objects.create(submission=submission, field_label=field.label, value=val)

        if errors:
            submission.delete()
        else:
            submitted = True

    return render(request, 'public/public_form.html', {
        'form_obj': form_obj, 'submitted': submitted,
        'errors': errors,
        'error_pks': set(errors.keys()),
    })


# ── Blog ─────────────────────────────────────────────────────────────────────

from management.models import BlogPost


class BlogListView(TemplateView):
    template_name = 'basic/blog_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['posts'] = BlogPost.objects.filter(published=True).order_by('-created_at')
        return ctx


class BlogDetailView(TemplateView):
    template_name = 'basic/blog_detail.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['post'] = get_object_or_404(BlogPost, slug=kwargs['slug'], published=True)
        ctx['recent'] = BlogPost.objects.filter(published=True).exclude(slug=kwargs['slug'])[:4]
        return ctx