"""Pricing catalog and public quotation calculations.

All totals are rebuilt on the server from admin-controlled database rates.
Frontend values are display-only and are never trusted for quotation totals.
"""

from decimal import Decimal
from math import ceil

from django.core.exceptions import ValidationError

from handle.models import DynamicFeature
from management.models import FeaturePrice, Pricing
from school.features import FEATURE_KEY_LABELS, FEATURE_MAP, FREE_FEATURES, STANDARD_FEATURE_PRICE


FEATURE_CATEGORIES = {
    "courses": "Academic",
    "student_mgmt": "Academic",
    "results": "Academic",
    "billing": "Academic",
    "study_gap": "Academic",
    "complaints": "Academic",
    "events": "Academic",
    "notices": "Communication",
    "member_mgmt": "Workforce",
    "hrms": "Workforce",
    "payroll": "Workforce",
    "leave": "Workforce",
    "timesheet": "Workforce",
    "tasks": "Workforce",
    "id_cards": "Workforce",
    "field_visits": "Workforce",
    "clients": "Business",
    "branches": "Business",
    "finance": "Business",
    "stock": "Business",
    "bulk_export": "Business",
    "biometric": "Attendance",
    "qr": "Attendance",
    "gps": "Attendance",
    "manual": "Attendance",
    "wifi": "Attendance",
    "qr_attendance": "Attendance",
    "face_attendance": "Attendance",
    "nepali_cal": "Attendance",
    "notifications": "Communication",
}

FEATURE_ICONS = {
    "academic": "fa-graduation-cap",
    "workforce": "fa-users",
    "attendance": "fa-fingerprint",
    "business": "fa-chart-line",
    "communication": "fa-bell",
    "custom": "fa-puzzle-piece",
}


def sync_feature_price_catalog(updated_by=None):
    """Add missing catalog rows without overwriting prices chosen by an admin."""
    dynamic_features = {
        feature.key: feature for feature in DynamicFeature.objects.all()
    }
    known_keys = list(FEATURE_MAP)
    known_keys.extend(key for key in dynamic_features if key not in FEATURE_MAP)
    existing = set(
        FeaturePrice.objects.filter(feature_key__in=known_keys).values_list(
            "feature_key", flat=True
        )
    )
    to_create = []
    for order, key in enumerate(known_keys, start=1):
        if key in existing:
            continue
        dynamic = dynamic_features.get(key)
        default_price = (
            Decimal("0")
            if key in FREE_FEATURES
            else Decimal(
                str(
                    dynamic.price
                    if dynamic and dynamic.price is not None
                    else STANDARD_FEATURE_PRICE
                )
            )
        )
        to_create.append(
            FeaturePrice(
                feature_key=key,
                label=(
                    dynamic.label
                    if dynamic
                    else FEATURE_KEY_LABELS.get(key, key.replace("_", " ").title())
                ),
                annual_price=default_price,
                is_active=dynamic.is_active if dynamic else True,
                display_order=order * 10,
                updated_by=updated_by,
            )
        )
    if to_create:
        FeaturePrice.objects.bulk_create(to_create)
    return FeaturePrice.objects.all()


def feature_catalog(public_only=False, active_only=False, sync_missing=False):
    # Public pricing requests stay read-only. Administrative screens may opt in
    # to catalog synchronization after migrations or a manual dynamic feature
    # import.
    if sync_missing:
        sync_feature_price_catalog()
    queryset = FeaturePrice.objects.all()
    if public_only:
        queryset = queryset.filter(is_public=True, is_active=True)
    elif active_only:
        queryset = queryset.filter(is_active=True)

    dynamic_by_key = {
        feature.key: feature
        for feature in DynamicFeature.objects.filter(
            key__in=queryset.values_list("feature_key", flat=True)
        )
    }
    rows = []
    for price in queryset:
        dynamic = dynamic_by_key.get(price.feature_key)
        category = (
            dynamic.category.title()
            if dynamic and dynamic.category
            else FEATURE_CATEGORIES.get(price.feature_key, "Custom")
        )
        rows.append(
            {
                "key": price.feature_key,
                "label": price.label,
                "annual_price": price.annual_price,
                "is_free": price.annual_price == 0,
                "is_active": price.is_active,
                "is_public": price.is_public,
                "category": category,
                "icon": (
                    dynamic.icon
                    if dynamic and dynamic.icon
                    else FEATURE_ICONS.get(category.lower(), "fa-puzzle-piece")
                ),
                "description": dynamic.description if dynamic else "",
                "price_record": price,
                "is_dynamic": bool(dynamic),
            }
        )
    return rows


def pricing_tiers():
    return list(Pricing.objects.filter(limit__gt=0).order_by("limit", "price", "id"))


def member_package_price(member_limit, tiers=None):
    member_limit = int(member_limit)
    if member_limit < 1 or member_limit > 1_000_000:
        raise ValidationError("Member limit must be between 1 and 1,000,000.")

    tiers = pricing_tiers() if tiers is None else list(tiers)
    if not tiers:
        return {
            "package": None,
            "package_name": "Custom member package",
            "package_limit": member_limit,
            "package_units": 1,
            "base_cost": Decimal("0"),
        }

    package = next((tier for tier in tiers if tier.limit >= member_limit), None)
    package_units = 1
    if package is None:
        package = tiers[-1]
        package_units = ceil(member_limit / package.limit)
    return {
        "package": package,
        "package_name": package.name,
        "package_limit": package.limit,
        "package_units": package_units,
        "base_cost": Decimal(str(package.price)) * package_units,
    }


def calculate_quote(member_limit, selected_feature_keys):
    package = member_package_price(member_limit)
    catalog = feature_catalog(public_only=True)
    catalog_by_key = {row["key"]: row for row in catalog}
    selected_keys = set(selected_feature_keys)
    invalid_keys = selected_keys - set(catalog_by_key)
    if invalid_keys:
        raise ValidationError("One or more selected features are not available for quotation.")

    selected_rows = [
        row for row in catalog if row["key"] in selected_keys
    ]
    feature_total = sum(
        (row["annual_price"] for row in selected_rows), Decimal("0")
    )
    annual_total = package["base_cost"] + feature_total
    return {
        **package,
        "member_limit": int(member_limit),
        "selected_features": selected_rows,
        "selected_keys": selected_keys,
        "feature_total": feature_total,
        "annual_total": annual_total,
        "monthly_equivalent": (annual_total / Decimal("12")).quantize(Decimal("0.01")),
        "per_member_annual": (annual_total / Decimal(str(member_limit))).quantize(
            Decimal("0.01")
        ),
    }


def pricing_tier_payload():
    return [
        {
            "name": tier.name,
            "limit": tier.limit,
            "price": tier.price,
        }
        for tier in pricing_tiers()
    ]
