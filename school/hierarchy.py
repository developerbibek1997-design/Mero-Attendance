"""
Reusable Organization -> Branch -> Classification -> Section -> Member
scoping service.

`school.permissions`/`school.features` answer "can this user use this
feature/permission at all?". This module answers a different question —
"which rows of the Branch/Classification/Section/Member hierarchy may this
user see or act on?" — so branch-scoping logic lives in one place instead of
being reimplemented per view/report.

Scoping only ever narrows for an actual Branch Manager (a user who is the
`manager` of at least one Branch). Everyone else — schooladmin, superadmin,
and regular staff with no managed branch — sees the whole organization, same
as before this module existed. This keeps the change additive: nothing that
already worked for existing staff silently loses access.
"""

from django.db.models import Q


def is_branch_manager(user, org=None):
    """True if `user` is the assigned manager of at least one Branch (optionally scoped to `org`)."""
    from handle.models import Branch
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'user_type', '') in ('1', '2'):
        return False  # org owners are never scoped, even if also set as a branch's manager
    qs = Branch.objects.filter(manager=user)
    if org is not None:
        qs = qs.filter(org=org)
    return qs.exists()


def managed_branch_ids(user, org):
    from handle.models import Branch
    return list(Branch.objects.filter(org=org, manager=user).values_list('id', flat=True))


def _scope_branch_ids(user, org):
    """None = unrestricted (sees every branch). A list = restricted to exactly these branch ids."""
    if org is not None and is_branch_manager(user, org):
        return managed_branch_ids(user, org)
    return None


def get_accessible_branches(user, org):
    """QuerySet of Branch objects `user` may act within, for `org`."""
    from handle.models import Branch
    if org is None:
        return Branch.objects.none()
    scope_ids = _scope_branch_ids(user, org)
    if scope_ids is None:
        return Branch.objects.filter(org=org)
    return Branch.objects.filter(org=org, pk__in=scope_ids)


def get_accessible_classifications(user, org, branch=None):
    """QuerySet of Classification objects `user` may see, optionally narrowed
    to one `branch`. A classification with no branches selected is org-wide
    and always included."""
    from handle.models import Classification
    if org is None:
        return Classification.objects.none()
    qs = Classification.objects.filter(org=org, status='active')
    scope_ids = _scope_branch_ids(user, org)
    if scope_ids is not None:
        if branch is not None and branch.id not in scope_ids:
            return Classification.objects.none()
        qs = qs.filter(Q(branches__isnull=True) | Q(branches__id__in=scope_ids)).distinct()
    if branch is not None:
        qs = qs.filter(Q(branches__isnull=True) | Q(branches=branch)).distinct()
    return qs


def get_accessible_sections(user, org, classification=None, branch=None):
    """QuerySet of Section objects `user` may see, optionally narrowed to one
    `classification` and/or `branch`. A section with no branch set is
    org-wide and always included."""
    from handle.models import Section
    if org is None:
        return Section.objects.none()
    qs = Section.objects.filter(org=org, status='active')
    if classification is not None:
        qs = qs.filter(classification=classification)
    if branch is not None:
        qs = qs.filter(Q(branch=branch) | Q(branch__isnull=True))
    scope_ids = _scope_branch_ids(user, org)
    if scope_ids is not None:
        if branch is not None and branch.id not in scope_ids:
            return Section.objects.none()
        qs = qs.filter(Q(branch_id__in=scope_ids) | Q(branch__isnull=True))
    return qs


def get_accessible_members(user, org, branch=None):
    """QuerySet of member objects `user` may see, optionally narrowed to one
    `branch`. A member with no branch set is org-wide and always included."""
    from handle.models import member as Member
    if org is None:
        return Member.objects.none()
    qs = Member.objects.filter(org=org)
    if branch is not None:
        qs = qs.filter(Q(branch=branch) | Q(branch__isnull=True))
    scope_ids = _scope_branch_ids(user, org)
    if scope_ids is not None:
        if branch is not None and branch.id not in scope_ids:
            return Member.objects.none()
        qs = qs.filter(Q(branch_id__in=scope_ids) | Q(branch__isnull=True))
    return qs
