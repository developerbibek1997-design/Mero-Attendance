"""
Shared AD <-> BS (Bikram Sambat) date conversion, used by every view that
shows or accepts a date under an org's Nepali-calendar setting
(`Organization.nepali_date`). Centralised so the "convert, fall back safely
on failure" pattern isn't hand-copied (and occasionally mis-copied) at each
call site.
"""

import nepali_datetime


def to_bs_display(ad_date):
    """AD `date`/`datetime` -> 'YYYY-MM-DD' BS string, or '' if `ad_date` is
    falsy or outside the range `nepali_datetime` can convert."""
    if not ad_date:
        return ''
    try:
        return str(nepali_datetime.date.from_datetime_date(ad_date))
    except (ValueError, TypeError, OverflowError):
        return ''


def from_bs_display(bs_date_str):
    """'YYYY-MM-DD' BS string -> AD `date`, or None if blank/unparseable.

    Used to re-derive an authoritative AD value server-side for date fields
    where precision matters (e.g. date of birth) — the BS date picker
    (static/assets/js/global-date-picker.js) converts BS -> AD client-side
    for speed, but its month-length table only has exact data for a limited
    range of years; outside that it falls back to an approximation that can
    drift by a few days for years far from the present. `nepali_datetime` is
    the authoritative source, so re-parsing the raw BS text through it here
    corrects that drift regardless of what the browser computed.
    """
    if not bs_date_str:
        return None
    try:
        year, month, day = map(int, str(bs_date_str).strip().split('-'))
        return nepali_datetime.date(year, month, day).to_datetime_date()
    except (ValueError, TypeError, OverflowError):
        return None
