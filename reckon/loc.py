#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import collections
import threading
from typing import Callable

try:
    from reprlib import repr
except ImportError:
    pass

from . import protos


class LocalCache(protos.ProtoCache):
    """A Localized cache.

    Can be implemented as a globalized cache by initializing at the top-level of a module.
    """

    def __init__(
        self,
        *,
        target_usage: float = None,
        strategy: protos.CacheStrategy = protos.CacheStrategy.DYN
    ):
        self._lock = threading.RLock()
        with self._lock:
            self.TARGET_RATIO = (
                target_usage if target_usage is not None else self.TARGET_RATIO
            )
            self._cache = dict()
            self._locks = collections.defaultdict(threading.RLock)
            self._hits = 0
            self._misses = 0
            self.strategy = strategy

    __getitem__ = protos.cache_getitem
    get = protos.cache_get
    keys = protos.cache_keys
    values = protos.cache_values
    items = protos.cache_items
    info = protos.cache_info
    clear = protos.clear_cache
    size = protos.cache_size
    usage = protos.memory_usage_ratio
    memoize = protos.memoize
    set_target_usage = protos.set_target_memory_use_ratio
    # Assigned on init.
    shrink = protos.shrink


def memoize(
    _func: Callable = None,
    *,
    target_usage: float = LocalCache.TARGET_RATIO,
    strategy: protos.CacheStrategy = protos.CacheStrategy.DYN
) -> Callable:
    cache = LocalCache(target_usage=target_usage, strategy=strategy)

    return cache.memoize(_func) if _func else cache.memoize
