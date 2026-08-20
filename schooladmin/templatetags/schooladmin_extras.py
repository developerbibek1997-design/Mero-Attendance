from django import template
from django.utils.html import format_html

register = template.Library()

_AVATAR_GRADIENT = 'linear-gradient(135deg,#818cf8,#6366f1)'


@register.filter
def member_avatar(m, size=32):
    """
    Small circular avatar for a member: their uploaded photo, or a
    colored-initial fallback when there isn't one. Inline-styled so it can
    drop into any template's member table/row without matching CSS.
    Usage: {{ i|member_avatar }} or {{ i|member_avatar:40 }}
    """
    if not m:
        return ''
    size = int(size)
    name = getattr(m, 'name', '') or ''
    initial = name.strip()[:1].upper() or '?'
    photo = getattr(m, 'photo', None)
    if photo:
        try:
            url = photo.url
        except ValueError:
            url = None
        if url:
            return format_html(
                '<img src="{}" alt="{}" style="width:{}px;height:{}px;border-radius:50%;'
                'object-fit:cover;flex-shrink:0;">',
                url, name, size, size,
            )
    font_size = max(size * 0.4, 10)
    return format_html(
        '<span style="width:{}px;height:{}px;border-radius:50%;flex-shrink:0;'
        'background:{};color:#fff;display:inline-flex;align-items:center;'
        'justify-content:center;font-size:{}px;font-weight:800;'
        'text-transform:uppercase;">{}</span>',
        size, size, _AVATAR_GRADIENT, font_size, initial,
    )

@register.filter
def dict_get(d, key):
    if isinstance(d, dict):
        return d.get(key)
    return None

@register.filter
def feat_field(org, field_name):
    """Return the value of an org boolean feature field by name. Used in feature settings template."""
    if org is None:
        return False
    return bool(getattr(org, field_name, False))

@register.filter
def feat_allowed(org, field_name):
    """True if this Django field's feature key is on the org's superadmin-granted allowlist."""
    from school.features import FIELD_TO_KEY_MAP, is_feature_allowed
    if org is None:
        return True
    key = FIELD_TO_KEY_MAP.get(field_name)
    if key is None:
        return True
    return is_feature_allowed(org, key)

@register.filter
def feat_is_free(field_name):
    """True if the Django field's feature is free (no charge)."""
    from school.features import FIELD_TO_KEY_MAP, is_free
    key = FIELD_TO_KEY_MAP.get(field_name)
    if key is None:
        return True  # fields without a paid key (e.g. auto_checkin) are treated as free
    return is_free(key)


@register.filter
def feat_price(field_name):
    """Annual price (Rs) for the Django field's feature. 0 for free features."""
    from school.features import FIELD_TO_KEY_MAP, feature_price
    key = FIELD_TO_KEY_MAP.get(field_name)
    if key is None:
        return 0
    return feature_price(key)


@register.filter
def getattr_filter(obj, attr):
    """Generic getattr filter: {{ obj|getattr_filter:'some_field' }}"""
    return getattr(obj, attr, None)

@register.filter
def in_list(value, container):
    """Membership test: {{ value|in_list:some_list_or_set }}. Django's {% with %}
    only accepts a single filter expression, not an `in` boolean expression,
    so this is the template-side equivalent of `value in container`."""
    if container is None:
        return False
    return value in container

@register.simple_tag
def has_org_feature(org, feature_key):
    """{% has_org_feature org 'payroll' as feat_enabled %}"""
    from school.features import has_feature
    return has_feature(org, feature_key)
