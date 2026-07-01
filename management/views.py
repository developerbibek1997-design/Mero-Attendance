
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


# ── SEO Landing Pages ─────────────────────────────────────────────────────────

# All SEO page content is defined here as a single source of truth.
# Each entry: slug → {title, meta_desc, h1, intro, sections, faqs, cta_label}
SEO_PAGES = {
    'attendance-management-system': {
        'title': 'Attendance Management System | Mero Attendance',
        'meta_desc': 'Automate attendance tracking for your school, office, or institute with Mero Attendance. Biometric, QR, GPS, WiFi, and manual attendance in one platform.',
        'h1': 'Attendance Management System',
        'intro': 'Mero Attendance is a complete attendance management system built for schools, colleges, offices, and institutes in Nepal. Track attendance in real time using biometric devices, QR codes, GPS, WiFi, or manual entry.',
        'sections': [
            {'heading': 'What is an Attendance Management System?', 'body': 'An attendance management system automates the process of recording and monitoring employee, student, or member attendance. It replaces paper registers with digital records that are accurate, tamper-proof, and instantly reportable.'},
            {'heading': 'Key Features', 'body': 'Real-time attendance tracking, biometric device integration, QR code check-in, GPS-based attendance, WiFi auto-check-in, shift management, late detection, leave integration, and automated reports.'},
            {'heading': 'Who Uses It?', 'body': 'Schools, colleges, universities, offices, factories, hospitals, hotels, NGOs, and any organization that needs to track people attendance reliably.'},
            {'heading': 'Why Choose Mero Attendance?', 'body': 'Built for Nepal with Nepali date support, multi-branch management, multi-device support (ZKTeco, Hikvision), and a complete HRMS — all in one affordable SaaS platform.'},
        ],
        'faqs': [
            {'q': 'Does it work offline?', 'a': 'Biometric devices sync data once internet is available. The web dashboard requires internet.'},
            {'q': 'Can I track multiple branches?', 'a': 'Yes. Mero Attendance supports unlimited branches with separate reports per branch.'},
            {'q': 'Is Nepali date (BS) supported?', 'a': 'Yes. You can switch between AD and BS dates across all reports.'},
        ],
        'cta_label': 'Start Free Trial',
    },
    'school-attendance-system': {
        'title': 'School Attendance System Nepal | Mero Attendance',
        'meta_desc': 'Digital school attendance system for Nepal. Track student and teacher attendance, generate class-wise reports, manage leave, and connect with biometric devices.',
        'h1': 'School Attendance System',
        'intro': 'A purpose-built school attendance system that tracks student and teacher attendance, manages leaves, generates class-wise reports, and integrates with biometric devices — all from a single dashboard.',
        'sections': [
            {'heading': 'Student Attendance Made Easy', 'body': 'Mark attendance class-wise or student-wise. Use biometric, QR, or manual entry. Get instant present/absent counts with daily, weekly, and monthly reports.'},
            {'heading': 'Teacher Attendance', 'body': 'Track teacher check-in and check-out times. Monitor late arrival, early departure, and teaching gaps. Generate individual teacher attendance reports.'},
            {'heading': 'Class-wise Reports', 'body': 'Generate attendance reports per class, section, or course. Filter by date range, branch, or classification. Export to Excel or PDF.'},
            {'heading': 'Linked with Student Portal', 'body': 'Students can view their own attendance, apply for leave, and check results — all from a mobile-friendly student dashboard.'},
        ],
        'faqs': [
            {'q': 'Can the system handle multiple classes?', 'a': 'Yes. Create unlimited classifications and sections. Each class has its own attendance report.'},
            {'q': 'Does it support student result management?', 'a': 'Yes. The result module links directly to student records and classification.'},
        ],
        'cta_label': 'Get Started Free',
    },
    'employee-attendance-system': {
        'title': 'Employee Attendance System | Mero Attendance',
        'meta_desc': 'Track employee attendance with biometric, QR, GPS, or WiFi. Generate payroll-linked attendance reports, manage leave, and automate HR workflows.',
        'h1': 'Employee Attendance System',
        'intro': 'Mero Attendance gives HR teams a complete employee attendance system. Track punch-in/out times, detect late arrivals, manage leaves, and automatically link attendance to payroll.',
        'sections': [
            {'heading': 'Payroll Integration', 'body': 'Attendance data flows directly into payroll calculations. Present days, paid leaves, unpaid absences, and overtime are all factored in automatically.'},
            {'heading': 'Shift Management', 'body': 'Set flexible or fixed shifts per employee. Detect late arrivals, early departures, and overtime with configurable thresholds.'},
            {'heading': 'Leave Management', 'body': 'Employees apply for leave online. Managers approve or reject with a single click. Leave affects attendance and payroll automatically.'},
            {'heading': 'Compliance Reports', 'body': 'Generate monthly attendance summaries, salary reports, and leave balance reports for compliance and audit purposes.'},
        ],
        'faqs': [
            {'q': 'Does it support remote employees?', 'a': 'Yes. GPS-based attendance and WiFi check-in work for remote or field employees.'},
            {'q': 'Can I generate payslips automatically?', 'a': 'Yes. Generate and send individual or bulk payslips in PDF format.'},
        ],
        'cta_label': 'Try It Free',
    },
    'biometric-attendance-system': {
        'title': 'Biometric Attendance System Software | Mero Attendance',
        'meta_desc': 'Connect your ZKTeco or Hikvision biometric device to Mero Attendance. Automate attendance, generate reports, and sync data in real time.',
        'h1': 'Biometric Attendance System Software',
        'intro': 'Mero Attendance integrates with popular biometric attendance devices including ZKTeco and Hikvision. Sync fingerprint or face recognition data directly to your online dashboard.',
        'sections': [
            {'heading': 'ZKTeco Integration', 'body': 'Connect any ZKTeco biometric device (ZK100, ZK200, ZK400 series and more) to Mero Attendance. Attendance records sync automatically via our SDK integration.'},
            {'heading': 'Hikvision Integration', 'body': 'Integrate Hikvision face recognition and fingerprint terminals. Pull attendance logs in real time without manual data entry.'},
            {'heading': 'Multi-Device Support', 'body': 'Add multiple devices per location or branch. Each device records are merged into a single timeline per employee.'},
            {'heading': 'Fallback Attendance', 'body': 'If a device goes offline, staff can still check in via mobile app, QR code, or admin manual entry. No attendance is lost.'},
        ],
        'faqs': [
            {'q': 'Which ZKTeco models are supported?', 'a': 'Most ZKTeco models using the ZKLib SDK are supported. Contact us to confirm your specific model.'},
            {'q': 'Do I need a separate server?', 'a': 'No. Mero Attendance is cloud-based. Your device connects to our servers directly.'},
        ],
        'cta_label': 'Connect Your Device',
    },
    'zkteco-attendance-software': {
        'title': 'ZKTeco Attendance Software Nepal | Mero Attendance',
        'meta_desc': 'Official ZKTeco compatible attendance software in Nepal. Sync ZKTeco biometric device data with Mero Attendance for automatic payroll and reporting.',
        'h1': 'ZKTeco Attendance Software',
        'intro': 'Mero Attendance is compatible with ZKTeco biometric attendance devices. Pull fingerprint attendance data automatically and generate payroll-linked reports without any manual entry.',
        'sections': [
            {'heading': 'How It Works', 'body': 'Install the Mero Attendance sync agent on a PC connected to your ZKTeco device. The agent pulls attendance logs every few minutes and uploads them to your cloud dashboard.'},
            {'heading': 'Supported Features', 'body': 'Fingerprint, face recognition, RFID card, and PIN-based attendance from ZKTeco devices. All attendance types are unified in one timeline.'},
            {'heading': 'Reports & Payroll', 'body': 'Once synced, generate daily reports, monthly summaries, late reports, and payslips — all in PDF or Excel format.'},
        ],
        'faqs': [
            {'q': 'Is this software free?', 'a': 'Mero Attendance offers a free demo. Contact us for pricing based on your organization size.'},
            {'q': 'Can I use multiple ZKTeco devices?', 'a': 'Yes. Add as many devices as needed across branches.'},
        ],
        'cta_label': 'Connect ZKTeco Device',
    },
    'hikvision-attendance-software': {
        'title': 'Hikvision Attendance Software Nepal | Mero Attendance',
        'meta_desc': 'Connect Hikvision face recognition terminals to Mero Attendance. Automate attendance tracking and payroll for your office or school.',
        'h1': 'Hikvision Attendance Software',
        'intro': 'Mero Attendance supports Hikvision face recognition and biometric terminals. Sync employee attendance data automatically and eliminate manual time-and-attendance tracking.',
        'sections': [
            {'heading': 'Hikvision Device Sync', 'body': 'Connect Hikvision DS-K1T series and compatible face recognition terminals. Attendance events pull to your Mero Attendance dashboard in near real time.'},
            {'heading': 'Face Recognition Attendance', 'body': 'No contact required. Employees are identified by face, making attendance fast and hygienic — ideal for high-traffic entry points.'},
            {'heading': 'Combined with Mero Attendance HRMS', 'body': 'Once attendance is synced, use the full HRMS suite — leave management, payroll, payslip, task tracking, and staff documents — all in one platform.'},
        ],
        'faqs': [
            {'q': 'Which Hikvision models work?', 'a': 'DS-K1T671 and compatible models using the ISAPI protocol. Contact us to confirm your device.'},
        ],
        'cta_label': 'Get Device Connected',
    },
    'qr-attendance-system': {
        'title': 'QR Code Attendance System | Mero Attendance',
        'meta_desc': 'Mark attendance by scanning a QR code with your mobile phone. Fast, contactless, and device-free. Works for offices, schools, and events.',
        'h1': 'QR Code Attendance System',
        'intro': 'Mero Attendance supports QR code-based attendance. Print or display a QR code at your entrance. Staff and students scan it with their phone to check in — no device, no card, no contact.',
        'sections': [
            {'heading': 'How QR Attendance Works', 'body': 'Admin generates a unique QR code per location or class. Staff scan it using the Mero Attendance mobile app. The system logs time, location, and identity automatically.'},
            {'heading': 'Rotating QR for Security', 'body': 'QR codes can be set to rotate periodically to prevent screenshot sharing. Each scan is validated against the employee profile and location.'},
            {'heading': 'Ideal For', 'body': 'Small offices without biometric devices, classrooms, events, workshops, and field teams who need flexible check-in options.'},
        ],
        'faqs': [
            {'q': 'Can one QR code work for multiple staff?', 'a': 'Yes. Each staff scans the same location QR but their own identity is recorded individually.'},
            {'q': 'Is this secure?', 'a': 'Yes. The system validates the scan against registered devices and can enforce location proximity.'},
        ],
        'cta_label': 'Enable QR Attendance',
    },
    'gps-attendance-system': {
        'title': 'GPS Attendance System for Field Staff | Mero Attendance',
        'meta_desc': 'Let field employees mark attendance from their location using GPS. Verify location accuracy and generate geo-stamped reports.',
        'h1': 'GPS Attendance System',
        'intro': 'Track field staff and remote employee attendance using GPS location verification. Staff check in from their phone. The system verifies their GPS coordinates against pre-set office locations.',
        'sections': [
            {'heading': 'Location-Based Check-In', 'body': 'Define an allowed radius for each office or site. Staff must be within the defined area to mark attendance. Fake check-ins from home are rejected automatically.'},
            {'heading': 'Field Staff Use Case', 'body': 'Perfect for construction sites, sales teams, delivery staff, healthcare workers, and any employee who works outside a fixed office.'},
            {'heading': 'Geo-Stamped Reports', 'body': 'Every attendance record includes GPS coordinates and a timestamp. Reports show location data alongside attendance status.'},
        ],
        'faqs': [
            {'q': 'Does GPS work without internet?', 'a': 'GPS check-in requires internet to submit the location to the server. Offline GPS attendance is not currently supported.'},
            {'q': 'How accurate is the location check?', 'a': 'Accuracy depends on the device GPS. You can set a tolerance radius (e.g., 100m) to accommodate slight GPS drift.'},
        ],
        'cta_label': 'Enable GPS Attendance',
    },
    'wifi-attendance-system': {
        'title': 'WiFi Based Attendance System | Mero Attendance',
        'meta_desc': 'Auto-mark attendance when staff connect to the office WiFi network. No device, no QR scan. Just connect and you are marked present.',
        'h1': 'WiFi Based Attendance System',
        'intro': 'Mero Attendance can automatically mark employees as present when they connect to a registered office WiFi network. No manual check-in required — just connect to WiFi and attendance is recorded.',
        'sections': [
            {'heading': 'How WiFi Attendance Works', 'body': 'Admin registers one or more office WiFi SSIDs in the system. When a registered staff member connects to that network, the app automatically marks them present with a timestamp.'},
            {'heading': 'Ideal for Open-Plan Offices', 'body': 'No queue at a biometric device. No scanning QR codes. Staff simply arrive at the office, connect to WiFi, and their attendance is recorded in the background.'},
            {'heading': 'Fallback Options', 'body': 'If staff work outside the WiFi zone, they can use GPS, QR, or manual check-in as a backup. All methods sync to the same attendance timeline.'},
        ],
        'faqs': [
            {'q': 'Can employees trick the system by connecting from home?', 'a': 'The system checks SSID and can also verify GPS location alongside WiFi connection to prevent spoofing.'},
        ],
        'cta_label': 'Enable WiFi Attendance',
    },
    'hrms-software-nepal': {
        'title': 'HRMS Software Nepal | Human Resource Management | Mero Attendance',
        'meta_desc': 'Complete HRMS software for Nepal. Manage staff, payroll, leave, documents, resignations, tasks, and compliance — all in one platform.',
        'h1': 'HRMS Software for Nepal',
        'intro': 'Mero Attendance is a complete Human Resource Management System (HRMS) built for Nepali organizations. From onboarding to resignation, manage the full employee lifecycle in one platform.',
        'sections': [
            {'heading': 'What is HRMS?', 'body': 'HRMS (Human Resource Management System) is software that handles all HR workflows: employee records, attendance, leave, payroll, performance, documents, and offboarding.'},
            {'heading': 'Staff Management', 'body': 'Maintain complete staff profiles including personal details, employment type, salary structure, shift schedule, branch, probation status, and document records.'},
            {'heading': 'Payroll & Payslip', 'body': 'Generate monthly payslips with automatic PF, SSF, tax, allowance, and deduction calculations. Send payslips by email or let staff download from their portal.'},
            {'heading': 'Leave & Attendance', 'body': 'Define leave types with annual allocations. Staff apply online, managers approve, and payroll adjusts automatically for unpaid leaves.'},
            {'heading': 'Resignation Management', 'body': 'Staff can apply for resignation online. Admin tracks notice period, last working day, and final settlement status from a single dashboard.'},
        ],
        'faqs': [
            {'q': 'Is PF and SSF calculation built in?', 'a': 'Yes. Configure PF and SSF percentages in payroll settings and they calculate automatically with each payslip.'},
            {'q': 'Does it support probation period tracking?', 'a': 'Yes. Set probation start and end dates per employee. Get automatic reminders when probation is nearing completion.'},
        ],
        'cta_label': 'Start Your HRMS',
    },
    'payroll-management-system': {
        'title': 'Payroll Management System Nepal | Mero Attendance',
        'meta_desc': 'Automate payroll for your staff in Nepal. Calculate salary, PF, SSF, tax, allowances, and deductions. Generate and send payslips in one click.',
        'h1': 'Payroll Management System',
        'intro': 'Mero Attendance includes a full payroll management system. Calculate staff salaries with attendance-linked present days, paid/unpaid leaves, allowances, deductions, PF, SSF, and tax — then generate professional payslips.',
        'sections': [
            {'heading': 'Attendance-Linked Payroll', 'body': 'Payroll reads attendance data directly. Present days, late deductions, paid leave, and unpaid absence all factor into the final salary calculation automatically.'},
            {'heading': 'Salary Components', 'body': 'Configure gross salary, allowances (travel, food, medical), bonuses, deductions, advance salary recovery, PF contributions, SSF contributions, and tax percentage per employee.'},
            {'heading': 'Probation Payroll', 'body': 'Set a reduced salary percentage for employees on probation. The system applies the probation rate automatically and switches to full salary after the probation period ends.'},
            {'heading': 'Payslip Generation', 'body': 'Generate individual or bulk payslips in PDF format. Send to staff email automatically or let staff download from their self-service portal.'},
        ],
        'faqs': [
            {'q': 'Can I process payroll for hourly staff?', 'a': 'Yes. Mero Attendance supports hourly, daily, and monthly salary types.'},
            {'q': 'What about advance salary recovery?', 'a': 'Advance salaries can be set up with installment-based recovery. The system deducts the installment from each payslip automatically.'},
        ],
        'cta_label': 'Set Up Payroll',
    },
    'school-billing-management-system': {
        'title': 'School Billing Management System Nepal | Mero Attendance',
        'meta_desc': 'Manage school fees, generate invoices, track payments, and send bills to students and parents. Complete billing module for schools in Nepal.',
        'h1': 'School Billing Management System',
        'intro': 'Mero Attendance includes a complete school billing module. Set monthly fees per student or class, generate bulk invoices, track paid and due amounts, and send bills by email.',
        'sections': [
            {'heading': 'Per-Student Fee Configuration', 'body': 'Set monthly fee, discount, scholarship, and billing start date per student. The system calculates the final payable amount automatically.'},
            {'heading': 'Bulk Bill Generation', 'body': 'Generate bills for an entire class or the whole school in one click. Filter by classification, section, or month.'},
            {'heading': 'Payment Tracking', 'body': 'Track paid, partially paid, unpaid, and overdue bills. Send payment reminders to parents by email.'},
            {'heading': 'Linked with Income', 'body': 'When a bill is marked paid, the system can automatically create an income record — keeping your finance module up to date without double entry.'},
        ],
        'faqs': [
            {'q': 'Can I set different fees per class?', 'a': 'Yes. Each student can have an individual fee, or you can apply a class-level default.'},
            {'q': 'Are overdue bills automatically flagged?', 'a': 'Yes. Bills past their due date are highlighted in the dashboard with a pending dues alert.'},
        ],
        'cta_label': 'Enable Billing',
    },
    'student-result-management-system': {
        'title': 'Student Result Management System Nepal | Mero Attendance',
        'meta_desc': 'Enter, manage, and publish student exam results. Send results by email. Let students view results from their own portal.',
        'h1': 'Student Result Management System',
        'intro': 'Mero Attendance includes a complete result management system. Create exam terms, enter marks per subject, publish results, and let students view their marksheet from the student portal.',
        'sections': [
            {'heading': 'Exam Term Management', 'body': 'Create exam terms (first term, half yearly, annual) per class and section. Set mark entry dates and publish dates.'},
            {'heading': 'Bulk Marks Entry', 'body': 'Enter marks for an entire class in a single form. Each student and subject combination is recorded with grade auto-calculation.'},
            {'heading': 'Result Publishing', 'body': 'Control when results become visible to students. Results are only visible in the student portal after the admin publishes them.'},
            {'heading': 'Send Results by Email', 'body': 'Send individual or bulk marksheets to students and parents by email directly from the result dashboard.'},
        ],
        'faqs': [
            {'q': 'Can students see unpublished results?', 'a': 'No. Only published results are visible in the student portal. Draft results are admin-only.'},
            {'q': 'Is grade auto-calculated?', 'a': 'Yes. Grade (A+, A, B, etc.) is computed from the percentage and pass/fail status is determined automatically.'},
        ],
        'cta_label': 'Enable Results',
    },
    'leave-management-system': {
        'title': 'Leave Management System Nepal | Mero Attendance',
        'meta_desc': 'Automate employee leave requests, approvals, and leave balance tracking. Link leave with attendance and payroll automatically.',
        'h1': 'Leave Management System',
        'intro': 'Mero Attendance includes a complete leave management system. Define leave types, set annual allocations, let staff apply online, approve with one click, and sync leave with attendance and payroll.',
        'sections': [
            {'heading': 'Leave Types', 'body': 'Create custom leave types: annual leave, sick leave, maternity leave, emergency leave. Set annual allocation and whether the leave is paid or unpaid.'},
            {'heading': 'Online Leave Application', 'body': 'Staff submit leave requests from their portal or mobile app. Managers receive instant notification and can approve or reject with a reason.'},
            {'heading': 'Leave Balance Tracking', 'body': 'The system tracks how many leaves each employee has used, remaining balance, and year-to-date leave history.'},
            {'heading': 'Payroll Integration', 'body': 'Unpaid leaves automatically reduce the staff salary in the next payroll run. Paid leaves have no deduction.'},
        ],
        'faqs': [
            {'q': 'Can admin log leave on behalf of staff?', 'a': 'Yes. Admins can manually log leave for any member from the admin panel.'},
            {'q': 'Does it support half-day leave?', 'a': 'This depends on your configuration. Contact us for details on partial day leave support.'},
        ],
        'cta_label': 'Enable Leave Management',
    },
    'multi-branch-attendance-system': {
        'title': 'Multi-Branch Attendance System | Mero Attendance',
        'meta_desc': 'Manage attendance across multiple branches from one dashboard. Branch-wise reports, staff assignment, and centralized admin control.',
        'h1': 'Multi-Branch Attendance System',
        'intro': 'Mero Attendance supports unlimited branches. Assign staff and students to branches, generate branch-wise attendance and payroll reports, and manage everything from a single centralized admin panel.',
        'sections': [
            {'heading': 'Centralized Multi-Branch Control', 'body': 'One organization account manages all branches. Admin sees all branches from the main dashboard. Branch managers can be assigned restricted access.'},
            {'heading': 'Branch-wise Reports', 'body': 'Filter all reports — attendance, payroll, billing, stock, income — by branch. Compare performance across branches easily.'},
            {'heading': 'Branch-level Devices', 'body': 'Assign biometric devices, QR codes, or GPS locations to specific branches. Attendance from each branch is logged separately and combined in the main report.'},
        ],
        'faqs': [
            {'q': 'Is there a limit on number of branches?', 'a': 'No. You can add as many branches as your organization needs.'},
            {'q': 'Can branch managers see only their branch data?', 'a': 'Yes. Use the privilege system to restrict staff visibility to branch-level data only.'},
        ],
        'cta_label': 'Set Up Branches',
    },
    'staff-management-system': {
        'title': 'Staff Management System Nepal | Mero Attendance',
        'meta_desc': 'Complete staff management for Nepal. Maintain staff records, shifts, salary, leave, documents, tasks, and performance from one HR dashboard.',
        'h1': 'Staff Management System',
        'intro': 'Mero Attendance provides a comprehensive staff management system. Maintain complete employee profiles, manage their shifts, salary, documents, tasks, leave, and attendance — all in one platform.',
        'sections': [
            {'heading': 'Employee Profiles', 'body': 'Store all staff information: personal details, employment type (permanent, contract, intern, probation), department, branch, shift times, and salary structure.'},
            {'heading': 'Document Management', 'body': 'Upload and manage staff documents: ID copies, contracts, certificates, degrees, and passport copies — with expiry date tracking.'},
            {'heading': 'Task Assignment', 'body': 'Create one-time or recurring tasks. Assign to individual staff or entire teams. Track completion with proof attachments and approval workflows.'},
            {'heading': 'Staff Self-Service Portal', 'body': 'Staff access their own attendance, payslips, leave history, task list, and complaints from a mobile-friendly dashboard — reducing HR admin workload.'},
        ],
        'faqs': [
            {'q': 'Can staff update their own profile?', 'a': 'Admins control what staff can update. By default, staff view their profile but cannot edit sensitive fields like salary.'},
        ],
        'cta_label': 'Start Managing Staff',
    },
    'office-management-system': {
        'title': 'Office Management System Nepal | Mero Attendance',
        'meta_desc': 'All-in-one office management software for Nepal. Attendance, payroll, leave, tasks, stock, finance, and HR in a single cloud platform.',
        'h1': 'Office Management System',
        'intro': 'Mero Attendance is an all-in-one office management system designed for offices, companies, and businesses in Nepal. From attendance to payroll, stock to finance — manage your entire office from one dashboard.',
        'sections': [
            {'heading': 'Complete Office Automation', 'body': 'Replace spreadsheets and manual registers with a cloud-based system. Track employee time, process payroll, manage stock, record income and expenses, and assign tasks — all in one place.'},
            {'heading': 'Finance Module', 'body': 'Record all income and expenses by category. Link payroll and billing payments automatically. Generate profit/loss summaries and financial reports by date, branch, or category.'},
            {'heading': 'Stock & Inventory', 'body': 'Manage office supplies, track usage, set low-stock alerts, and maintain a full movement history with stock-in and stock-out records.'},
            {'heading': 'Events & Calendar', 'body': 'Schedule meetings, events, and programs. Link events to stock usage and expenses. View all upcoming events in a visual calendar.'},
        ],
        'faqs': [
            {'q': 'Is this suitable for a small office?', 'a': 'Yes. Mero Attendance is designed to scale from 5 employees to 5,000. Start with just attendance and add modules as you grow.'},
        ],
        'cta_label': 'Get Started',
    },
    'school-erp-nepal': {
        'title': 'School ERP Nepal | School Management System | Mero Attendance',
        'meta_desc': 'Complete school ERP for Nepal. Manage student attendance, results, billing, teacher attendance, payroll, leave, and more in one platform.',
        'h1': 'School ERP System Nepal',
        'intro': 'Mero Attendance is a school ERP system built specifically for Nepali schools, colleges, and institutes. Manage students, teachers, attendance, results, billing, and payroll — all from one cloud platform.',
        'sections': [
            {'heading': 'Student Management', 'body': 'Maintain complete student records: personal details, guardian info, class, section, billing, and attendance history. Track student status from admission to pass-out.'},
            {'heading': 'Teacher Management', 'body': 'Track teacher attendance, teaching logs, courses assigned, and salary. Set shift times and generate monthly teaching reports.'},
            {'heading': 'Academic Modules', 'body': 'Manage classifications (classes), sections, courses/subjects, exam terms, and result records. Generate class-wise academic performance reports.'},
            {'heading': 'School Finance', 'body': 'Collect student fees, track income from billing, record expenses, and generate financial summaries. Full billing and finance integration in one platform.'},
        ],
        'faqs': [
            {'q': 'Does it support Nepali calendar (BS)?', 'a': 'Yes. You can switch between AD and BS dates for all records, reports, and attendance.'},
            {'q': 'Is it suitable for a college?', 'a': 'Yes. Mero Attendance works for schools, colleges, bachelor programs, and any academic institution.'},
        ],
        'cta_label': 'Start Your School ERP',
    },
    'attendance-app-nepal': {
        'title': 'Attendance App Nepal | Mobile Attendance Tracking | Mero Attendance',
        'meta_desc': 'Mobile attendance app for Nepal. QR scan, GPS check-in, WiFi auto-attendance. Works on Android and iOS.',
        'h1': 'Attendance App Nepal',
        'intro': 'Mero Attendance provides a mobile-friendly attendance solution for organizations in Nepal. Staff can check in using QR scan, GPS location, or WiFi — all from their smartphone.',
        'sections': [
            {'heading': 'Mobile Check-In Options', 'body': 'Staff use their phone to scan a QR code, verify their GPS location, or auto-check-in via WiFi. No separate device or punch card needed.'},
            {'heading': 'Works for All Industries', 'body': 'Schools, offices, factories, NGOs, hospitals — any organization where staff need a mobile check-in option instead of a fixed biometric device.'},
            {'heading': 'Nepal-Specific', 'body': 'Nepali calendar support, local time zone, Nepali language interface option, and pricing suitable for Nepali SMEs and educational institutions.'},
        ],
        'faqs': [
            {'q': 'Is there a native app?', 'a': 'Mero Attendance is a Progressive Web App (PWA) that works on any mobile browser. A native Android app is in development.'},
        ],
        'cta_label': 'Try the App',
    },
    'cloud-attendance-system': {
        'title': 'Cloud-Based Attendance System | Mero Attendance',
        'meta_desc': 'Access your attendance system from anywhere. Cloud-based, real-time, secure, and always available. No server to maintain.',
        'h1': 'Cloud-Based Attendance System',
        'intro': 'Mero Attendance is a 100% cloud-based attendance management system. Access your dashboard, reports, and settings from anywhere in the world — no installation, no server maintenance required.',
        'sections': [
            {'heading': 'Always Available', 'body': 'Your attendance data is securely stored in the cloud. Access it 24/7 from any browser on any device — desktop, tablet, or mobile.'},
            {'heading': 'Real-Time Data', 'body': 'Attendance records appear on your dashboard as they are marked. No end-of-day upload or sync delay. See who is present right now.'},
            {'heading': 'Secure & Private', 'body': 'Data is isolated per organization. No other organization can see your data. HTTPS encryption on all connections.'},
            {'heading': 'No IT Required', 'body': 'No server, no IT staff, no maintenance. Just create your account, add your members, and start tracking.'},
        ],
        'faqs': [
            {'q': 'What happens to my data if I cancel?', 'a': 'You can export all your data before cancellation. Contact support for data export assistance.'},
        ],
        'cta_label': 'Start Cloud Attendance',
    },
}


class SeoLandingView(TemplateView):
    """Single view that serves all SEO landing pages from the SEO_PAGES dict."""
    template_name = 'basic/seo_landing.html'

    def get(self, request, *args, **kwargs):
        slug = kwargs.get('slug', '')
        page = SEO_PAGES.get(slug)
        if not page:
            from django.http import Http404
            raise Http404
        ctx = self.get_context_data(**kwargs)
        ctx['page'] = page
        ctx['slug'] = slug
        return render(request, self.template_name, ctx)


class SitemapView(TemplateView):
    """Generate XML sitemap for all public pages and SEO pages."""
    template_name = 'basic/sitemap.xml'
    content_type = 'application/xml'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['seo_slugs'] = list(SEO_PAGES.keys())
        ctx['posts'] = BlogPost.objects.filter(published=True).values_list('slug', flat=True)
        return ctx


def robots_txt(request):
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /schooladmin/',
        'Disallow: /superadmin/',
        'Disallow: /staff/',
        'Disallow: /handle/',
        'Disallow: /admin/',
        '',
        'Sitemap: https://meroattendance.com/sitemap.xml',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')