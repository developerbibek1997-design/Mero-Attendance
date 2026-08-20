from django.test import TestCase
from django.urls import reverse

from management.models import FAQ


class HomepageFAQTests(TestCase):
    def setUp(self):
        FAQ.objects.all().delete()

    def test_homepage_shows_only_active_faqs(self):
        visible = FAQ.objects.create(
            question="Can our organization use the platform?",
            answer="Yes, enabled modules can be configured for your organization.",
            order=1,
            is_active=True,
        )
        hidden = FAQ.objects.create(
            question="This question must stay hidden",
            answer="Inactive FAQ answer.",
            order=2,
            is_active=False,
        )

        response = self.client.get(reverse("management:homepage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="faq"')
        self.assertContains(response, visible.question)
        self.assertNotContains(response, hidden.question)

    def test_homepage_faq_schema_contains_quoted_question_and_answer(self):
        FAQ.objects.create(
            question="Does it support BS and AD dates?",
            answer="Yes. Both calendars are supported.",
            order=1,
            is_active=True,
        )

        response = self.client.get(reverse("management:homepage"))

        self.assertContains(response, '"@type": "FAQPage"')
        self.assertContains(response, '"name": "Does it support BS and AD dates?"')
        self.assertContains(response, '"text": "Yes. Both calendars are supported."')
