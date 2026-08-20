from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseForbidden
from django.utils import timezone

from management.models import (
    AgentProfile, AgentLedger, AgentActivityLog,
    Organization, Schooladmin, CustomUser
)
from .decorators import agent_required, get_agent_profile, check_agent_org_ownership
from .forms import AgentAddOrgForm, AgentEditOrgForm, AgentProfileForm


def _log(agent, action, org=None, description='', request=None):
    ip = None
    if request:
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded.split(',')[0] if x_forwarded else request.META.get('REMOTE_ADDR')
    AgentActivityLog.objects.create(
        agent=agent, action=action, organization=org,
        description=description, ip_address=ip
    )


class AgentDashboard(View):
    template_name = 'agent/dashboard.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        orgs = agent.organizations.all()
        total_orgs = orgs.count()
        active_orgs = orgs.filter(activate=True).count()
        total_commission = sum(
            e.commission_amount for e in agent.ledger_entries.filter(payment_status='paid')
        )
        pending_commission = sum(
            e.commission_amount for e in agent.ledger_entries.filter(payment_status='unpaid')
        )
        recent_activity = agent.activity_logs.all()[:10]
        return render(request, self.template_name, {
            'agent': agent,
            'orgs': orgs,
            'total_orgs': total_orgs,
            'active_orgs': active_orgs,
            'total_commission': total_commission,
            'pending_commission': pending_commission,
            'recent_activity': recent_activity,
        })


class AgentOrgList(View):
    template_name = 'agent/organizations.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        orgs = agent.organizations.all().order_by('-id')
        return render(request, self.template_name, {'agent': agent, 'orgs': orgs})


class AgentAddOrg(View):
    template_name = 'agent/add_org.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        if not agent.can_add_org():
            messages.error(request, "You have reached your organization limit or are not allowed to create organizations.")
            return redirect('agent:org_list')
        form = AgentAddOrgForm()
        return render(request, self.template_name, {'agent': agent, 'form': form})

    @agent_required
    def post(self, request):
        agent = get_agent_profile(request)
        if not agent.can_add_org():
            messages.error(request, "You have reached your organization limit.")
            return redirect('agent:org_list')

        form = AgentAddOrgForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    org = form.save(commit=False)
                    org.agent = agent
                    org.created_by_agent = True
                    org.org_status = 'trial'
                    org.payment_status = 'trial'
                    org.new_serial_key = form.cleaned_data.get('serial_key', '')
                    org.save()

                    user = CustomUser.objects.create_user(
                        username=form.cleaned_data['admin_email'],
                        email=form.cleaned_data['admin_email'],
                        password=form.cleaned_data['admin_password'],
                        first_name=form.cleaned_data['admin_first_name'],
                        last_name=form.cleaned_data.get('admin_last_name', ''),
                        user_type='2',
                    )
                    Schooladmin.objects.create(admin=user, org=org)

                    _log(agent, 'CREATE_ORG', org=org,
                         description=f"Created organization: {org.name}", request=request)

                messages.success(request, f"Organization '{org.name}' created successfully with admin account.")
                return redirect('agent:org_detail', org_id=org.id)
            except Exception as e:
                messages.error(request, f"Error creating organization: {e}")
        return render(request, self.template_name, {'agent': agent, 'form': form})


class AgentOrgDetail(View):
    template_name = 'agent/org_detail.html'

    @agent_required
    def get(self, request, org_id):
        agent = get_agent_profile(request)
        org = check_agent_org_ownership(agent, org_id)
        if not org:
            return HttpResponseForbidden("You do not have access to this organization.")
        admins = Schooladmin.objects.filter(org=org).select_related('admin')
        ledger = AgentLedger.objects.filter(agent=agent, organization=org).order_by('-created_at')
        return render(request, self.template_name, {
            'agent': agent, 'org': org, 'admins': admins, 'ledger': ledger
        })


class AgentEditOrg(View):
    template_name = 'agent/org_edit.html'

    @agent_required
    def get(self, request, org_id):
        agent = get_agent_profile(request)
        org = check_agent_org_ownership(agent, org_id)
        if not org:
            return HttpResponseForbidden("You do not have access to this organization.")
        form = AgentEditOrgForm(instance=org)
        return render(request, self.template_name, {'agent': agent, 'org': org, 'form': form})

    @agent_required
    def post(self, request, org_id):
        agent = get_agent_profile(request)
        org = check_agent_org_ownership(agent, org_id)
        if not org:
            return HttpResponseForbidden("You do not have access to this organization.")
        form = AgentEditOrgForm(request.POST, request.FILES, instance=org)
        if form.is_valid():
            form.save()
            _log(agent, 'EDIT_ORG', org=org,
                 description=f"Edited organization: {org.name}", request=request)
            messages.success(request, "Organization updated successfully.")
            return redirect('agent:org_detail', org_id=org.id)
        return render(request, self.template_name, {'agent': agent, 'org': org, 'form': form})


class AgentBilling(View):
    template_name = 'agent/billing.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        ledger = agent.ledger_entries.all().order_by('-created_at').select_related('organization')
        total_paid = sum(e.amount for e in ledger.filter(payment_status='paid'))
        total_unpaid = sum(e.amount for e in ledger.filter(payment_status='unpaid'))
        return render(request, self.template_name, {
            'agent': agent, 'ledger': ledger,
            'total_paid': total_paid, 'total_unpaid': total_unpaid
        })


class AgentCommission(View):
    template_name = 'agent/commission.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        entries = agent.ledger_entries.all().order_by('-created_at').select_related('organization')
        total_earned = sum(e.commission_amount for e in entries.filter(payment_status='paid'))
        total_pending = sum(e.commission_amount for e in entries.filter(payment_status='unpaid'))
        return render(request, self.template_name, {
            'agent': agent, 'entries': entries,
            'total_earned': total_earned, 'total_pending': total_pending
        })


class AgentReports(View):
    template_name = 'agent/reports.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        if not agent.allowed_to_view_reports:
            return HttpResponseForbidden("You are not allowed to view reports.")
        orgs = agent.organizations.all()
        active_count = orgs.filter(activate=True).count()
        inactive_count = orgs.filter(activate=False).count()
        org_by_status = {
            'active': orgs.filter(org_status='active').count(),
            'trial': orgs.filter(org_status='trial').count(),
            'expired': orgs.filter(org_status='expired').count(),
            'suspended': orgs.filter(org_status='suspended').count(),
        }
        return render(request, self.template_name, {
            'agent': agent, 'orgs': orgs,
            'active_count': active_count, 'inactive_count': inactive_count,
            'org_by_status': org_by_status,
        })


class AgentProfileView(View):
    template_name = 'agent/profile.html'

    @agent_required
    def get(self, request):
        agent = get_agent_profile(request)
        form = AgentProfileForm(instance=agent)
        return render(request, self.template_name, {'agent': agent, 'form': form})

    @agent_required
    def post(self, request):
        agent = get_agent_profile(request)
        form = AgentProfileForm(request.POST, request.FILES, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully.")
            return redirect('agent:profile')
        return render(request, self.template_name, {'agent': agent, 'form': form})
