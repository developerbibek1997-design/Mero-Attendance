"""Reusable services shared by the Member create/edit/import flows.

Granting a Member dashboard access (creating the CustomUser + Staff link) used
to be implemented three separate times — AddMember, memberEdit, and the bulk
Excel importer — each with slightly different guards. `provision_staff_account`
is the single place that logic lives now.
"""

from management.models import CustomUser
from .models import Staff


class StaffProvisionResult:
    __slots__ = ('status', 'message', 'user', 'password')

    def __init__(self, status, message, user=None, password=None):
        # status: 'created' | 'already_exists' | 'email_conflict' | 'missing_info'
        self.status = status
        self.message = message
        self.user = user
        self.password = password


def provision_staff_account(mem, org):
    """Create/link the CustomUser + Staff row that gives `mem` dashboard access.

    DB-only — does not send the welcome email. Callers should send it
    themselves (with the returned `.password`) only after their own
    transaction has committed, so a rollback can never leave credentials
    emailed for a member that doesn't actually exist.
    """
    if Staff.objects.filter(member=mem).exists():
        return StaffProvisionResult(
            'already_exists',
            f"{mem.name} already has portal access — no new credentials email was sent.",
        )

    if not (mem.email and mem.phone):
        return StaffProvisionResult(
            'missing_info',
            "Add both an email and a phone number to grant portal access — credentials can't be emailed without them.",
        )

    if CustomUser.objects.filter(email=mem.email).exists():
        return StaffProvisionResult(
            'email_conflict',
            f"Couldn't grant portal access — the email '{mem.email}' is already used by another account.",
        )

    password = str(mem.phone)
    user = CustomUser.objects.create_user(
        first_name=mem.name, last_name=mem.name,
        email=mem.email, username=mem.email, password=password,
    )
    user.user_type = "3"
    user.save(update_fields=['user_type'])
    Staff.objects.create(member=mem, admin=user, org=org, number=mem.phone)

    return StaffProvisionResult('created', 'Dashboard access created.', user=user, password=password)
