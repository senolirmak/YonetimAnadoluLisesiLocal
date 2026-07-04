# -*- coding: utf-8 -*-
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_attr(obj, attr_name):
    """okul/yonetim liste şablonlarında dinamik alan/metot erişimi için."""
    try:
        value = getattr(obj, attr_name)
    except Exception:
        return ""
    if callable(value):
        try:
            value = value()
        except Exception:
            return ""
    if isinstance(value, bool):
        return "Evet" if value else "Hayır"
    return value
