from django import template
from urllib.parse import urlparse

register = template.Library()


def _item_is_current(request, item):
    if not request or not item:
        return False
    link = item.get('link_callback') or item.get('link')
    if not link:
        return False
    return urlparse(str(link)).path == request.path


@register.simple_tag(takes_context=True)
def nav_item_is_current(context, item):
    return _item_is_current(context.get('request'), item)


@register.simple_tag(takes_context=True)
def nav_group_has_active(context, group):
    request = context.get('request')
    for item in group.get('items') or []:
        if _item_is_current(request, item):
            return True
    return False
