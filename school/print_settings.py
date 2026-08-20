"""
Reusable per-user, per-report print configuration.

Any printable page (Daily Report, Monthly Report, Payslip, ID cards, ...)
can opt in by picking a short `report_key` and:

  1. In its view, call `get_print_preference(request.user, 'my_report')`
     and pass the result into the template context as `print_preference`
     so the first paint already reflects the user's saved choice (no
     flash-of-default-settings).
  2. In its template, include `partials/print_settings_panel.html` and set
     `data-report-key="my_report"` on the print-settings mount point.

Settings are also cached in localStorage client-side (see
static/js/print_settings.js) purely as an instant, offline-safe mirror —
the database row saved here is the source of truth per the spec.
"""
import copy

from handle.models import PrintPreference, OrgPrintDefault

DEFAULT_PRINT_SETTINGS = {
    'paper': 'A4',          # 'A4' | 'Letter' | 'Legal'
    'orientation': 'portrait',   # 'portrait' | 'landscape'
    'margin': 'normal',     # 'normal' | 'narrow' | 'none'
    'fit_to_width': True,
    'hidden_columns': [],
}

_ALLOWED_PAPER = {'A4', 'Letter', 'Legal'}
_ALLOWED_ORIENTATION = {'portrait', 'landscape'}
_ALLOWED_MARGIN = {'normal', 'narrow', 'none'}


def get_org_print_default(org, report_key):
    """Return the org-wide default for this report, merged over the
    hardcoded fallback. Every printable page can call this even if no admin
    has ever set one — it just returns DEFAULT_PRINT_SETTINGS unchanged."""
    settings = copy.deepcopy(DEFAULT_PRINT_SETTINGS)
    if not org:
        return settings
    row = OrgPrintDefault.objects.filter(org=org, report_key=report_key).first()
    if row and isinstance(row.settings, dict):
        settings.update(_sanitize(row.settings))
    return settings


def save_org_print_default(org, report_key, raw_settings):
    """Validate/whitelist `raw_settings` and upsert the org-wide default."""
    clean = _sanitize(raw_settings if isinstance(raw_settings, dict) else {})
    row, _ = OrgPrintDefault.objects.update_or_create(
        org=org, report_key=report_key[:50],
        defaults={'settings': clean},
    )
    return row.settings


def get_print_preference(user, report_key, org=None):
    """Return the effective settings for this user+report: the hardcoded
    fallback, overridden by the org's admin-set default (if any), overridden
    by this user's own saved choice (if any) — so a first-time viewer sees
    the org's chosen layout rather than the generic app default, while
    anyone who has customized it for themselves keeps that customization."""
    settings = get_org_print_default(org, report_key) if org else copy.deepcopy(DEFAULT_PRINT_SETTINGS)
    if not user or not getattr(user, 'is_authenticated', False):
        return settings
    row = PrintPreference.objects.filter(user=user, report_key=report_key).first()
    if row and isinstance(row.settings, dict):
        settings.update(_sanitize(row.settings))
    return settings


def save_print_preference(user, report_key, raw_settings):
    """Validate/whitelist `raw_settings` and upsert it. Returns the saved dict."""
    clean = _sanitize(raw_settings if isinstance(raw_settings, dict) else {})
    row, _ = PrintPreference.objects.update_or_create(
        user=user, report_key=report_key[:50],
        defaults={'settings': clean},
    )
    return row.settings


def _sanitize(raw):
    out = {}
    paper = raw.get('paper')
    if paper in _ALLOWED_PAPER:
        out['paper'] = paper
    orientation = raw.get('orientation')
    if orientation in _ALLOWED_ORIENTATION:
        out['orientation'] = orientation
    margin = raw.get('margin')
    if margin in _ALLOWED_MARGIN:
        out['margin'] = margin
    if isinstance(raw.get('fit_to_width'), bool):
        out['fit_to_width'] = raw['fit_to_width']
    hidden = raw.get('hidden_columns')
    if isinstance(hidden, list):
        out['hidden_columns'] = [str(c)[:50] for c in hidden if isinstance(c, (str, int))][:50]
    return out
