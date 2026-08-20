"""Canonical organization feature, preset, pricing, and expiry helpers.

The superadmin organization form intentionally uses this module as the single
source of truth. A selected feature is both enabled on the organization and
allowed by its subscription plan, avoiding the two-checkbox states that
previously drifted apart.
"""

from collections import OrderedDict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from handle.models import DynamicFeature, OrganizationFeatureGrant
from management.models import FeaturePrice
from management.pricing_services import member_package_price
from school.features import (
    FEATURE_KEY_LABELS,
    FEATURE_MAP,
    FREE_FEATURES,
    feature_price,
    invalidate_org_feature_cache,
)


FEATURE_DEPENDENCIES = {
    "results": {"courses"},
    "study_gap": {"courses"},
    "billing": {"student_mgmt"},
}

FEATURE_GROUPS = OrderedDict(
    [
        (
            "academic",
            {
                "label": "Academic & Student",
                "icon": "fa-graduation-cap",
                "description": "Courses, students, results, billing and teaching workflows.",
                "keys": (
                    "courses",
                    "student_mgmt",
                    "results",
                    "billing",
                    "study_gap",
                    "complaints",
                    "events",
                    "notices",
                ),
            },
        ),
        (
            "workforce",
            {
                "label": "People & Workforce",
                "icon": "fa-users-gear",
                "description": "Staff, payroll, leave, tasks and field workforce tools.",
                "keys": (
                    "member_mgmt",
                    "hrms",
                    "payroll",
                    "leave",
                    "timesheet",
                    "tasks",
                    "id_cards",
                    "field_visits",
                    "clients",
                    "branches",
                ),
            },
        ),
        (
            "attendance",
            {
                "label": "Attendance & Automation",
                "icon": "fa-fingerprint",
                "description": "Choose every attendance method and calendar capability in one place.",
                "keys": (
                    "biometric",
                    "qr",
                    "gps",
                    "manual",
                    "wifi",
                    "qr_attendance",
                    "face_attendance",
                    "nepali_cal",
                    "notifications",
                ),
            },
        ),
        (
            "business",
            {
                "label": "Business & Operations",
                "icon": "fa-chart-line",
                "description": "Finance, inventory, exports and operational add-ons.",
                "keys": ("finance", "stock", "bulk_export"),
            },
        ),
    ]
)

FEATURE_DESCRIPTIONS = {
    "courses": "Course, classification, section, subject and routine setup.",
    "student_mgmt": "Student profiles, enrolment and student portal.",
    "results": "Exams, marks, grade sheets and result publishing.",
    "billing": "Student bills, payments and billing reports.",
    "study_gap": "Teaching log and study-gap tracking.",
    "complaints": "Complaints, requests and resolution workflow.",
    "events": "Organization events and calendar activities.",
    "notices": "Notices and announcements for portal users.",
    "member_mgmt": "Core staff and member directory. Always enabled.",
    "hrms": "HR documents, resignation and employee lifecycle.",
    "payroll": "Payroll runs, salary records and payslips.",
    "leave": "Leave requests, approvals and balances.",
    "timesheet": "Daily timesheets and approval workflow.",
    "tasks": "Assign, track and complete work.",
    "id_cards": "Generate printable member and student ID cards.",
    "field_visits": "Approved visits, live location and field attendance.",
    "clients": "Client CRM, follow-ups, proposals and billing links.",
    "branches": "Multi-branch organization management.",
    "biometric": "RFID and biometric device attendance.",
    "qr": "Standard QR-code attendance.",
    "gps": "GPS and geofence attendance.",
    "manual": "Authorized manual attendance entry.",
    "wifi": "Wi-Fi and multi-method attendance.",
    "qr_attendance": "Time-limited dynamic QR attendance.",
    "face_attendance": "Face recognition attendance workflow.",
    "nepali_cal": "Nepali calendar and BS date reporting.",
    "notifications": "In-app alerts and notification workflows.",
    "finance": "Income, expenses and finance reports.",
    "stock": "Inventory, purchases, sales and stock movement.",
    "bulk_export": "Bulk spreadsheet and report exports.",
}

FEATURE_ICONS = {
    "courses": "fa-book-open",
    "student_mgmt": "fa-user-graduate",
    "results": "fa-square-poll-vertical",
    "billing": "fa-file-invoice-dollar",
    "study_gap": "fa-chalkboard-user",
    "complaints": "fa-comments",
    "events": "fa-calendar-days",
    "notices": "fa-bullhorn",
    "member_mgmt": "fa-users",
    "hrms": "fa-id-badge",
    "payroll": "fa-money-check-dollar",
    "leave": "fa-calendar-check",
    "timesheet": "fa-clock",
    "tasks": "fa-list-check",
    "id_cards": "fa-address-card",
    "field_visits": "fa-location-dot",
    "clients": "fa-handshake",
    "branches": "fa-code-branch",
    "biometric": "fa-fingerprint",
    "qr": "fa-qrcode",
    "gps": "fa-map-location-dot",
    "manual": "fa-pen-to-square",
    "wifi": "fa-wifi",
    "qr_attendance": "fa-expand",
    "face_attendance": "fa-face-smile",
    "nepali_cal": "fa-calendar",
    "notifications": "fa-bell",
    "finance": "fa-chart-pie",
    "stock": "fa-boxes-stacked",
    "bulk_export": "fa-file-export",
}

# Presets contain feature keys, not database field names. Unknown dynamic keys
# are ignored until the corresponding DynamicFeature is active.
ORG_FEATURE_PRESETS = {
    "school": {
        "member_mgmt",
        "courses",
        "student_mgmt",
        "results",
        "billing",
        "study_gap",
        "complaints",
        "events",
        "notices",
        "payroll",
        "leave",
        "id_cards",
        "manual",
        "qr",
        "qr_attendance",
        "nepali_cal",
        "notifications",
        "academic_management",
        "library",
    },
    "college": {
        "member_mgmt",
        "courses",
        "student_mgmt",
        "results",
        "billing",
        "study_gap",
        "events",
        "notices",
        "hrms",
        "payroll",
        "leave",
        "timesheet",
        "id_cards",
        "finance",
        "manual",
        "qr",
        "biometric",
        "qr_attendance",
        "nepali_cal",
        "notifications",
        "academic_management",
        "library",
        "accounting",
    },
    "bachelor": {
        "member_mgmt",
        "courses",
        "student_mgmt",
        "results",
        "billing",
        "study_gap",
        "events",
        "notices",
        "hrms",
        "payroll",
        "leave",
        "timesheet",
        "finance",
        "manual",
        "qr",
        "biometric",
        "nepali_cal",
        "academic_management",
        "library",
        "accounting",
    },
    "institute": {
        "member_mgmt",
        "courses",
        "student_mgmt",
        "results",
        "billing",
        "notices",
        "hrms",
        "payroll",
        "leave",
        "tasks",
        "clients",
        "finance",
        "manual",
        "qr",
        "notifications",
        "academic_management",
        "accounting",
    },
    "office": {
        "member_mgmt",
        "hrms",
        "payroll",
        "leave",
        "timesheet",
        "tasks",
        "id_cards",
        "field_visits",
        "clients",
        "branches",
        "notices",
        "finance",
        "bulk_export",
        "manual",
        "biometric",
        "gps",
        "wifi",
        "notifications",
        "accounting",
    },
    "industry": {
        "member_mgmt",
        "hrms",
        "payroll",
        "leave",
        "timesheet",
        "tasks",
        "id_cards",
        "field_visits",
        "branches",
        "notices",
        "finance",
        "stock",
        "bulk_export",
        "manual",
        "biometric",
        "gps",
        "wifi",
        "notifications",
        "accounting",
    },
    "others": {
        "member_mgmt",
        "payroll",
        "leave",
        "manual",
        "qr",
        "nepali_cal",
        "notifications",
    },
}


def active_dynamic_features():
    return list(DynamicFeature.objects.filter(is_active=True).order_by("category", "label"))


def all_available_feature_keys(dynamic_features=None):
    dynamic_features = active_dynamic_features() if dynamic_features is None else dynamic_features
    return set(FEATURE_MAP) | {feature.key for feature in dynamic_features}


def apply_feature_dependencies(feature_keys, dynamic_features=None):
    """Return a valid selection with every required parent feature included."""
    selected = set(feature_keys)
    dynamic_features = active_dynamic_features() if dynamic_features is None else dynamic_features
    dynamic_by_key = {feature.key: feature for feature in dynamic_features}

    changed = True
    while changed:
        changed = False
        for key in tuple(selected):
            required = set(FEATURE_DEPENDENCIES.get(key, set()))
            dynamic = dynamic_by_key.get(key)
            if dynamic:
                required.update(dynamic.requires or [])
            missing = required - selected
            if missing:
                selected.update(missing)
                changed = True
    return selected


def preset_feature_keys(category, dynamic_features=None):
    dynamic_features = active_dynamic_features() if dynamic_features is None else dynamic_features
    available = all_available_feature_keys(dynamic_features)
    requested = ORG_FEATURE_PRESETS.get(category, ORG_FEATURE_PRESETS["others"])
    return apply_feature_dependencies(requested & available, dynamic_features)


def selected_feature_keys(org):
    if not org:
        return set()

    allowed = set(org.allowed_features or [])
    selected = {
        key
        for key, field_name in FEATURE_MAP.items()
        if getattr(org, field_name, False) and (key in FREE_FEATURES or key in allowed)
    }
    selected.update(
        OrganizationFeatureGrant.objects.filter(
            org=org, enabled=True, feature__is_active=True
        ).values_list("feature__key", flat=True)
    )
    selected.add("member_mgmt")
    return selected


def build_feature_groups(org=None, selected_keys=None, dynamic_features=None):
    dynamic_features = active_dynamic_features() if dynamic_features is None else dynamic_features
    dynamic_by_key = {feature.key: feature for feature in dynamic_features}
    configured_prices = dict(
        FeaturePrice.objects.filter(
            feature_key__in=(set(FEATURE_MAP) | set(dynamic_by_key))
        ).values_list("feature_key", "annual_price")
    )
    selected = (
        selected_feature_keys(org)
        if selected_keys is None
        else apply_feature_dependencies(selected_keys, dynamic_features)
    )

    group_rows = []
    assigned_keys = set()
    for slug, group in FEATURE_GROUPS.items():
        rows = []
        group_keys = list(group["keys"])
        group_keys.extend(
            feature.key for feature in dynamic_features if (feature.category or "custom") == slug
        )
        for key in group_keys:
            if key not in FEATURE_MAP and key not in dynamic_by_key:
                continue
            dynamic = dynamic_by_key.get(key)
            fallback_price = (
                dynamic.price
                if dynamic and dynamic.price is not None
                else feature_price(key)
            )
            price = Decimal(str(configured_prices.get(key, fallback_price)))
            rows.append(
                {
                    "key": key,
                    "label": dynamic.label if dynamic else FEATURE_KEY_LABELS.get(key, key.replace("_", " ").title()),
                    "description": (
                        dynamic.description
                        if dynamic and dynamic.description
                        else FEATURE_DESCRIPTIONS.get(key, "Enable this module for the organization.")
                    ),
                    "icon": dynamic.icon if dynamic and dynamic.icon else FEATURE_ICONS.get(key, "fa-puzzle-piece"),
                    "checked": key in selected,
                    "locked": key == "member_mgmt",
                    "is_free": price == 0,
                    "price": price,
                    "is_dynamic": bool(dynamic),
                    "requires": list(
                        set(FEATURE_DEPENDENCIES.get(key, set()))
                        | set(dynamic.requires or [] if dynamic else [])
                    ),
                }
            )
            assigned_keys.add(key)
        if rows:
            group_rows.append({**group, "slug": slug, "features": rows})

    custom_rows = []
    for dynamic in dynamic_features:
        if dynamic.key in assigned_keys:
            continue
        fallback_price = (
            dynamic.price
            if dynamic.price is not None
            else feature_price(dynamic.key)
        )
        price = Decimal(
            str(configured_prices.get(dynamic.key, fallback_price))
        )
        custom_rows.append(
            {
                "key": dynamic.key,
                "label": dynamic.label,
                "description": dynamic.description or "Custom platform module.",
                "icon": dynamic.icon or "fa-puzzle-piece",
                "checked": dynamic.key in selected,
                "locked": False,
                "is_free": price == 0,
                "price": price,
                "is_dynamic": True,
                "requires": list(dynamic.requires or []),
            }
        )
    if custom_rows:
        group_rows.append(
            {
                "slug": "custom",
                "label": "Premium & Custom",
                "icon": "fa-gem",
                "description": "Database-managed modules created in the feature registry.",
                "features": custom_rows,
            }
        )
    return group_rows


@transaction.atomic
def save_feature_selection(org, feature_keys):
    """Synchronize flags, plan allowlist, and dynamic grants in one transaction."""
    dynamic_features = active_dynamic_features()
    available = all_available_feature_keys(dynamic_features)
    selected = apply_feature_dependencies(set(feature_keys) & available, dynamic_features)
    selected.add("member_mgmt")

    changed_fields = []
    for key, field_name in FEATURE_MAP.items():
        enabled = key in selected
        if getattr(org, field_name) != enabled:
            setattr(org, field_name, enabled)
            changed_fields.append(field_name)

    allowed = sorted((set(FREE_FEATURES) | (selected & set(FEATURE_MAP))))
    if org.allowed_features != allowed:
        org.allowed_features = allowed
        changed_fields.append("allowed_features")
    if changed_fields:
        org.save(update_fields=sorted(set(changed_fields)))

    existing = {
        grant.feature_id: grant
        for grant in OrganizationFeatureGrant.objects.filter(
            org=org, feature__in=dynamic_features
        )
    }
    to_create = []
    to_update = []
    for feature in dynamic_features:
        enabled = feature.key in selected
        grant = existing.get(feature.id)
        if grant is None:
            to_create.append(
                OrganizationFeatureGrant(org=org, feature=feature, enabled=enabled)
            )
        elif grant.enabled != enabled:
            grant.enabled = enabled
            to_update.append(grant)
    if to_create:
        OrganizationFeatureGrant.objects.bulk_create(to_create)
    if to_update:
        OrganizationFeatureGrant.objects.bulk_update(to_update, ["enabled"])
    invalidate_org_feature_cache(org.id)
    return selected


def _org_end_date(org):
    if org.subscription_end:
        return org.subscription_end
    expire_on = org.expire_on
    if not expire_on:
        return None
    return expire_on.date() if hasattr(expire_on, "date") else expire_on


def subscription_summary(
    org,
    today=None,
    enabled_dynamic=None,
    configured_prices=None,
):
    """Calculate annual value, term value and expiry state without storing totals."""
    today = today or date.today()
    allowed = set(org.allowed_features or [])
    enabled_legacy = {
        key
        for key, field_name in FEATURE_MAP.items()
        if getattr(org, field_name, False) and (key in FREE_FEATURES or key in allowed)
    }
    if enabled_dynamic is None:
        enabled_dynamic = list(
            DynamicFeature.objects.filter(
                org_grants__org=org,
                org_grants__enabled=True,
                is_active=True,
            ).values("key", "price")
        )

    all_enabled_keys = enabled_legacy | {
        row["key"] for row in enabled_dynamic
    }
    if configured_prices is None:
        configured_prices = dict(
            FeaturePrice.objects.filter(
                feature_key__in=all_enabled_keys
            ).values_list("feature_key", "annual_price")
        )

    def configured_rate(key, fallback=None):
        if key in configured_prices:
            return Decimal(str(configured_prices[key]))
        return Decimal(
            str(feature_price(key) if fallback is None else fallback)
        )

    feature_annual = sum(
        (configured_rate(key) for key in enabled_legacy),
        Decimal("0"),
    )
    feature_annual += sum(
        (
            configured_rate(row["key"], row["price"])
            for row in enabled_dynamic
        ),
        Decimal("0"),
    )
    quoted_member_limit = min(max(org.member_limit or 1, 1), 1_000_000)
    package = member_package_price(quoted_member_limit)
    calculated_annual = package["base_cost"] + feature_annual
    custom_amount = org.custom_subscription_amount
    quoted_annual = (
        Decimal(str(custom_amount))
        if custom_amount is not None
        else calculated_annual
    )
    annual_cost = Decimal("0") if org.free_demo else quoted_annual

    start = (
        org.created_at.date()
        if org.created_at
        else org.subscription_start
    )
    end = _org_end_date(org)
    if start and end and end >= start:
        term_days = (end - start).days + 1
        contract_total = annual_cost * Decimal(term_days) / Decimal("365")
    else:
        term_days = None
        contract_total = annual_cost
    contract_total = contract_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    days_remaining = (end - today).days if end else None
    if days_remaining is None:
        expiry_state = "no_expiry"
    elif days_remaining < 0:
        expiry_state = "expired"
    elif days_remaining <= 30:
        expiry_state = "due_soon"
    else:
        expiry_state = "active"

    return {
        "annual_cost": annual_cost.quantize(Decimal("0.01")),
        "catalog_annual": calculated_annual.quantize(Decimal("0.01")),
        "base_package_cost": package["base_cost"].quantize(Decimal("0.01")),
        "feature_annual_cost": feature_annual.quantize(Decimal("0.01")),
        "package_name": package["package_name"],
        "package_units": package["package_units"],
        "custom_amount_applied": custom_amount is not None,
        "contract_total": contract_total,
        "term_days": term_days,
        "end_date": end,
        "days_remaining": days_remaining,
        "expiry_state": expiry_state,
        "enabled_count": len(enabled_legacy) + len(enabled_dynamic),
        "paid_feature_count": sum(configured_rate(key) > 0 for key in enabled_legacy)
        + sum(
            configured_rate(row["key"], row["price"]) > 0
            for row in enabled_dynamic
        ),
    }


def dashboard_subscription_context(organizations, today=None):
    today = today or date.today()
    organizations = list(organizations)
    org_ids = [org.id for org in organizations]
    dynamic_by_org = {org_id: [] for org_id in org_ids}
    grants = OrganizationFeatureGrant.objects.filter(
        org_id__in=org_ids,
        enabled=True,
        feature__is_active=True,
    ).values("org_id", "feature__key", "feature__price")
    for grant in grants:
        dynamic_by_org[grant["org_id"]].append(
            {"key": grant["feature__key"], "price": grant["feature__price"]}
        )
    configured_prices = dict(
        FeaturePrice.objects.values_list("feature_key", "annual_price")
    )

    rows = []
    for org in organizations:
        rows.append(
            {
                "org": org,
                "summary": subscription_summary(
                    org,
                    today=today,
                    enabled_dynamic=dynamic_by_org.get(org.id, []),
                    configured_prices=configured_prices,
                ),
            }
        )

    reminders = sorted(
        (
            row
            for row in rows
            if row["summary"]["expiry_state"] in {"expired", "due_soon"}
        ),
        key=lambda row: (
            row["summary"]["end_date"] or date.max,
            row["org"].name.lower(),
        ),
    )
    outstanding = sum(
        (
            row["summary"]["contract_total"]
            for row in rows
            if row["org"].payment_status in {"unpaid", "partial"}
        ),
        Decimal("0"),
    )
    return {
        "organization_rows": rows,
        "expiry_reminders": reminders,
        "total_annual_cost": sum(
            (row["summary"]["annual_cost"] for row in rows), Decimal("0")
        ),
        "total_contract_cost": sum(
            (row["summary"]["contract_total"] for row in rows), Decimal("0")
        ),
        "outstanding_cost": outstanding,
        "active_subscription_count": sum(
            row["summary"]["expiry_state"] == "active" and row["org"].activate
            for row in rows
        ),
        "expiring_count": sum(
            row["summary"]["expiry_state"] == "due_soon" for row in rows
        ),
        "expired_count": sum(
            row["summary"]["expiry_state"] == "expired" for row in rows
        ),
    }
