#!/usr/bin/env python
# -*- coding: UTF-8 -*-

try:
    from reprlib import repr
except ImportError:
    pass


from .loc import LocalCache


__all__ = (
    "get",
    "keys",
    "values",
    "items",
    "clear",
    "shrink",
    "size",
    "memoize",
    "usage",
    "set_usage",
    "info",
)


cache = LocalCache()
get = cache.get
keys = cache.keys
values = cache.values
items = cache.items
clear = cache.clear
shrink = cache.shrink
size = cache.size
usage = cache.usage
info = cache.info
set_usage = cache.set_target_usage
memoize = cache.memoize
