"""
Centralized email notification utilities for the HRMS system.
All emails go through these helpers so formatting is consistent.
"""

from django.core.mail import send_mail, send_mass_mail
from django.conf import settings
import threading


FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@meroattendance.com')


def _send_async(subject, message, recipient_list, html_message=None):
    """Fire-and-forget email in a background thread so views don't block."""
    def _task():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=FROM_EMAIL,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=True,
            )
        except Exception:
            pass
    t = threading.Thread(target=_task, daemon=True)
    t.start()


# ── User / Account ───────────────────────────────────────────────────────────

def send_welcome_email(email, name, password, org_name):
    subject = f"Welcome to {org_name} — Your Account Details"
    body = f"""Hi {name},

Your account has been created on {org_name}'s portal.

Login: {email}
Password: {password}

Please log in and change your password immediately.

Regards,
{org_name} Team"""
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#1e293b;padding:24px;color:#fff;">
    <h2 style="margin:0;">Welcome to {org_name}</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>,</p>
    <p>Your account has been created. Here are your login details:</p>
    <table style="background:#f1f5f9;border-radius:6px;padding:16px;width:100%;border-spacing:0;">
      <tr><td style="color:#64748b;padding:4px 0;">Email</td><td><strong>{email}</strong></td></tr>
      <tr><td style="color:#64748b;padding:4px 0;">Password</td><td><strong>{password}</strong></td></tr>
    </table>
    <p style="color:#ef4444;margin-top:16px;"><strong>Please change your password after your first login.</strong></p>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">
    {org_name} &bull; Powered by Mero Attendance
  </div>
</div>"""
    _send_async(subject, body, [email], html)


# ── Leave ────────────────────────────────────────────────────────────────────

def send_leave_status_email(email, name, status, leave_type, start, end, remarks='', org_name=''):
    status_label = 'Approved ✓' if status == 'approved' else 'Rejected ✗'
    color = '#16a34a' if status == 'approved' else '#dc2626'
    subject = f"Leave Request {status_label} — {org_name}"
    body = f"Hi {name},\n\nYour {leave_type} leave from {start} to {end} has been {status}.\nRemarks: {remarks or 'N/A'}\n\n{org_name} Team"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:{color};padding:24px;color:#fff;">
    <h2 style="margin:0;">Leave {status_label}</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>,</p>
    <p>Your leave request has been <strong style="color:{color};">{status}</strong>.</p>
    <table style="background:#f1f5f9;border-radius:6px;padding:16px;width:100%;border-spacing:0;">
      <tr><td style="color:#64748b;padding:4px 8px;">Leave Type</td><td><strong>{leave_type}</strong></td></tr>
      <tr><td style="color:#64748b;padding:4px 8px;">From</td><td><strong>{start}</strong></td></tr>
      <tr><td style="color:#64748b;padding:4px 8px;">To</td><td><strong>{end}</strong></td></tr>
      {'<tr><td style="color:#64748b;padding:4px 8px;">Remarks</td><td>'+remarks+'</td></tr>' if remarks else ''}
    </table>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)


# ── Bill ─────────────────────────────────────────────────────────────────────

def send_bill_email(email, name, invoice_number, total_amount, due_date, items, org_name, remarks=''):
    subject = f"Invoice {invoice_number} — {org_name}"
    items_text = '\n'.join(f"  • {i['desc']}: Rs. {i['amount']}" for i in items)
    body = f"Hi {name},\n\nInvoice {invoice_number}\nDue: {due_date}\nTotal: Rs. {total_amount}\n\n{items_text}\n\n{org_name}"
    items_html = ''.join(
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;'>{i['desc']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;'>Rs. {i['amount']}</td></tr>"
        for i in items
    )
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#0f172a;padding:24px;color:#fff;display:flex;justify-content:space-between;align-items:center;">
    <div><h2 style="margin:0;">{org_name}</h2><p style="margin:4px 0 0;opacity:.7;font-size:14px;">Invoice</p></div>
    <div style="text-align:right;"><p style="margin:0;font-size:20px;font-weight:700;">{invoice_number}</p></div>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Dear <strong>{name}</strong>,</p>
    <p>Please find your invoice details below. Payment is due by <strong>{due_date}</strong>.</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <thead><tr style="background:#f1f5f9;">
        <th style="padding:10px 12px;text-align:left;font-size:13px;color:#64748b;">Description</th>
        <th style="padding:10px 12px;text-align:right;font-size:13px;color:#64748b;">Amount</th>
      </thead></tr>
      <tbody>{items_html}</tbody>
      <tfoot><tr style="background:#0f172a;color:#fff;">
        <td style="padding:12px;font-weight:700;">Total Due</td>
        <td style="padding:12px;text-align:right;font-weight:700;">Rs. {total_amount}</td>
      </tr></tfoot>
    </table>
    {'<p style="color:#64748b;font-size:13px;">Note: '+remarks+'</p>' if remarks else ''}
    <p style="margin-top:20px;">Please contact the administration if you have any questions.</p>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name} &bull; Powered by Mero Attendance</div>
</div>"""
    _send_async(subject, body, [email], html)


# ── Result ───────────────────────────────────────────────────────────────────

def send_result_email(email, name, exam_name, results, org_name):
    subject = f"Result Published: {exam_name} — {org_name}"
    rows = ''.join(
        f"<tr><td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;'>{r['subject']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:center;'>{r['marks']}/{r['full']}</td>"
        f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:center;"
        f"color:{'#16a34a' if r['passed'] else '#dc2626'};font-weight:600;'>{'Pass' if r['passed'] else 'Fail'}</td></tr>"
        for r in results
    )
    body = f"Hi {name},\n\nYour results for {exam_name} have been published.\n{org_name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#1e293b;padding:24px;color:#fff;">
    <h2 style="margin:0;">Result Published</h2>
    <p style="margin:4px 0 0;opacity:.7;">{exam_name}</p>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>, your results are ready:</p>
    <table style="width:100%;border-collapse:collapse;">
      <thead><tr style="background:#f1f5f9;">
        <th style="padding:10px 12px;text-align:left;font-size:13px;color:#64748b;">Subject</th>
        <th style="padding:10px 12px;text-align:center;font-size:13px;color:#64748b;">Marks</th>
        <th style="padding:10px 12px;text-align:center;font-size:13px;color:#64748b;">Status</th>
      </thead></tr>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)


# ── Resignation ───────────────────────────────────────────────────────────────

def send_resignation_status_email(email, name, status, last_working_day, org_name):
    color = '#16a34a' if status == 'approved' else ('#dc2626' if status == 'rejected' else '#f59e0b')
    subject = f"Resignation {status.title()} — {org_name}"
    body = f"Hi {name},\n\nYour resignation has been {status}.\nLast Working Day: {last_working_day or 'TBD'}\n\n{org_name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:{color};padding:24px;color:#fff;">
    <h2 style="margin:0;">Resignation {status.title()}</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>,</p>
    <p>Your resignation has been <strong>{status}</strong>.</p>
    <p>Last Working Day: <strong>{last_working_day or 'To be confirmed'}</strong></p>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)


# ── Payslip ───────────────────────────────────────────────────────────────────

def send_payslip_email(email, name, month_name, net_payable, org_name, details=None):
    subject = f"Payslip for {month_name} — {org_name}"
    body = f"Hi {name},\n\nYour payslip for {month_name} is ready.\nNet Payable: Rs. {net_payable}\n\n{org_name}"
    det_html = ''
    if details:
        det_html = ''.join(
            f"<tr><td style='padding:6px 12px;color:#64748b;'>{k}</td>"
            f"<td style='padding:6px 12px;text-align:right;'>{v}</td></tr>"
            for k, v in details.items()
        )
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#0f172a;padding:24px;color:#fff;">
    <h2 style="margin:0;">Payslip — {month_name}</h2>
    <p style="margin:4px 0 0;opacity:.7;">{org_name}</p>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>, your payslip is ready.</p>
    {'<table style="width:100%;border-collapse:collapse;">'+det_html+'</table>' if det_html else ''}
    <div style="background:#0f172a;color:#fff;border-radius:6px;padding:16px;margin-top:16px;display:flex;justify-content:space-between;">
      <span style="font-weight:600;">Net Payable</span>
      <span style="font-size:20px;font-weight:700;">Rs. {net_payable}</span>
    </div>
    <p style="margin-top:16px;">Log in to your portal to view the full breakdown.</p>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)


# ── Complaint ─────────────────────────────────────────────────────────────────

def send_task_assigned_email(email, name, task_title, due_date, priority, org_name, assigned_by='Admin'):
    subject = f"New Task Assigned — {org_name}"
    priority_color = {'low': '#22c55e', 'medium': '#3b82f6', 'high': '#f97316', 'urgent': '#ef4444'}.get(priority, '#6b7280')
    body = (f"Hi {name},\n\nA new task has been assigned to you by {assigned_by}.\n\n"
            f"Task: {task_title}\nPriority: {priority.upper()}\nDue Date: {due_date}\n\n"
            f"Log in to your portal to view the full details.\n\n{org_name}")
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#1e293b;padding:24px;color:#fff;">
    <h2 style="margin:0;font-size:20px;">📋 New Task Assigned</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>,</p>
    <p>You have a new task assigned by <strong>{assigned_by}</strong>.</p>
    <div style="background:#f8fafc;border-radius:8px;padding:16px;margin:16px 0;border-left:4px solid {priority_color};">
      <h3 style="margin:0 0 8px 0;color:#0f172a;">{task_title}</h3>
      <p style="margin:0;font-size:13px;"><span style="background:{priority_color};color:#fff;padding:2px 8px;border-radius:12px;font-size:12px;">{priority.upper()}</span></p>
      <p style="margin:8px 0 0;font-size:13px;color:#64748b;">Due: <strong>{due_date}</strong></p>
    </div>
    <p>Log in to your portal to view details and update the task status.</p>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)


def send_task_completed_email(admin_email, staff_name, task_title, completed_at, note, org_name):
    subject = f"Task Completed — {task_title}"
    body = f"Staff {staff_name} has marked task '{task_title}' as completed at {completed_at}.\nNote: {note or 'N/A'}\n\n{org_name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#16a34a;padding:24px;color:#fff;">
    <h2 style="margin:0;">✅ Task Completed</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p><strong>{staff_name}</strong> has completed the task <em>"{task_title}"</em>.</p>
    <p style="font-size:13px;color:#64748b;">Completed at: {completed_at}</p>
    {'<p><strong>Note:</strong> '+note+'</p>' if note else ''}
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [admin_email], html)


def send_task_overdue_email(admin_email, staff_name, task_title, due_date, org_name):
    subject = f"Task Overdue — {task_title}"
    body = f"Task '{task_title}' assigned to {staff_name} is overdue (due: {due_date}).\n\n{org_name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:#ef4444;padding:24px;color:#fff;">
    <h2 style="margin:0;">⚠️ Task Overdue</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Task <em>"{task_title}"</em> assigned to <strong>{staff_name}</strong> is now overdue.</p>
    <p style="font-size:13px;color:#64748b;">Due date was: {due_date}</p>
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [admin_email], html)


def send_task_approval_email(email, name, task_title, approval_status, reason, org_name):
    color = '#16a34a' if approval_status == 'approved' else '#ef4444'
    subject = f"Task {approval_status.title()} — {org_name}"
    body = f"Hi {name},\n\nYour completed task '{task_title}' has been {approval_status}.\nReason: {reason or 'N/A'}\n\n{org_name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:{color};padding:24px;color:#fff;">
    <h2 style="margin:0;">Task {approval_status.title()}</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>,</p>
    <p>Your completed task <em>"{task_title}"</em> has been <strong>{approval_status}</strong>.</p>
    {'<p><strong>Reason:</strong> '+reason+'</p>' if reason else ''}
    {'<p style="color:#ef4444;">The task has been returned to rework required status.</p>' if approval_status == 'rejected' else ''}
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)


def send_complaint_update_email(email, name, subject_text, status, remarks, org_name):
    color = '#16a34a' if status == 'resolved' else '#f59e0b'
    subject = f"Complaint Update — {org_name}"
    body = f"Hi {name},\n\nYour complaint '{subject_text}' status: {status}.\nRemarks: {remarks or 'N/A'}\n\n{org_name}"
    html = f"""
<div style="font-family:Arial,sans-serif;max-width:560px;margin:auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
  <div style="background:{color};padding:24px;color:#fff;">
    <h2 style="margin:0;">Complaint {status.title()}</h2>
  </div>
  <div style="padding:24px;color:#334155;">
    <p>Hi <strong>{name}</strong>,</p>
    <p>Your complaint <em>"{subject_text}"</em> has been updated to <strong>{status}</strong>.</p>
    {'<p>Remarks: '+remarks+'</p>' if remarks else ''}
  </div>
  <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:12px;">{org_name}</div>
</div>"""
    _send_async(subject, body, [email], html)
