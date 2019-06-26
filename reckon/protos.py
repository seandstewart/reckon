#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import abc
import dataclasses
import functools
import gc
import inspect
import time
import threading
from collections import deque
from types import MappingProxyType
from typing import (
    Deque,
    Dict,
    Hashable,
    Any,
    Tuple,
    Optional,
    Callable,
    Union,
    Type,
    DefaultDict,
)

import psutil

from .util import size


@dataclasses.dataclass
class CacheEntry:
    func: Callable
    key: Hashable
    duration: float
    result: Any
    args: Tuple
    kwargs: Dict[str, Any]
    expiration: Optional[int] = None
    lock: threading.RLock = dataclasses.field(default_factory=threading.RLock)

    def __post_init__(self):
        with self.lock:
            self.last_used = time.time()
            self.time_to_expire = None
            self.update_time_to_expire()
            self.size = size(self.result)

    def delete(self):
        with self.lock:
            del self.func._cache[self.key]

    def __del__(self):
        self.delete()

    def __eq__(self, other):
        with self.lock:
            return self.score == other.score

    def __lt__(self, other):
        with self.lock:
            return self.score < other.score

    def __hash__(self):
        with self.lock:
            return self.key

    def recalculate_size(self) -> float:
        with self.lock:
            self.size = size(self._result)
            return self.size

    def __sizeof__(self) -> float:
        return self.size

    @property
    def age(self) -> float:
        with self.lock:
            return time.time() - self.last_used

    @property
    def score(self) -> float:
        with self.lock:
            return (self.size * self.duration) / (self.age ** 2)

    def update_time_to_expire(self):
        if self.expiration:
            self.time_to_expire = time.time() + self.expiration
        else:
            self.time_to_expire = None

    def refresh(self):
        self.recalculate_size()
        self.update_time_to_expire()

    @property
    def res(self) -> Any:
        with self.lock:
            if self.time_to_expire is not None and time.time() > self.time_to_expire:
                self.result = self.func(*self.args, **self.kwargs)
                self.refresh()
            self.last_used = time.time()
            return self.result


class ProtoCache(abc.ABC):
    """An abstract class for implementing a thread-safe cache."""

    TARGET_RATIO = 1.0
    _cache: Deque[CacheEntry]
    _lock: threading.RLock
    _caches: DefaultDict[Callable, Dict[Hashable, CacheEntry]]
    _locks = DefaultDict[Hashable, threading.RLock]

    @abc.abstractmethod
    def usage(self) -> float:
        pass

    @abc.abstractmethod
    def set_target_usage(self):
        pass

    @abc.abstractmethod
    def shrink(self):
        pass

    @abc.abstractmethod
    def clear(self):
        pass

    @abc.abstractmethod
    def memoize(self, func: Callable) -> Callable:
        pass


CacheType = Union[ProtoCache, Type[ProtoCache]]


def shrink_cache(cls_or_instance: CacheType, target_usage: float = None):
    """Shrink the cache until the pct avail memory is under the target usage.

    Calculate the current size of our global cache, get the current size of free memory,
    and delete cache entries until the ratio of cache size to free memory is under the
    target ratio.
    """
    cleanup = False
    if not target_usage:
        target_usage = cls_or_instance.TARGET_RATIO

    with cls_or_instance._lock:
        mem_ratio = cls_or_instance.usage()
        if mem_ratio > target_usage:
            cleanup = True
            cls_or_instance._cache = deque(
                sorted(cls_or_instance._cache, key=lambda i: i.score, reverse=True)
            )
        start = time.time()

        def should_delete(mem_usage):
            return (
                (mem_usage is None or mem_usage > target_usage)
                and time.time() - start < 1
                and cls_or_instance._cache
            )

        while should_delete(cls_or_instance.usage()):
            try:
                cls_or_instance._cache.pop().delete()
            except IndexError:
                break
        if cleanup:
            gc.collect()


def memory_usage_ratio(cls_or_instance: CacheType):
    """
    Calculate the ratio of used RAM to available RAM.
    The ratio is designed to reserve at least a tenth of available
    system memory no matter what.
    """
    with cls_or_instance._lock:
        ratio = float(
            1.0
            * size(cls_or_instance._cache)
            / (psutil.virtual_memory().available - (psutil.virtual_memory().total / 10))
        )
        return None if ratio < 0 else ratio


def clear_cache(cls_or_instance: CacheType):
    """
    Clear all of the existing cache entries.
    """
    with cls_or_instance._lock:
        while cls_or_instance._cache:
            cls_or_instance._cache.pop().delete()


def set_target_memory_use_ratio(cls_or_instance: CacheType, ratio: float):
    with cls_or_instance._lock:
        cls_or_instance.target_memory_use_ratio = ratio


def memoize(cls_or_instance: CacheType, func: Callable) -> Callable:
    """
    Cache the results of calling func with args and kw. Return cached
    results if possible. Maintain a dynamically sized cache based on
    function execution time and the available free memory ratio.
    You probably should use the memoized decorator instead of calling this
    directly.
    """
    func.cache = MappingProxyType(cls_or_instance._caches[func])

    @functools.wraps(func)
    def _memoized(*args, **kwargs) -> Any:

        with cls_or_instance._locks[func], cls_or_instance._lock:

            try:
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                key = frozenset(bound.arguments.items())
                cache = cls_or_instance._caches[func]
                if key in cache:
                    result = cache[key].res
                    cls_or_instance.shrink()
                    return result
            # received an unhashable input, can't cache this.
            except TypeError:
                result = func(*args, **kwargs)
                return result

            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            duration = end - start

            entry = CacheEntry(
                func=func,
                key=key,
                duration=duration,
                result=result,
                expiration=kwargs.get("expiration"),
                args=args,
                kwargs=kwargs,
            )
            cls_or_instance.shrink()
            cls_or_instance._caches[func][key] = entry
            cls_or_instance._cache.append(entry)

            return result

    return _memoized
