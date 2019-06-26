#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import collections
import threading

try:
    from reprlib import repr
except ImportError:
    pass


from . import protos


__all__ = ("clear", "shrink", "memoize", "usage", "set_usage")


class GlobalCache(protos.ProtoCache):
    """Global cache. Implemented as a singleton.

    This will maintain a thread-safe, global cache for your memoization.
    The major advantage here being that you maintain a single, in-memory cache for everything,
    rather than individual caches for every wrapped function.
    """

    _cache = collections.deque()
    _lock = threading.RLock()
    _caches = collections.defaultdict(dict)
    _locks = collections.defaultdict(threading.RLock)

    clear = classmethod(protos.clear_cache)
    shrink = classmethod(protos.shrink_cache)
    usage = classmethod(protos.memory_usage_ratio)
    memoize = classmethod(protos.memoize)
    set_target_usage = classmethod(protos.set_target_memory_use_ratio)


clear = GlobalCache.clear
shrink = GlobalCache.shrink
usage = GlobalCache.usage
set_usage = GlobalCache.set_target_usage
memoize = GlobalCache.memoize
