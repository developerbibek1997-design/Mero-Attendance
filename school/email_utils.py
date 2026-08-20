"""
Centralized email notification utilities.

Every outgoing email routes through `_send_email()`, which:
  - renders a real .html template under templates/basic/email/ (instead of
    an inline Python f-string), with the shared header/footer partial and
    the Play Store / App Store / Web Dashboard links merged in automatically
  - logs the attempt to EmailLog (pending -> sent/failed), so a failure is
    never silent and an admin can see + resend it
  - skips a recipient if a non-failed EmailLog already exists for the same
    (recipient, email_type, related_object) — prevents duplicate sends for
    the same event (e.g. a double form submit)
  - sends in a background thread so views don't block
"""

import threading

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags


def _with_pdf_attachment(attachments, pdf_template, pdf_context, filename):
    """Render pdf_template to PDF bytes and prepend it to `attachments` (list of (filename, bytes, mimetype)). Never raises — a PDF failure shouldn't block the email itself."""
    try:
        from school.pdf_utils import render_to_pdf
        pdf_bytes = render_to_pdf(f'basic/pdf/{pdf_template}.html', pdf_context)
        if pdf_bytes:
            return [(filename, pdf_bytes, 'application/pdf')] + list(attachments or [])
    except Exception:
        pass
    return attachments


def _app_links():
    return {
        'play_store_url': getattr(settings, 'PLAY_STORE_URL', ''),
        'app_store_url': getattr(settings, 'APP_STORE_URL', ''),
        'web_dashboard_url': getattr(settings, 'WEB_DASHBOARD_URL', ''),
    }


def _send_email(template_name, context, subject, recipient_list, email_type='other',
                 org=None, related_object_type='', related_object_id=None, attachments=None,
                 force=False):
    """
    Render templates/basic/email/{template_name}.html with `context` (app
    download links merged in automatically), create a pending EmailLog per
    recipient (skipping recipients that already have a non-failed log for
    this exact email_type + related_object — dedup), then send in a
    background thread and flip each log to sent/failed.

    `force=True` bypasses the dedup check — for explicit user-triggered
    resends, where sending again is the whole point.
    """
    from handle.models import EmailLog

    ctx = {**context, **_app_links()}
    html_message = render_to_string(f'basic/email/{template_name}.html', ctx)
    text_message = strip_tags(html_message)

    to_send = []
    for email in recipient_list:
        if not email:
            continue
        already_handled = (not force) and EmailLog.objects.filter(
            recipient_email=email, email_type=email_type, related_object_id=related_object_id,
        ).exclude(status='failed').exists()
        if already_handled:
            continue
        log = EmailLog.objects.create(
            org=org, recipient_email=email, recipient_name=context.get('name', '') or context.get('member_name', ''),
            email_type=email_type, subject=subject, status='pending',
            related_object_type=related_object_type, related_object_id=related_object_id,
        )
        to_send.append((email, log))

    if not to_send:
        return

    def _task():
        for email, log in to_send:
            try:
                msg = EmailMultiAlternatives(subject=subject, body=text_message, to=[email])
                msg.attach_alternative(html_message, "text/html")
                for filename, content, mimetype in (attachments or []):
                    msg.attach(filename, content, mimetype)
                msg.send(fail_silently=False)
                log.status = 'sent'
                log.sent_at = timezone.now()
                log.save(update_fields=['status', 'sent_at'])
            except Exception as e:
                log.status = 'failed'
                log.error_message = str(e)[:2000]
                log.save(update_fields=['status', 'error_message'])

    threading.Thread(target=_task, daemon=True).start()


# ── User / Account ───────────────────────────────────────────────────────────

def send_welcome_email(email, name, password, org_name, org=None, login_url=None):
    context = {
        'name': name, 'email': email, 'password': password, 'org_name': org_name,
        'login_url': login_url or getattr(settings, 'WEB_DASHBOARD_URL', ''),
    }
    _send_email('welcome', context, f"Welcome to {org_name} — Your Account Details", [email],
                email_type='welcome', org=org, related_object_type='CustomUser')


# ── Leave ────────────────────────────────────────────────────────────────────

def send_leave_status_email(email, name, status, leave_type, start, end, remarks='', org_name='',
                             org=None, related_object_id=None, force=False):
    email_type = 'leave_approved' if status == 'approved' else 'leave_rejected'
    status_label = 'Approved' if status == 'approved' else 'Rejected'
    context = {'name': name, 'status': status, 'status_label': status_label, 'leave_type': leave_type,
               'start': start, 'end': end, 'remarks': remarks, 'org_name': org_name}
    _send_email('leave_status', context, f"Leave Request {status_label} — {org_name}", [email],
                email_type=email_type, org=org, related_object_type='LeaveReport', related_object_id=related_object_id,
                force=force)


def send_leave_submitted_email(admin_emails, member_name, leave_type, start, end, reason, org_name,
                                org=None, related_object_id=None, force=False):
    context = {'member_name': member_name, 'leave_type': leave_type, 'start': start, 'end': end,
               'reason': reason, 'org_name': org_name}
    _send_email('leave_submitted', context, f"New Leave Request — {member_name}", admin_emails,
                email_type='leave_submitted', org=org, related_object_type='LeaveReport', related_object_id=related_object_id,
                force=force)


def send_leave_cancelled_email(email, name, leave_type, start, end, org_name, org=None, related_object_id=None, force=False):
    context = {'name': name, 'leave_type': leave_type, 'start': start, 'end': end, 'org_name': org_name}
    _send_email('leave_cancelled', context, f"Leave Request Cancelled — {org_name}", [email],
                email_type='leave_cancelled', org=org, related_object_type='LeaveReport', related_object_id=related_object_id,
                force=force)


# ── Bill ─────────────────────────────────────────────────────────────────────

def send_bill_email(email, name, invoice_number, total_amount, due_date, items, org_name, remarks='',
                     org=None, related_object_id=None, attachments=None, force=False):
    context = {'name': name, 'invoice_number': invoice_number, 'total_amount': total_amount,
               'due_date': due_date, 'items': items, 'org_name': org_name, 'remarks': remarks}
    attachments = _with_pdf_attachment(attachments, 'bill', context, f"Invoice_{invoice_number}.pdf")
    _send_email('bill', context, f"Invoice {invoice_number} — {org_name}", [email],
                email_type='bill', org=org, related_object_type='Bill', related_object_id=related_object_id,
                attachments=attachments, force=force)


def send_payment_receipt_email(email, name, invoice_number, amount_paid, balance_due, org_name,
                                org=None, related_object_id=None, attachments=None, force=False):
    context = {'name': name, 'invoice_number': invoice_number, 'amount_paid': amount_paid,
               'balance_due': balance_due, 'org_name': org_name}
    _send_email('payment_receipt', context, f"Payment Received — {invoice_number} — {org_name}", [email],
                email_type='payment_receipt', org=org, related_object_type='Bill', related_object_id=related_object_id,
                attachments=attachments, force=force)


# ── Result ───────────────────────────────────────────────────────────────────

def send_result_email(email, name, exam_name, results, org_name, org=None, related_object_id=None,
                       attachments=None, force=False):
    context = {'name': name, 'exam_name': exam_name, 'results': results, 'org_name': org_name}
    attachments = _with_pdf_attachment(attachments, 'result', context, f"Result_{exam_name}.pdf".replace(' ', '_'))
    _send_email('result', context, f"Result Published: {exam_name} — {org_name}", [email],
                email_type='result', org=org, related_object_type='ExamTerm', related_object_id=related_object_id,
                attachments=attachments, force=force)


# ── Resignation ───────────────────────────────────────────────────────────────

def send_resignation_status_email(email, name, status, last_working_day, org_name, org=None, related_object_id=None, force=False):
    context = {'name': name, 'status': status, 'last_working_day': last_working_day, 'org_name': org_name}
    _send_email('resignation_status', context, f"Resignation {status.title()} — {org_name}", [email],
                email_type='resignation', org=org, related_object_type='ResignationRecord', related_object_id=related_object_id,
                force=force)


# ── Payslip ───────────────────────────────────────────────────────────────────

def send_payslip_email(email, name, month_name, net_payable, org_name, details=None,
                        org=None, related_object_id=None, attachments=None, force=False):
    context = {'name': name, 'month_name': month_name, 'net_payable': net_payable,
               'org_name': org_name, 'details': details or {}}
    attachments = _with_pdf_attachment(attachments, 'payslip', context, f"Payslip_{month_name}.pdf".replace(' ', '_'))
    _send_email('payslip', context, f"Payslip for {month_name} — {org_name}", [email],
                email_type='payslip', org=org, related_object_type='PaySlip', related_object_id=related_object_id,
                attachments=attachments, force=force)


# ── Tasks ────────────────────────────────────────────────────────────────────

def send_task_assigned_email(email, name, task_title, due_date, priority, org_name, assigned_by='Admin',
                              org=None, related_object_id=None, force=False):
    context = {'name': name, 'task_title': task_title, 'due_date': due_date, 'priority': priority,
               'org_name': org_name, 'assigned_by': assigned_by}
    _send_email('task_assigned', context, f"New Task Assigned — {org_name}", [email],
                email_type='task_assigned', org=org, related_object_type='Task', related_object_id=related_object_id,
                force=force)


def send_task_completed_email(admin_email, staff_name, task_title, completed_at, note, org_name,
                               org=None, related_object_id=None, force=False):
    context = {'staff_name': staff_name, 'task_title': task_title, 'completed_at': completed_at,
               'note': note, 'org_name': org_name}
    _send_email('task_completed', context, f"Task Completed — {task_title}", [admin_email],
                email_type='task_completed', org=org, related_object_type='TaskInstance', related_object_id=related_object_id,
                force=force)


def send_task_overdue_email(admin_email, staff_name, task_title, due_date, org_name, org=None, related_object_id=None, force=False):
    context = {'staff_name': staff_name, 'task_title': task_title, 'due_date': due_date, 'org_name': org_name}
    _send_email('task_overdue', context, f"Task Overdue — {task_title}", [admin_email],
                email_type='task_overdue', org=org, related_object_type='TaskInstance', related_object_id=related_object_id,
                force=force)


def send_task_approval_email(email, name, task_title, approval_status, reason, org_name, org=None, related_object_id=None, force=False):
    context = {'name': name, 'task_title': task_title, 'approval_status': approval_status,
               'reason': reason, 'org_name': org_name}
    _send_email('task_approval', context, f"Task {approval_status.title()} — {org_name}", [email],
                email_type='task_approval', org=org, related_object_type='TaskInstance', related_object_id=related_object_id,
                force=force)


# ── Complaints ───────────────────────────────────────────────────────────────

def send_complaint_update_email(email, name, subject_text, status, remarks, org_name, org=None, related_object_id=None, force=False):
    context = {'name': name, 'subject_text': subject_text, 'status': status, 'remarks': remarks, 'org_name': org_name}
    _send_email('complaint_update', context, f"Complaint Update — {org_name}", [email],
                email_type='complaint', org=org, related_object_type='Complaint', related_object_id=related_object_id,
                force=force)


# ── Notices ──────────────────────────────────────────────────────────────────

def send_notice_email(recipient_emails, title, body, priority, org_name, published_on='',
                       org=None, related_object_id=None, attachments=None, force=False):
    """Email a published notice to its resolved recipients. Dedup is keyed on
    (recipient, 'notice', notice_id), so re-saving a notice never double-sends
    unless the admin explicitly resends (force=True)."""
    context = {'title': title, 'body': body, 'priority': priority,
               'priority_label': priority.title(), 'org_name': org_name,
               'published_on': published_on}
    _send_email('notice', context, f"{org_name}: {title}", recipient_emails,
                email_type='notice', org=org, related_object_type='Notice',
                related_object_id=related_object_id, attachments=attachments, force=force)


def send_broadcast_message_email(recipient_emails, subject, body, org_name, org=None):
    """A one-off admin broadcast (Operations -> Messages). Always `force=True`:
    unlike a Notice (which has a stable id to dedupe resends against), every
    Send click here is a deliberate new message with no persisted object, so
    the normal EmailLog dedup would otherwise silently swallow every send to
    a recipient after their first ever broadcast."""
    context = {'title': subject, 'body': body, 'priority': 'normal',
               'priority_label': 'Message', 'org_name': org_name, 'published_on': ''}
    _send_email('notice', context, f"{org_name}: {subject}", recipient_emails,
                email_type='broadcast_message', org=org, related_object_type='OperationsBroadcast',
                force=True)


# ── Academic Management ──────────────────────────────────────────────────────

def send_assignment_assigned_email(email, name, assignment_title, subject_name, due_date, org_name,
                                    org=None, related_object_id=None, force=False):
    context = {'name': name, 'assignment_title': assignment_title, 'subject_name': subject_name,
               'due_date': due_date, 'org_name': org_name}
    _send_email('assignment_assigned', context, f"New Assignment: {assignment_title} — {org_name}", [email],
                email_type='assignment_assigned', org=org, related_object_type='Assignment',
                related_object_id=related_object_id, force=force)


def send_assignment_graded_email(email, name, assignment_title, obtained_marks, total_marks, org_name,
                                  org=None, related_object_id=None, force=False):
    context = {'name': name, 'assignment_title': assignment_title, 'obtained_marks': obtained_marks,
               'total_marks': total_marks, 'org_name': org_name}
    _send_email('assignment_graded', context, f"Graded: {assignment_title} — {org_name}", [email],
                email_type='marks_published', org=org, related_object_type='AssignmentSubmission',
                related_object_id=related_object_id, force=force)


# ── Attendance ───────────────────────────────────────────────────────────────

def send_attendance_summary_email(email, name, period_label, summary, org_name, org=None, related_object_id=None):
    """summary: dict like {'present': int, 'absent': int, 'leave': int, 'total_days': int}."""
    context = {'name': name, 'period_label': period_label, 'summary': summary, 'org_name': org_name}
    _send_email('attendance_summary', context, f"Attendance Summary — {period_label} — {org_name}", [email],
                email_type='attendance_summary', org=org, related_object_type='member', related_object_id=related_object_id)


# ── Admin resend (re-derives from the related object's current state) ────────

def resend_email_log(log):
    """
    Re-derive and resend a failed EmailLog entry from the current state of
    its related object, targeted only at the original recipient (never the
    whole audience again). Returns (ok: bool, message: str).
    """
    from handle.models import (
        PaySlip, Bill, ExamTerm, ResultRecord, ResignationRecord, Complaint, Task, TaskInstance,
    )
    from management.models import LeaveReport

    et = log.email_type
    org = log.org
    email = log.recipient_email
    oid = log.related_object_id
    org_name = org.name if org else ''

    try:
        if et in ('leave_approved', 'leave_rejected'):
            report = LeaveReport.objects.get(pk=oid)
            status = 'approved' if report.approved else 'rejected'
            lt_name = report.leave_type.name if report.leave_type else 'Leave'
            send_leave_status_email(
                email=email, name=report.member.name, status=status, leave_type=lt_name,
                start=str(report.gap_start), end=str(report.gap_end), org_name=org_name,
                org=org, related_object_id=report.id, force=True,
            )
            return True, "Resent."

        if et == 'leave_submitted':
            report = LeaveReport.objects.get(pk=oid)
            lt_name = report.leave_type.name if report.leave_type else 'Leave'
            send_leave_submitted_email(
                admin_emails=[email], member_name=report.member.name, leave_type=lt_name,
                start=str(report.gap_start), end=str(report.gap_end), reason=report.reason or '',
                org_name=org_name, org=org, related_object_id=report.id, force=True,
            )
            return True, "Resent."

        if et in ('bill', 'payment_receipt'):
            bill = Bill.objects.get(pk=oid)
            if et == 'bill':
                items = [{'desc': i.description, 'amount': i.amount} for i in bill.items.all()]
                send_bill_email(
                    email=email, name=bill.member.name, invoice_number=bill.invoice_number,
                    total_amount=bill.total_amount, due_date=bill.due_date, items=items,
                    org_name=org_name, remarks=bill.remarks or '',
                    org=org, related_object_id=bill.id, force=True,
                )
            else:
                send_payment_receipt_email(
                    email=email, name=bill.member.name, invoice_number=bill.invoice_number,
                    amount_paid=bill.amount_paid, balance_due=bill.total_amount - bill.amount_paid,
                    org_name=org_name, org=org, related_object_id=bill.id, force=True,
                )
            return True, "Resent."

        if et == 'result':
            exam = ExamTerm.objects.get(pk=oid)
            records = ResultRecord.objects.filter(exam=exam).select_related('student', 'subject')
            target_member = None
            for r in records:
                if r.student.email == email or getattr(r.student, 'guardian_email', '') == email:
                    target_member = r.student
                    break
            if not target_member:
                return False, "Could not find a matching student/guardian for this recipient."
            results = [
                {'subject': r.subject.name, 'marks': r.obtained_marks, 'full': r.subject.full_marks, 'passed': r.is_passed}
                for r in records.filter(student=target_member)
            ]
            send_result_email(
                email=email, name=target_member.name, exam_name=exam.name, results=results,
                org_name=org_name, org=org, related_object_id=exam.id, force=True,
            )
            return True, "Resent."

        if et == 'payslip':
            slip = PaySlip.objects.get(pk=oid)
            send_payslip_email(
                email=email, name=slip.member.name, month_name=slip.month_name, net_payable=slip.net_payable,
                org_name=org_name,
                details={
                    'Gross Salary': f"Rs. {slip.gross_salary}", 'Allowances': f"Rs. {slip.allowance_total}",
                    'Deductions': f"Rs. {slip.advance_deduction + slip.loan_deduction}",
                    'PF': f"Rs. {slip.pf_employee}", 'Tax': f"Rs. {slip.tax_deduction}",
                    'Present Days': slip.present_days, 'Total Days': slip.total_days,
                },
                org=org, related_object_id=slip.id, force=True,
            )
            return True, "Resent."

        if et == 'resignation':
            rec = ResignationRecord.objects.get(pk=oid)
            send_resignation_status_email(
                email=email, name=rec.member.name, status=rec.status, last_working_day=rec.last_working_day,
                org_name=org_name, org=org, related_object_id=rec.id, force=True,
            )
            return True, "Resent."

        if et == 'complaint':
            c = Complaint.objects.get(pk=oid)
            send_complaint_update_email(
                email=email, name=c.filed_by.name, subject_text=c.subject, status=c.status,
                remarks=c.admin_remarks or '', org_name=org_name, org=org,
                related_object_id=c.id, force=True,
            )
            return True, "Resent."

        if et == 'task_assigned':
            task = Task.objects.get(pk=oid)
            target = task.assigned_to.filter(email=email).first()
            if not target:
                return False, "Could not find the assignee for this recipient."
            send_task_assigned_email(
                email=email, name=target.name, task_title=task.title, due_date=task.due_date,
                priority=task.priority, org_name=org_name, org=org,
                related_object_id=task.id, force=True,
            )
            return True, "Resent."

        if et in ('task_completed', 'task_overdue', 'task_approval'):
            inst = TaskInstance.objects.get(pk=oid)
            if et == 'task_completed':
                send_task_completed_email(
                    admin_email=email, staff_name=inst.assigned_member.name, task_title=inst.task.title,
                    completed_at=inst.completed_at, note=inst.completion_note, org_name=org_name,
                    org=org, related_object_id=inst.id, force=True,
                )
            elif et == 'task_overdue':
                send_task_overdue_email(
                    admin_email=email, staff_name=inst.assigned_member.name, task_title=inst.task.title,
                    due_date=inst.due_date, org_name=org_name, org=org,
                    related_object_id=inst.id, force=True,
                )
            else:
                send_task_approval_email(
                    email=email, name=inst.assigned_member.name, task_title=inst.task.title,
                    approval_status=inst.approval_status, reason=inst.not_done_detail or '',
                    org_name=org_name, org=org, related_object_id=inst.id, force=True,
                )
            return True, "Resent."

        return False, f"Auto-resend isn't supported for '{log.get_email_type_display()}' emails — the source record may no longer exist or hold enough context."
    except Exception as e:
        return False, f"Couldn't resend: {e}"
