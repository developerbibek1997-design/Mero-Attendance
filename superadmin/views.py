from datetime import timezone
import datetime
import os
from django.http.response import HttpResponseRedirect
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.contrib import messages
from django.urls import reverse
from django.db import transaction
from django.utils.text import slugify
from management.models import Holiday, Occasion, Organization
from management.models import Schooladmin, AgentProfile, AgentLedger, AgentActivityLog
from management.models import CustomUser
from school import settings
from .forms import OrgForm, SchooladminForm, BlogPostForm, FAQForm
from management.models import BlogPost, FAQ, ContactUs, PackageRequest
from agent.forms import SuperAdminAgentForm
from handle.models import AttendanceRecord, Classification, Course, Device, Staff, member
from management.pricing_services import pricing_tier_payload
from .organization_services import (
    active_dynamic_features,
    build_feature_groups,
    dashboard_subscription_context,
    preset_feature_keys,
    save_feature_selection,
    selected_feature_keys,
    subscription_summary,
)

from django.core.mail import send_mail


def activate(request, id):
    if request.method == 'POST':
        date = request.POST.get('date')
        if not date:
            messages.error(request, "Please provide a valid date.")
            return HttpResponseRedirect(reverse('superadmin:dashboard'))
        else:
            org = Organization.objects.get(id = id)
            org.activate = True
            org.expire_on = date
            org.save()
            messages.success(request, "Successfully Activated Organization")
            return HttpResponseRedirect(reverse('superadmin:dashboard'))
    else:
        messages.error(request, "Invalid request method.")
        return HttpResponseRedirect(reverse('superadmin:dashboard'))

def deactivate(request, id):
    org = Organization.objects.get(id = id)
    org.activate = False
    org.save()
    messages.success(request, "Successfully Deactivated Organization")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))

class Dashboard(View):
    template_name = 'super_admin/SAdashboard.html'

    def get(self, request, *args, **kwargs):
        organizations = list(Organization.objects.all().order_by('name'))
        org_count = len(organizations)
        user_count = Schooladmin.objects.all().count()
        
        # Fetching both weekly and occasion holidays for the dashboard
        recent_holidays = Holiday.objects.all().select_related('org').order_by('-id')[:5] 
        recent_occasions = Occasion.objects.all().select_related('org').order_by('-date')[:5]
        
        subscription_context = dashboard_subscription_context(organizations)
        recent_contacts = ContactUs.objects.order_by('-created_at')[:5]
        recent_package_requests = PackageRequest.objects.order_by('-created_at')[:5]
        dist = {
            'org': organizations,
            'org_count': org_count,
            'user_count': user_count,
            'recent_holidays': recent_holidays,
            'recent_occasions': recent_occasions,
            'recent_contacts': recent_contacts,
            'recent_package_requests': recent_package_requests,
            **subscription_context,
        }
        return render(request, self.template_name, dist)

class OrganizationDetail(View):
    template_name = 'super_admin/orgDetails.html'

    def get(self, request, id, *args, **kwargs):
        print("fck me ")
        org = get_object_or_404(Organization, id=id)
        
        # 1. Fetch Members & Classifications
        members = member.objects.filter(org=org).exclude(status='dumped').order_by('-created_date')
        classifications = Classification.objects.filter(org=org)
        
        # Generate Classification Distribution for the Chart
        classification_distribution = []
        for cls in classifications:
            count = members.filter(classification=cls).count()
            if count > 0:
                classification_distribution.append({
                    'name': cls.name,
                    'count': count
                })

        # 2. Fetch Infrastructure & Staff
        devices = Device.objects.filter(org=org)
        # Fetch the actual Org Admins created by Superadmin
        school_admins = Schooladmin.objects.filter(org=org).select_related('admin')
        # Fetch standard staff if any exist
        staff_members = Staff.objects.filter(org=org).select_related('admin')
        
        # 3. Generate Top Stats
        total_members = members.count()
        active_members = members.filter(black_list=False).count()
        total_attendance = AttendanceRecord.objects.filter(org=org).count()
        
        # Connected Year (Fallback to current year if no members)
        first_member = members.order_by('created_date').first()
        connected_year = first_member.created_date.year if first_member else datetime.date.today().year

        # 4. Fetch Holidays
        weekly_holidays = Holiday.objects.filter(org=org)
        occasions = Occasion.objects.filter(org=org).order_by('-date')

        context = {
            'org': org,
            'members': members,
            'total_members': total_members,
            'active_members': active_members,
            'total_attendance': total_attendance,
            'classifications': classifications,
            'classification_distribution': classification_distribution, # Required for Pie Chart!
            'devices': devices,
            'school_admins': school_admins, # Passing the Org Admins
            'staff_members': staff_members, # Passing Standard Staff
            'weekly_holidays': weekly_holidays,
            'occasions': occasions,
            'connected_year': connected_year,
            'subscription_summary': subscription_summary(org),
        }

        return render(request, self.template_name, context)


class GlobalHolidayView(View):
    template_name = 'super_admin/addGlobalHoliday.html'

    def get(self, request, *args, **kwargs):
        orgs = Organization.objects.filter(activate=True).order_by('name')
        
        # Fetch distinct occasions so we don't show duplicates if pushed to multiple orgs
        occasions = Occasion.objects.values('name', 'date', 'end_date').distinct().order_by('-date')[:30]
        
        return render(request, self.template_name, {
            'orgs': orgs,
            'occasions': occasions
        })

    def post(self, request, *args, **kwargs):
        org_ids = request.POST.getlist('organizations')
        action_type = request.POST.get('action_type') # 'weekly' or 'occasion'
        
        if not org_ids:
            messages.error(request, "Please select at least one organization.")
            return redirect('superadmin:globalHoliday')

        # Determine target organizations
        if 'all' in org_ids:
            target_orgs = Organization.objects.all()
        else:
            target_orgs = Organization.objects.filter(id__in=org_ids)

        # Handle Weekly Days Off
        if action_type == 'weekly':
            days = request.POST.getlist('day')
            for org in target_orgs:
                existing_days = set(Holiday.objects.filter(org=org).values_list('holiday', flat=True))
                selected_days = set(days)
                
                # Add new holidays that don't exist yet for this org
                holidays_to_add = selected_days - existing_days
                for day in holidays_to_add:
                    Holiday.objects.create(holiday=day, org=org)
                    
                # Optional: Remove unchecked days (if you want strict override)
                # holidays_to_remove = existing_days - selected_days
                # Holiday.objects.filter(org=org, holiday__in=holidays_to_remove).delete()

            messages.success(request, f"Weekly holidays successfully pushed to {target_orgs.count()} organization(s).")

        # Handle Occasion / Gap Holidays
        elif action_type == 'occasion':
            occasion_name = request.POST.get('occasion')
            start_date = request.POST.get('ocDate')
            holiday_type = request.POST.get('holidayType')
            end_date = request.POST.get('ocEndDate') if holiday_type == 'gap' else None
            
            for org in target_orgs:
                Occasion.objects.create(
                    name=occasion_name,
                    org=org,
                    date=start_date,
                    end_date=end_date if end_date else None
                )
            messages.success(request, f"Occasion '{occasion_name}' added to {target_orgs.count()} organization(s).")

        return redirect('superadmin:dashboard')

# 2. Advanced Broadcast Email View
class BroadcastNotificationView(View):
    template_name = 'super_admin/broadcastEmail.html'

    def get(self, request, *args, **kwargs):
        orgs = Organization.objects.filter(activate=True).order_by('name')
        return render(request, self.template_name, {'orgs': orgs})

    def post(self, request, *args, **kwargs):
        org_ids = request.POST.getlist('organizations')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        if not org_ids:
            messages.error(request, "Please select at least one organization to email.")
            return redirect('superadmin:broadcastEmail')

        if subject and message:
            # Filter admins based on selected orgs
            if 'all' in org_ids:
                admins = Schooladmin.objects.select_related('admin').all()
            else:
                admins = Schooladmin.objects.select_related('admin').filter(org_id__in=org_ids)
                
            recipient_list = [admin.admin.email for admin in admins if admin.admin.email]
            
            if not recipient_list:
                messages.warning(request, "No valid email addresses found for the selected organizations.")
                return redirect('superadmin:broadcastEmail')

            try:
                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,
                    recipient_list,
                    fail_silently=False,
                )
                messages.success(request, f"Email sent successfully to {len(recipient_list)} admin(s).")
            except Exception as e:
                messages.error(request, f"Failed to send email: {str(e)}")
        else:
            messages.error(request, "Subject and Message are required.")
            
        return redirect('superadmin:dashboard')


    

class MemberList(View):
    template_name = 'super_admin/memberList.html'

    def get(self, request, *args, **kwargs):
        mem = member.objects.all()
       
        dist = {
            'mem': mem,
            'org': Organization.objects.all()
           
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *agrs, **kwargs):
        clas = request.POST['classification']
        print('class', clas)
        try:

            ors = Organization.objects.get(id = clas)
        except:
            pass
        
        cl=Organization.objects.all()
        if clas == 'All':
            mem = member.objects.all()
            th = 'All' 
        else:
            mem = member.objects.filter(org = ors).exclude(status='dumped')
            th = Organization.objects.get(id = clas).name
        dist = {
            'mem':mem,
            'clas':cl,
            'thisone': th,
            'org': Organization.objects.all()
        }
        return render(request, self.template_name, dist)
    
class Settings(View):
    template_name = 'super_admin/settings.html'

    def get(self, request, *args, **kwargs):
        from django.db import connection
        org = Organization.objects.all()
        dist = {
            'org': org,
            'db_is_sqlite': connection.vendor == 'sqlite',
        }
        return render(request, self.template_name, dist)

    def post(self, request, *args, **kwargs):
        messages.success(request, "Settings Updated Successfully")
        return HttpResponseRedirect(reverse('superadmin:setting'))


def build_sqlite_backup_response(source_path):
    """
    Copies the SQLite file at `source_path` via the sqlite3 online backup
    API (not a raw file copy) into a server-side temp file, then wraps it in
    a FileResponse that deletes the temp file once fully streamed — nothing
    from the backup is left on disk after the download completes. Using the
    backup API instead of a plain file copy means a backup taken while the
    app is live and writing never captures a torn/partial page, and
    correctly picks up committed WAL data a plain file copy of db.sqlite3
    could miss.
    """
    import sqlite3
    import tempfile

    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.sqlite3')
    os.close(tmp_fd)

    source_conn = sqlite3.connect(f'file:{source_path}?mode=ro', uri=True)
    dest_conn = sqlite3.connect(tmp_path)
    try:
        source_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        source_conn.close()

    filename = f"mero_attendance_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
    file_handle = open(tmp_path, 'rb')
    original_close = file_handle.close

    def _close_and_cleanup():
        original_close()
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    file_handle.close = _close_and_cleanup
    response = FileResponse(file_handle, as_attachment=True, filename=filename, content_type='application/x-sqlite3')
    response['Content-Length'] = os.path.getsize(tmp_path)
    return response


def database_backup(request):
    """Superadmin-only: download a point-in-time SQLite backup. See build_sqlite_backup_response()."""
    from django.db import connection

    if request.method != 'POST':
        messages.error(request, "Invalid request method.")
        return redirect('superadmin:setting')

    if connection.vendor != 'sqlite':
        messages.error(request, "Database backup is only available for SQLite deployments.")
        return redirect('superadmin:setting')

    return build_sqlite_backup_response(str(connection.settings_dict['NAME']))


class SearchView(View):

    template_name = 'super_admin/searchResult.html'


    def post(self, request, *args, **kwargs):
        search_query = request.POST.get('search_query', '')
        if search_query:
            org = Organization.objects.filter(name__icontains=search_query)
            user = Schooladmin.objects.filter(admin__first_name__icontains=search_query) | Schooladmin.objects.filter(admin__last_name__icontains=search_query)
            mem = member.objects.filter(name=search_query).exclude(status='dumped') | member.objects.filter(email__icontains=search_query).exclude(status='dumped')

            print(org, user, mem)
            
            dist = {
                'org': org,
                'user': user,
                'search_query': search_query, 
                'mem': mem,
            }
            return render(request, self.template_name, dist)
        else:
            messages.error(request, "Please enter a search term.")
            return HttpResponseRedirect(reverse('superadmin:dashboard'))

    def get(self, request, *args, **kwagrs):
        org = Organization.objects.all()
        org_count = org.count()
        user_count = Schooladmin.objects.all().count()
        dist = {
            'org':org,
            'org_count':org_count,
            'user_count':user_count

        }
        return render(request, self.template_name, dist)
    

def _organization_form_context(form, org=None, selected_keys=None):
    category = (
        form.data.get('category')
        if form.is_bound
        else (org.category if org else form.initial.get('category', 'others'))
    ) or 'others'
    dynamic_features = active_dynamic_features()
    if selected_keys is None:
        selected_keys = (
            selected_feature_keys(org)
            if org
            else preset_feature_keys(category, dynamic_features)
        )
    return {
        'form': form,
        'org': org,
        'is_edit': bool(org),
        'feature_groups': build_feature_groups(
            org=org,
            selected_keys=selected_keys,
            dynamic_features=dynamic_features,
        ),
        'feature_presets': {
            category_key: sorted(
                preset_feature_keys(category_key, dynamic_features)
            )
            for category_key, _label in Organization.CATEGORY_CHOICES
        },
        'pricing_tiers': pricing_tier_payload(),
        'subscription_summary': subscription_summary(org) if org else None,
    }


def _posted_feature_keys(request):
    selected = set(request.POST.getlist('feature_keys'))
    # Older/no-JavaScript submissions do not include the unified feature input.
    # In that case the category's safe recommended preset is the intended state.
    if not selected:
        selected = preset_feature_keys(request.POST.get('category', 'others'))
    return selected


def _normalize_subscription(org):
    if org.created_at:
        org.subscription_start = org.created_at.date()
    if not org.subscription_end and org.expire_on:
        org.subscription_end = (
            org.expire_on.date() if hasattr(org.expire_on, 'date') else org.expire_on
        )
    if not org.subscription_plan:
        org.subscription_plan = 'Free Demo' if org.free_demo else 'Annual Custom'


class addOrg(View):
    template_name = 'super_admin/organization_form.html'

    def get(self, request, *args, **kwargs):
        form = OrgForm()
        return render(request, self.template_name, _organization_form_context(form))

    def post(self, request, *args, **kwargs):
        form = OrgForm(request.POST, request.FILES or None)
        posted_keys = _posted_feature_keys(request)
        if form.is_valid():
            with transaction.atomic():
                new_org = form.save(commit=False)
                _normalize_subscription(new_org)
                new_org.save()
                save_feature_selection(new_org, posted_keys)
            messages.success(
                request,
                "Organization created with its subscription and feature package.",
            )
            return HttpResponseRedirect(reverse('superadmin:editOrg', args=[new_org.id]))

        messages.error(request, "Please correct the highlighted organization details.")
        return render(
            request,
            self.template_name,
            _organization_form_context(form, selected_keys=posted_keys),
        )


def deleteOrg(request, id):
    org = Organization.objects.get(id=id)
    org.delete()
    messages.success(request, "Successfully Deleted Organization")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))


def editOrg(request, id):
    org = get_object_or_404(Organization, id=id)

    if request.method == 'POST':
        form = OrgForm(request.POST, request.FILES or None, instance=org)
        posted_keys = _posted_feature_keys(request)
        if form.is_valid():
            with transaction.atomic():
                org = form.save(commit=False)
                _normalize_subscription(org)
                org.save()
                save_feature_selection(org, posted_keys)
            messages.success(
                request,
                "Organization, subscription, pricing and features updated successfully.",
            )
            return HttpResponseRedirect(reverse('superadmin:editOrg', args=[org.id]))

        messages.error(request, "Please correct the highlighted organization details.")
        return render(
            request,
            'super_admin/organization_form.html',
            _organization_form_context(form, org=org, selected_keys=posted_keys),
        )

    form = OrgForm(instance=org)
    return render(
        request,
        'super_admin/organization_form.html',
        _organization_form_context(form, org=org),
    )

class addUser(View):
    template_name = 'super_admin/addUser.html'

    def get(self, request, *args, **kwagrs):
        org = Organization.objects.all()
        form = SchooladminForm()
        dist = {
            'org':org,
            'form':form
        }
        return render(request, self.template_name, dist)
    
    def post(self, request, *args, **kwargs):
        form = SchooladminForm(request.POST or None)
        if form.is_valid():
            cd = form.cleaned_data
            first_name = cd['first_name']
            last_name = cd['last_name']
            email = cd['email']
            password = cd['password']
            number = cd['number']
            org = cd['org']
            TypeOne = CustomUser.objects.create_user(first_name=first_name, last_name = last_name, email = email, username = email, password=password)
            Schooladmin.objects.create(admin = TypeOne, org = org, number = number)
            TypeOne.user_type = "2"
            TypeOne.save()
            messages.success(request, "Succesfully Added User")
            return HttpResponseRedirect(reverse('superadmin:addUser'))
        else:
            messages.error(request, "Something went Wrong")
            return render(request, self.template_name, {'form':form})



def deleteUser(request, id):
    org = Organization.objects.get(id = id)
    org.delete()
    messages.success(request, "Successfully Delete User")
    return HttpResponseRedirect(reverse('superadmin:dashboard'))


def editUser(request, id):
    form = OrgForm()
    org = Organization.objects.get(id =id)
    form.fields['name'].initial = org.name
    form.fields['serial_key'].initial = org.serial_key
    form.fields['expire_on'].initial = org.expire_on
    form.fields['new_serial_key'].initial = org.new_serial_key
    form.fields['activate'].initial = org.activate

    dist = {
        'form':form,
        'org':org
    }
    if request.method == 'POST':
        org.name = request.POST['name']
        org.serial_key = request.POST['serial_key']
        org.expire_on = request.POST['expire_on']
        org.new_serial_key = request.POST['new_serial_key']
        org.activate = True if request.POST['activate'] == 'on' else False
        org.save()
        messages.success(request, "Succesfully Update Organizaton")
        return HttpResponseRedirect(reverse('superadmin:editOrg', args=[org.id]))
    return render(request, 'super_admin/editOrg.html', dist)

# ── Cross-Org Attendance Report ────────────────────────────────────────────────

from handle.models import AttendanceRecord as _AR

class SuperAttendanceReportView(View):
    template_name = 'super_admin/attendance_report.html'

    def get(self, request):
        orgs = Organization.objects.all().order_by('name')
        selected_org = request.GET.get('org', '')
        from_date = request.GET.get('from_date', '')
        to_date = request.GET.get('to_date', '')
        records = _AR.objects.none()
        org_obj = None
        total = 0

        if selected_org:
            try:
                org_obj = Organization.objects.get(pk=selected_org)
                records = _AR.objects.filter(org=org_obj).select_related('mem').order_by('-scanned_time')
                if from_date:
                    records = records.filter(scanned_time__date__gte=from_date)
                if to_date:
                    records = records.filter(scanned_time__date__lte=to_date)
                total = records.count()
                records = records[:1000]
            except Organization.DoesNotExist:
                pass

        return render(request, self.template_name, {
            'orgs': orgs, 'records': records, 'total_records': total,
            'selected_org': selected_org, 'org_obj': org_obj,
            'from_date': from_date, 'to_date': to_date,
        })

    def post(self, request):
        selected_org = request.POST.get('org')
        from_date = request.POST.get('from_date')
        to_date = request.POST.get('to_date')
        if request.POST.get('confirm') != 'yes':
            messages.error(request, "Check the confirmation box before deleting.")
            return redirect('superadmin:attendance_report')
        try:
            org_obj = Organization.objects.get(pk=selected_org)
            qs = _AR.objects.filter(org=org_obj)
            if from_date:
                qs = qs.filter(scanned_time__date__gte=from_date)
            if to_date:
                qs = qs.filter(scanned_time__date__lte=to_date)
            count = qs.count()
            qs.delete()
            messages.success(request, f"Deleted {count} records from {org_obj.name}.")
        except Exception as e:
            messages.error(request, str(e))
        return redirect('superadmin:attendance_report')


# ─── Agent Management Views ───────────────────────────────────────────────────

class AgentListView(View):
    template_name = 'super_admin/agents/list.html'

    def get(self, request):
        agents = AgentProfile.objects.all().select_related('admin').order_by('-created_at')
        return render(request, self.template_name, {'agents': agents})


class AgentAddView(View):
    template_name = 'super_admin/agents/add.html'

    def get(self, request):
        form = SuperAdminAgentForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        form = SuperAdminAgentForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = CustomUser.objects.create_user(
                        username=form.cleaned_data['email'],
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password'],
                        first_name=form.cleaned_data['first_name'],
                        last_name=form.cleaned_data.get('last_name', ''),
                        user_type='4',
                    )
                    agent = form.save(commit=False)
                    agent.admin = user
                    agent.created_by = request.user
                    agent.save()
                messages.success(request, f"Agent '{agent.full_name}' created successfully.")
                return redirect('superadmin:agent_list')
            except Exception as e:
                messages.error(request, f"Error creating agent: {e}")
        return render(request, self.template_name, {'form': form})


class AgentDetailView(View):
    template_name = 'super_admin/agents/detail.html'

    def get(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        orgs = agent.organizations.all().order_by('-id')
        ledger = agent.ledger_entries.all().order_by('-created_at')[:20]
        activity = agent.activity_logs.all()[:20]
        return render(request, self.template_name, {
            'agent': agent, 'orgs': orgs, 'ledger': ledger, 'activity': activity
        })


class AgentEditView(View):
    template_name = 'super_admin/agents/edit.html'

    def get(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        form = SuperAdminAgentForm(instance=agent)
        return render(request, self.template_name, {'agent': agent, 'form': form})

    def post(self, request, agent_id):
        agent = get_object_or_404(AgentProfile, id=agent_id)
        form = SuperAdminAgentForm(request.POST, request.FILES, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, "Agent updated successfully.")
            return redirect('superadmin:agent_detail', agent_id=agent_id)
        return render(request, self.template_name, {'agent': agent, 'form': form})


def agent_suspend(request, agent_id):
    agent = get_object_or_404(AgentProfile, id=agent_id)
    agent.status = 'suspended'
    agent.save()
    messages.success(request, f"Agent '{agent.full_name}' has been suspended.")
    return redirect('superadmin:agent_detail', agent_id=agent_id)


def agent_activate(request, agent_id):
    agent = get_object_or_404(AgentProfile, id=agent_id)
    agent.status = 'active'
    agent.save()
    messages.success(request, f"Agent '{agent.full_name}' has been activated.")
    return redirect('superadmin:agent_detail', agent_id=agent_id)


# ── Blog Management ──────────────────────────────────────────────────────────

class BlogListView(View):
    template_name = 'super_admin/blog/list.html'

    def get(self, request):
        posts = BlogPost.objects.all().order_by('-created_at')
        return render(request, self.template_name, {'posts': posts})


class BlogCreateView(View):
    template_name = 'super_admin/blog/form.html'

    def get(self, request):
        form = BlogPostForm()
        return render(request, self.template_name, {'form': form, 'is_edit': False})

    def post(self, request):
        form = BlogPostForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, "Blog post created successfully.")
            return redirect('superadmin:blog_list')
        return render(request, self.template_name, {'form': form, 'is_edit': False})


class BlogEditView(View):
    template_name = 'super_admin/blog/form.html'

    def get(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        form = BlogPostForm(instance=post)
        return render(request, self.template_name, {'form': form, 'post': post, 'is_edit': True})

    def post(self, request, pk):
        post = get_object_or_404(BlogPost, pk=pk)
        form = BlogPostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Blog post updated successfully.")
            return redirect('superadmin:blog_list')
        return render(request, self.template_name, {'form': form, 'post': post, 'is_edit': True})


def blog_delete(request, pk):
    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == 'POST':
        post.delete()
        messages.success(request, "Blog post deleted.")
    return redirect('superadmin:blog_list')


def blog_toggle_publish(request, pk):
    post = get_object_or_404(BlogPost, pk=pk)
    if request.method == 'POST':
        post.published = not post.published
        post.save(update_fields=['published'])
        messages.success(request, f"'{post.title}' is now {'published' if post.published else 'unpublished'}.")
    return redirect('superadmin:blog_list')


class FAQListView(View):
    template_name = 'super_admin/faq/list.html'

    def get(self, request):
        faqs = FAQ.objects.all().order_by('order', 'id')
        return render(request, self.template_name, {'faqs': faqs})


class FAQCreateView(View):
    template_name = 'super_admin/faq/form.html'

    def get(self, request):
        form = FAQForm()
        return render(request, self.template_name, {'form': form, 'is_edit': False})

    def post(self, request):
        form = FAQForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "FAQ created successfully.")
            return redirect('superadmin:faq_list')
        return render(request, self.template_name, {'form': form, 'is_edit': False})


class FAQEditView(View):
    template_name = 'super_admin/faq/form.html'

    def get(self, request, pk):
        faq = get_object_or_404(FAQ, pk=pk)
        form = FAQForm(instance=faq)
        return render(request, self.template_name, {'form': form, 'faq': faq, 'is_edit': True})

    def post(self, request, pk):
        faq = get_object_or_404(FAQ, pk=pk)
        form = FAQForm(request.POST, instance=faq)
        if form.is_valid():
            form.save()
            messages.success(request, "FAQ updated successfully.")
            return redirect('superadmin:faq_list')
        return render(request, self.template_name, {'form': form, 'faq': faq, 'is_edit': True})


def faq_delete(request, pk):
    faq = get_object_or_404(FAQ, pk=pk)
    if request.method == 'POST':
        faq.delete()
        messages.success(request, "FAQ deleted.")
    return redirect('superadmin:faq_list')


def faq_toggle_active(request, pk):
    faq = get_object_or_404(FAQ, pk=pk)
    if request.method == 'POST':
        faq.is_active = not faq.is_active
        faq.save(update_fields=['is_active'])
        messages.success(request, f"'{faq.question}' is now {'active' if faq.is_active else 'inactive'}.")
    return redirect('superadmin:faq_list')


class ContactSubmissionListView(View):
    template_name = 'super_admin/contacts/list.html'

    def get(self, request):
        contacts = ContactUs.objects.order_by('-created_at')
        return render(request, self.template_name, {'contacts': contacts})


def contact_delete(request, pk):
    contact = get_object_or_404(ContactUs, pk=pk)
    if request.method == 'POST':
        contact.delete()
        messages.success(request, "Contact submission deleted.")
    return redirect('superadmin:contact_list')


class PackageRequestListView(View):
    template_name = 'super_admin/package_requests/list.html'

    def get(self, request):
        package_requests = PackageRequest.objects.order_by('-created_at')
        return render(request, self.template_name, {'package_requests': package_requests})


def package_request_delete(request, pk):
    pkg_request = get_object_or_404(PackageRequest, pk=pk)
    if request.method == 'POST':
        pkg_request.delete()
        messages.success(request, "Package request deleted.")
    return redirect('superadmin:package_request_list')


# ---------------------------------------------------------------------------
# Dynamic Feature Registry — add features/permissions with zero code changes.
# Additive layer alongside the legacy addOrg/editOrg flat checkbox grid above,
# which continues to control the original 31 hardcoded feature columns.
# ---------------------------------------------------------------------------

class FeatureRegistryView(View):
    template_name = 'super_admin/features/registry.html'

    def get(self, request):
        from handle.models import DynamicFeature
        from management.pricing_services import feature_catalog
        from school.permissions import PERMISSION_REGISTRY
        features = DynamicFeature.objects.all().prefetch_related('permissions').order_by('category', 'label')
        categories = [(c['slug'], c['label']) for c in PERMISSION_REGISTRY]
        return render(request, self.template_name, {
            'features': features,
            'categories': categories,
            'pricing_rows': feature_catalog(sync_missing=True),
        })

    def post(self, request):
        from decimal import Decimal, InvalidOperation
        from handle.models import DynamicFeature, DynamicPermission
        from management.models import FeaturePrice
        from management.pricing_services import sync_feature_price_catalog
        action = request.POST.get('action')

        if action == 'create_feature':
            key = slugify(request.POST.get('key', '')).replace('-', '_')
            label = request.POST.get('label', '').strip()
            if not key or not label:
                messages.error(request, "Key and label are required.")
                return redirect('superadmin:feature_registry')
            if key in FEATURE_MAP_KEYS():
                messages.error(request, f"'{key}' collides with a built-in feature key — choose another.")
                return redirect('superadmin:feature_registry')
            try:
                annual_price = Decimal(request.POST.get('annual_price', '0') or '0')
                if annual_price < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                messages.error(request, "Feature price must be zero or a positive amount.")
                return redirect('superadmin:feature_registry')
            feature, created = DynamicFeature.objects.get_or_create(key=key, defaults={
                'label': label,
                'icon': request.POST.get('icon', '').strip() or 'fa-puzzle-piece',
                'category': request.POST.get('category', '').strip(),
                'description': request.POST.get('description', '').strip(),
                'price': annual_price,
            })
            if created:
                FeaturePrice.objects.update_or_create(
                    feature_key=key,
                    defaults={
                        'label': label,
                        'annual_price': annual_price,
                        'is_active': True,
                        'is_public': request.POST.get('is_public') == 'on',
                        'updated_by': request.user if request.user.is_authenticated else None,
                    },
                )
                messages.success(request, f"Feature '{label}' created. Grant it to organizations from the org list.")
            else:
                messages.error(request, f"A feature with key '{key}' already exists.")

        elif action == 'toggle_active':
            feature = get_object_or_404(DynamicFeature, pk=request.POST.get('feature_id'))
            feature.is_active = not feature.is_active
            feature.save(update_fields=['is_active'])
            FeaturePrice.objects.filter(feature_key=feature.key).update(
                is_active=feature.is_active
            )
            messages.success(request, f"'{feature.label}' is now {'active' if feature.is_active else 'inactive'}.")

        elif action == 'delete_feature':
            feature = get_object_or_404(DynamicFeature, pk=request.POST.get('feature_id'))
            label = feature.label
            FeaturePrice.objects.filter(feature_key=feature.key).delete()
            feature.delete()
            messages.success(request, f"Feature '{label}' deleted (grants and permissions removed).")

        elif action == 'update_feature_price':
            sync_feature_price_catalog(
                request.user if request.user.is_authenticated else None
            )
            feature_price = get_object_or_404(
                FeaturePrice,
                feature_key=request.POST.get('feature_key'),
            )
            try:
                annual_price = Decimal(request.POST.get('annual_price', '') or '0')
                if annual_price < 0:
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                messages.error(request, "Feature price must be zero or a positive amount.")
                return redirect('superadmin:feature_registry')
            feature_price.annual_price = annual_price
            feature_price.is_public = request.POST.get('is_public') == 'on'
            feature_price.is_active = request.POST.get('is_active') == 'on'
            feature_price.updated_by = (
                request.user if request.user.is_authenticated else None
            )
            feature_price.save(
                update_fields=[
                    'annual_price',
                    'is_public',
                    'is_active',
                    'updated_by',
                    'updated_at',
                ]
            )
            DynamicFeature.objects.filter(key=feature_price.feature_key).update(
                price=annual_price,
                is_active=feature_price.is_active,
            )
            messages.success(
                request,
                f"{feature_price.label} rate updated to Rs {annual_price}/year.",
            )

        elif action == 'add_permission':
            feature = get_object_or_404(DynamicFeature, pk=request.POST.get('feature_id'))
            flag = slugify(request.POST.get('flag', '')).replace('-', '_')
            label = request.POST.get('perm_label', '').strip()
            if not flag.startswith('can_'):
                flag = f"can_{flag}" if flag else ''
            if not flag or not label:
                messages.error(request, "Permission flag and label are required.")
                return redirect('superadmin:feature_registry')
            _, created = DynamicPermission.objects.get_or_create(flag=flag, defaults={
                'label': label,
                'icon': request.POST.get('perm_icon', '').strip() or 'fa-check-circle',
                'feature': feature,
            })
            if created:
                messages.success(request, f"Permission '{label}' added to '{feature.label}'.")
            else:
                messages.error(request, f"A permission with flag '{flag}' already exists.")

        elif action == 'delete_permission':
            perm = get_object_or_404(DynamicPermission, pk=request.POST.get('permission_id'))
            perm.delete()
            messages.success(request, "Permission deleted.")

        return redirect('superadmin:feature_registry')


def FEATURE_MAP_KEYS():
    from school.features import FEATURE_MAP
    return set(FEATURE_MAP.keys())


class OrgFeatureGrantsView(View):
    """Per-org grant matrix for dynamic features, with bulk enable/disable and clone-from-org."""
    template_name = 'super_admin/features/org_grants.html'

    def get(self, request, org_id):
        from handle.models import DynamicFeature, OrganizationFeatureGrant
        org = get_object_or_404(Organization, pk=org_id)
        features = DynamicFeature.objects.filter(is_active=True).order_by('category', 'label')
        enabled_keys = set(
            OrganizationFeatureGrant.objects.filter(org=org, enabled=True).values_list('feature__key', flat=True)
        )
        rows = [{'feature': f, 'enabled': f.key in enabled_keys} for f in features]
        other_orgs = Organization.objects.exclude(pk=org.id).order_by('name')
        return render(request, self.template_name, {
            'org': org, 'rows': rows, 'other_orgs': other_orgs,
        })

    def post(self, request, org_id):
        from handle.models import DynamicFeature, OrganizationFeatureGrant
        from school.features import invalidate_org_feature_cache
        org = get_object_or_404(Organization, pk=org_id)
        action = request.POST.get('action')

        if action == 'save_grants':
            checked = set(request.POST.getlist('feature_key'))
            for feature in DynamicFeature.objects.filter(is_active=True):
                OrganizationFeatureGrant.objects.update_or_create(
                    org=org, feature=feature, defaults={'enabled': feature.key in checked}
                )
            messages.success(request, f"Feature grants updated for {org.name}.")

        elif action == 'enable_all':
            for feature in DynamicFeature.objects.filter(is_active=True):
                OrganizationFeatureGrant.objects.update_or_create(org=org, feature=feature, defaults={'enabled': True})
            messages.success(request, f"All features enabled for {org.name}.")

        elif action == 'disable_all':
            OrganizationFeatureGrant.objects.filter(org=org).update(enabled=False)
            messages.success(request, f"All features disabled for {org.name}.")

        elif action == 'clone_from':
            source = get_object_or_404(Organization, pk=request.POST.get('source_org_id'))
            source_grants = OrganizationFeatureGrant.objects.filter(org=source)
            for grant in source_grants:
                OrganizationFeatureGrant.objects.update_or_create(
                    org=org, feature=grant.feature, defaults={'enabled': grant.enabled}
                )
            messages.success(request, f"Cloned feature grants from {source.name}.")

        invalidate_org_feature_cache(org.id)
        return redirect('superadmin:org_feature_grants', org_id=org.id)
