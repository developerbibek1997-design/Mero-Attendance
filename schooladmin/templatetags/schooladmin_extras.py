from django import template

register = template.Library()

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
def getattr_filter(obj, attr):
    """Generic getattr filter: {{ obj|getattr_filter:'some_field' }}"""
    return getattr(obj, attr, None)

@register.simple_tag
def has_org_feature(org, feature_key):
    """{% has_org_feature org 'payroll' as feat_enabled %}"""
    from school.features import has_feature
    return has_feature(org, feature_key)
