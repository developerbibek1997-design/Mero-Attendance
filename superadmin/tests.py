from datetime import date, datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from handle.models import DynamicFeature, OrganizationFeatureGrant
from management.models import CustomUser, FeaturePrice, Organization, Pricing
from management.pricing_services import calculate_quote, member_package_price
from superadmin.organization_services import (
    preset_feature_keys,
    save_feature_selection,
    subscription_summary,
)


class OrganizationFeatureServiceTests(TestCase):
    def setUp(self):
        self.accounting = DynamicFeature.objects.create(
            key="test_accounting",
            label="Test Accounting",
            category="business",
            price=Decimal("5000.00"),
            is_active=True,
        )
        self.org = Organization.objects.create(
            name="Service Test School",
            category="school",
            expire_on=timezone.now() + timedelta(days=365),
            serial_key="SERVICE-001",
            new_serial_key="ACT-SERVICE-001",
            created_at=timezone.make_aware(datetime(2026, 1, 1)),
            subscription_start=date(2026, 1, 1),
            subscription_end=date(2026, 12, 31),
            payment_status="paid",
            org_status="active",
        )

    def test_feature_selection_synchronizes_flags_allowlist_dynamic_and_dependencies(self):
        save_feature_selection(
            self.org,
            {"results", "billing", "test_accounting", "manual"},
        )
        self.org.refresh_from_db()

        self.assertTrue(self.org.feature_results)
        self.assertTrue(self.org.feature_courses)
        self.assertTrue(self.org.feature_billing)
        self.assertTrue(self.org.feature_student_mgmt)
        self.assertTrue(self.org.manual_attendance)
        self.assertIn("results", self.org.allowed_features)
        self.assertIn("courses", self.org.allowed_features)
        self.assertTrue(
            OrganizationFeatureGrant.objects.get(
                org=self.org, feature=self.accounting
            ).enabled
        )

    def test_industry_preset_contains_workforce_stock_and_attendance(self):
        keys = preset_feature_keys("industry")

        self.assertTrue(
            {"member_mgmt", "hrms", "payroll", "stock", "biometric", "manual"}
            <= keys
        )

    def test_subscription_summary_calculates_annual_and_term_price(self):
        save_feature_selection(self.org, {"finance", "test_accounting", "manual"})

        summary = subscription_summary(self.org, today=date(2026, 6, 1))

        self.assertEqual(summary["annual_cost"], Decimal("8000.00"))
        self.assertEqual(summary["contract_total"], Decimal("8000.00"))
        self.assertEqual(summary["paid_feature_count"], 2)

    def test_free_demo_keeps_features_but_zeroes_commercial_total(self):
        save_feature_selection(self.org, {"finance", "test_accounting"})
        self.org.free_demo = True
        self.org.save(update_fields=["free_demo"])

        summary = subscription_summary(self.org, today=date(2026, 6, 1))

        self.assertEqual(summary["catalog_annual"], Decimal("8000.00"))
        self.assertEqual(summary["annual_cost"], Decimal("0.00"))
        self.assertEqual(summary["contract_total"], Decimal("0.00"))

    def test_admin_feature_rate_and_member_package_drive_calculated_amount(self):
        Pricing.objects.create(
            name="Up to 50 Members",
            price=7000,
            limit=50,
            device="Web",
        )
        FeaturePrice.objects.update_or_create(
            feature_key="finance",
            defaults={
                "label": "Finance",
                "annual_price": Decimal("4200.00"),
                "is_active": True,
                "is_public": True,
            },
        )
        save_feature_selection(self.org, {"finance"})

        summary = subscription_summary(self.org, today=date(2026, 6, 1))

        self.assertEqual(summary["base_package_cost"], Decimal("7000.00"))
        self.assertEqual(summary["feature_annual_cost"], Decimal("4200.00"))
        self.assertEqual(summary["catalog_annual"], Decimal("11200.00"))
        self.assertEqual(summary["annual_cost"], Decimal("11200.00"))

    def test_custom_subscription_amount_overrides_catalog_without_losing_breakdown(self):
        FeaturePrice.objects.update_or_create(
            feature_key="finance",
            defaults={
                "label": "Finance",
                "annual_price": Decimal("4200.00"),
                "is_active": True,
                "is_public": True,
            },
        )
        save_feature_selection(self.org, {"finance"})
        self.org.custom_subscription_amount = Decimal("9750.00")
        self.org.save(update_fields=["custom_subscription_amount"])

        summary = subscription_summary(self.org, today=date(2026, 6, 1))

        self.assertTrue(summary["custom_amount_applied"])
        self.assertEqual(summary["catalog_annual"], Decimal("4200.00"))
        self.assertEqual(summary["annual_cost"], Decimal("9750.00"))


class SuperadminOrganizationViewsTests(TestCase):
    def setUp(self):
        self.superadmin = CustomUser.objects.create_user(
            username="platform@example.com",
            email="platform@example.com",
            password="test-password",
            user_type="1",
        )
        self.client.force_login(self.superadmin)
        self.academic = DynamicFeature.objects.create(
            key="test_academic_suite",
            label="Test Academic Suite",
            category="academic",
            price=Decimal("4500.00"),
            is_active=True,
        )

    def _post_data(self, **overrides):
        data = {
            "name": "Premium School",
            "category": "school",
            "address": "Kathmandu",
            "member_limit": "500",
            "expire_on": "2027-06-30",
            "serial_key": "PREMIUM-001",
            "new_serial_key": "ACT-PREMIUM-001",
            "activate": "on",
            "subscription_plan": "School Annual",
            "subscription_start": "2026-07-01",
            "subscription_end": "2027-06-30",
            "payment_status": "paid",
            "org_status": "active",
            "feature_keys": [
                "member_mgmt",
                "results",
                "billing",
                "manual",
                "test_academic_suite",
            ],
        }
        data.update(overrides)
        return data

    def test_add_form_has_one_unified_feature_block(self):
        response = self.client.get(reverse("superadmin:addOrg"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All Features — One Unified Block", count=1)
        self.assertContains(response, "All Features On")
        self.assertContains(response, "Industry")
        self.assertNotContains(response, "Allowed Features (Plan)")
        self.assertNotContains(response, "Premium Modules")

    def test_add_organization_saves_subscription_and_one_feature_selection(self):
        response = self.client.post(
            reverse("superadmin:addOrg"),
            self._post_data(
                custom_subscription_amount="28000.00",
                custom_amount_note="Negotiated school package",
            ),
        )

        org = Organization.objects.get(serial_key="PREMIUM-001")
        self.assertRedirects(
            response,
            reverse("superadmin:editOrg", args=[org.id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(org.subscription_plan, "School Annual")
        self.assertEqual(org.subscription_start, org.created_at.date())
        self.assertEqual(org.subscription_end, date(2027, 6, 30))
        self.assertEqual(org.custom_subscription_amount, Decimal("28000.00"))
        self.assertEqual(org.custom_amount_note, "Negotiated school package")
        self.assertTrue(org.feature_results)
        self.assertTrue(org.feature_courses)
        self.assertTrue(org.feature_billing)
        self.assertTrue(org.feature_student_mgmt)
        self.assertIn("results", org.allowed_features)
        self.assertTrue(
            OrganizationFeatureGrant.objects.get(
                org=org, feature=self.academic
            ).enabled
        )

    def test_edit_organization_disables_unchecked_features_and_updates_expiry(self):
        self.client.post(reverse("superadmin:addOrg"), self._post_data())
        org = Organization.objects.get(serial_key="PREMIUM-001")
        edit_data = self._post_data(
            name="Premium School Updated",
            category="industry",
            subscription_plan="Industry Pro",
            subscription_end="2028-06-30",
            expire_on="2028-06-30",
            payment_status="partial",
            feature_keys=["member_mgmt", "stock", "biometric"],
        )

        response = self.client.post(
            reverse("superadmin:editOrg", args=[org.id]),
            edit_data,
        )

        self.assertEqual(response.status_code, 302)
        org.refresh_from_db()
        self.assertEqual(org.category, "industry")
        self.assertEqual(org.subscription_plan, "Industry Pro")
        self.assertEqual(org.subscription_end, date(2028, 6, 30))
        self.assertTrue(org.feature_stock)
        self.assertTrue(org.rfid_based)
        self.assertFalse(org.feature_results)
        self.assertFalse(org.feature_billing)
        self.assertNotIn("results", org.allowed_features)
        self.assertFalse(
            OrganizationFeatureGrant.objects.get(
                org=org, feature=self.academic
            ).enabled
        )

    def test_dashboard_shows_aggregate_cost_and_expiry_reminder_near_org(self):
        end = date.today() + timedelta(days=10)
        data = self._post_data(
            name="Renewal School",
            subscription_start=date.today().isoformat(),
            subscription_end=end.isoformat(),
            expire_on=end.isoformat(),
            payment_status="unpaid",
            feature_keys=["member_mgmt", "finance"],
        )
        self.client.post(reverse("superadmin:addOrg"), data)

        response = self.client.get(reverse("superadmin:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Annual Package Value")
        self.assertContains(response, "Subscription Reminders")
        self.assertContains(response, "Renewal School")
        self.assertContains(response, "10 days left")
        self.assertEqual(response.context["total_annual_cost"], Decimal("3000.00"))
        self.assertEqual(response.context["expiring_count"], 1)

    def test_feature_registry_updates_admin_controlled_rate(self):
        response = self.client.post(
            reverse("superadmin:feature_registry"),
            {
                "action": "update_feature_price",
                "feature_key": "finance",
                "annual_price": "4750.00",
                "is_public": "on",
                "is_active": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("superadmin:feature_registry"),
            fetch_redirect_response=False,
        )
        rate = FeaturePrice.objects.get(feature_key="finance")
        self.assertEqual(rate.annual_price, Decimal("4750.00"))
        self.assertTrue(rate.is_public)
        self.assertTrue(rate.is_active)
        self.assertEqual(rate.updated_by, self.superadmin)


class PublicPricingQuotationTests(TestCase):
    def setUp(self):
        Pricing.objects.create(
            name="Starter 25",
            price=5000,
            limit=25,
            device="Web",
        )
        Pricing.objects.create(
            name="Growth 100",
            price=12000,
            limit=100,
            device="Web",
        )
        FeaturePrice.objects.update_or_create(
            feature_key="finance",
            defaults={
                "label": "Finance",
                "annual_price": Decimal("2500.00"),
                "is_active": True,
                "is_public": True,
            },
        )

    def test_member_package_selects_smallest_covering_tier_and_scales_above_max(self):
        starter = member_package_price(20)
        scaled = member_package_price(220)

        self.assertEqual(starter["package_name"], "Starter 25")
        self.assertEqual(starter["base_cost"], Decimal("5000"))
        self.assertEqual(scaled["package_name"], "Growth 100")
        self.assertEqual(scaled["package_units"], 3)
        self.assertEqual(scaled["base_cost"], Decimal("36000"))

    def test_quote_is_rebuilt_from_member_tier_and_admin_feature_rate(self):
        quote = calculate_quote(20, {"finance"})

        self.assertEqual(quote["base_cost"], Decimal("5000"))
        self.assertEqual(quote["feature_total"], Decimal("2500.00"))
        self.assertEqual(quote["annual_total"], Decimal("7500.00"))

    def test_public_pricing_rejects_forged_or_private_feature_key(self):
        response = self.client.post(
            reverse("management:pricing"),
            {"member_limit": "20", "feature_keys": ["not_for_sale"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "One or more selected features are not available for quotation.",
        )
        self.assertNotIn("quote_result", response.context)

    def test_public_pricing_renders_and_calculates_authoritative_quote(self):
        get_response = self.client.get(reverse("management:pricing"))
        post_response = self.client.post(
            reverse("management:pricing"),
            {"member_limit": "20", "feature_keys": ["finance"]},
        )

        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "Build your Mero Attendance quotation")
        self.assertContains(get_response, "Finance")
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(
            post_response.context["quote_result"]["annual_total"],
            Decimal("7500.00"),
        )
        self.assertContains(post_response, "Your quotation is ready")

    def test_public_homepage_shows_new_erp_workflows_and_quote_link(self):
        response = self.client.get(reverse("management:homepage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Hierarchy &amp; Subject Attendance")
        self.assertContains(response, "Homework &amp; Assignment Workspace")
        self.assertContains(response, "Premium Messages &amp; Notifications")
        self.assertContains(response, "Build Your Quotation")


class DatabaseBackupTests(TestCase):
    """Phase 8: superadmin-only SQLite backup via the sqlite3 online backup API."""

    def setUp(self):
        self.superadmin = CustomUser.objects.create_user(
            username="backup-super@example.com", email="backup-super@example.com",
            password="test-password", user_type="1",
        )
        self.org_admin = CustomUser.objects.create_user(
            username="backup-orgadmin@example.com", email="backup-orgadmin@example.com",
            password="test-password", user_type="2",
        )

    def test_build_sqlite_backup_response_streams_valid_db_and_cleans_up(self):
        # Exercise the actual backup-building code against a real on-disk
        # SQLite file. Deliberately NOT sourced from `connection.connection`
        # (the live Django test connection): TestCase wraps every test in an
        # open outer transaction on that exact connection, and asking
        # sqlite3's backup API to read from a connection that's mid-transaction
        # on itself makes it spin retrying a self-imposed lock indefinitely.
        # A plain freestanding file is all this test needs — it only checks
        # that a valid SQLite file comes back, not any particular content.
        import os
        import sqlite3
        import tempfile
        from superadmin.views import build_sqlite_backup_response

        real_db_file = tempfile.mktemp(suffix='.sqlite3')
        seed_conn = sqlite3.connect(real_db_file)
        seed_conn.execute('CREATE TABLE t (id INTEGER PRIMARY KEY)')
        seed_conn.commit()
        seed_conn.close()

        try:
            response = build_sqlite_backup_response(real_db_file)
            self.assertEqual(response['Content-Type'], 'application/x-sqlite3')
            self.assertIn('attachment', response['Content-Disposition'])
            self.assertIn('.sqlite3', response['Content-Disposition'])
            body = b''.join(response.streaming_content)
            self.assertTrue(body.startswith(b'SQLite format 3'))
            response.close()  # FileResponse deletes its own temp file here
        finally:
            os.remove(real_db_file)

    def test_superadmin_reaches_backup_logic(self):
        # Confirms the view's permission/method gating lets a real superadmin
        # POST through to the backup step (mocked so the test doesn't touch
        # any real file), without re-testing build_sqlite_backup_response
        # itself here — that's covered above.
        from unittest.mock import patch
        from django.http import HttpResponse

        self.client.force_login(self.superadmin)
        with patch('superadmin.views.build_sqlite_backup_response', return_value=HttpResponse('ok')) as mocked:
            response = self.client.post(reverse('superadmin:database_backup'))
        mocked.assert_called_once()
        self.assertEqual(response.status_code, 200)

    def test_get_request_is_rejected(self):
        self.client.force_login(self.superadmin)
        response = self.client.get(reverse('superadmin:database_backup'))
        self.assertEqual(response.status_code, 302)

    def test_org_admin_is_blocked_by_middleware(self):
        self.client.force_login(self.org_admin)
        response = self.client.post(reverse('superadmin:database_backup'))
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.get('Content-Type'), 'application/x-sqlite3')

    def test_anonymous_is_redirected(self):
        response = self.client.post(reverse('superadmin:database_backup'))
        self.assertEqual(response.status_code, 302)
