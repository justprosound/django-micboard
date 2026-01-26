from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Template filter to look up a key in a dictionary."""
    if not dictionary:
        return None
    return dictionary.get(key)
