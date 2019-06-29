#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import enum
from typing import Callable

from reckon import glob, loc
from reckon.protos import CacheStrategy
from reckon.util import size


__all__ = ("glob", "loc", "memoize", "CacheLocale", "local", "size", "CacheStrategy")


class CacheLocale(str, enum.Enum):
    GLOB = "global"
    LOC = "local"


def memoize(
    _func: Callable = None,
    *,
    locale: CacheLocale = CacheLocale.GLOB,
    strategy: CacheStrategy = CacheStrategy.DYN,
    max_mem_usage: float = None
):
    locale = CacheLocale(locale)
    if locale == CacheLocale.GLOB:
        if max_mem_usage is not None:
            glob.set_usage(max_mem_usage)
        return glob.memoize(_func) if _func else glob.memoize
    else:
        return loc.memoize(_func, target_usage=max_mem_usage, strategy=strategy)


def local(max_mem_usage: float = None, strategy: CacheStrategy = CacheStrategy.DYN):
    return loc.LocalCache(target_usage=max_mem_usage, strategy=strategy)
