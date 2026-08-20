"""
HTML -> PDF rendering, used to attach a printable PDF (payslip, bill,
result sheet) to the corresponding notification email. Uses xhtml2pdf
(already listed in requirements.txt) — no new dependency.
"""

import io

from django.template.loader import render_to_string
from xhtml2pdf import pisa


def render_to_pdf(template_name, context):
    """Render a Django template to PDF bytes, or None if rendering failed."""
    html = render_to_string(template_name, context)
    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding='utf-8')
    if result.err:
        return None
    return buffer.getvalue()
