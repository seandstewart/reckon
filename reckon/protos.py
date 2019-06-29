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
from typing import (
    Dict,
    Hashable,
    Any,
    Tuple,
    Optional,
    Callable,
    Union,
    Type,
    DefaultDict,
    NamedTuple,
    FrozenSet,
)

import psutil

from .util import size


@functools.total_ordering
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


class CacheInfo(NamedTuple):
    entries: int
    size: float
    usage: float
    max: float
    hits: int
    misses: int


class ProtoCache(abc.ABC):
    """An abstract class for implementing a thread-safe cache."""

    TARGET_RATIO = 1.0
    _lock: threading.RLock
    _cache: Dict[FrozenSet[Union[Callable, Tuple[Hashable, ...]]], CacheEntry]
    _locks: DefaultDict[Hashable, threading.RLock]
    _hits: int
    _misses: int

    @abc.abstractmethod
    def __getitem__(self, key: Hashable) -> CacheEntry:
        pass

    @abc.abstractmethod
    def get(self, key: Hashable, default: CacheEntry = None) -> Optional[CacheEntry]:
        pass

    @abc.abstractmethod
    def size(self) -> int:
        pass

    @abc.abstractmethod
    def info(self) -> CacheInfo:
        pass

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
# Seriously, we should never block for more than a millisecond.
_MAX_SHRINK_TIME = 0.001


def _should_shrink(
    current: float, target: float, start: float, instance: CacheType
) -> bool:
    return (
        (current is None or current > target)
        and time.time() - start < _MAX_SHRINK_TIME
        and instance._cache
    )


def cache_info(instance: CacheType) -> CacheInfo:
    return CacheInfo(
        entries=len(instance._cache),
        size=instance.size(),
        usage=instance.usage(),
        max=instance.TARGET_RATIO,
        hits=instance._hits,
        misses=instance._misses,
    )


def cache_getitem(instance: CacheType, key: Hashable) -> CacheEntry:
    return instance._cache.__getitem__(key)


def cache_get(
    instance: CacheType, key: Hashable, default: CacheEntry = None
) -> Optional[CacheEntry]:
    return instance._cache.get(key, default=default)


def cache_size(instance: CacheType) -> int:
    return size(instance) + size(instance._cache)


def shrink_cache(instance: CacheType, target_usage: float = None):
    """Shrink the cache until the pct avail memory is under the target usage.

    Calculate the current size of our global cache, get the current size of free memory,
    and delete cache entries until the ratio of cache size to free memory is under the
    target ratio.
    """
    target_usage = target_usage or instance.TARGET_RATIO
    should_delete = functools.partial(
        _should_shrink, target=target_usage, start=time.time(), instance=instance
    )

    with instance._lock:
        # Localizing variables for faster access in the while loop.
        cacheusage = instance.usage
        mem_ratio = cacheusage()
        entries = deque(sorted(instance._cache.values()))
        cleanup = mem_ratio > target_usage
        entriespop = entries.popleft
        cachepop = instance._cache.pop

        while entries and should_delete(mem_ratio):
            entry = entriespop()
            cachepop(entry.key)
            del entry
            mem_ratio = cacheusage()

    if cleanup:
        gc.collect()


_get_mem = psutil.virtual_memory


def memory_usage_ratio(instance: CacheType):
    """Calculate the ratio of used RAM to available RAM.

    The ratio is designed to reserve at least a tenth of available
    system memory no matter what.
    """
    with instance._lock:
        mem = _get_mem()
        ratio = float(size(instance._cache) / (mem.available - (mem.total / 10)))
        return None if ratio < 0 else ratio


def clear_cache(instance: CacheType):
    """Clear all of the existing cache entries."""
    with instance._lock:
        # Localizing variables for faster access in the while loop.
        instance._cache.clear()
        instance._misses = 0
        instance._hits = 0
        gc.collect()


def set_target_memory_use_ratio(instance: CacheType, ratio: float):
    """Set the target ratio to maintain.

    Keep in mind, setting this too low could result in effectively no cache usage.
    """
    with instance._lock:
        instance.target_memory_use_ratio = ratio


def _create_entry(
    func: Callable,
    key: FrozenSet,
    args: Tuple[Hashable, ...],
    kwargs: Dict[str, Any],
    *,
    expiration: int = None
) -> CacheEntry:
    start = time.time()
    result = func(*args, **kwargs)
    end = time.time()
    duration = end - start

    entry = CacheEntry(
        func=func,
        key=key,
        duration=duration,
        result=result,
        expiration=expiration,
        args=args,
        kwargs=kwargs,
    )
    return entry


def memoize(instance: CacheType, func: Callable) -> Callable:
    """
    Cache the results of calling func with args and kw. Return cached
    results if possible. Maintain a dynamically sized cache based on
    function execution time and the available free memory ratio.
    You probably should use the memoized decorator instead of calling this
    directly.
    """
    func.cache = instance

    @functools.wraps(func)
    def _memoized(*args, **kwargs) -> Any:

        with instance._lock:
            try:
                sig = inspect.signature(func)
                bound = sig.bind(*args, **kwargs)
                key = hash(frozenset(set(bound.arguments.items()) | {func}))
            # received an unhashable input, can't cache this.
            except TypeError:
                instance._misses += 1
                return func(*args, **kwargs)

            if key in instance._cache:
                result = instance._cache[key].res
                instance._hits += 1
            else:
                entry = _create_entry(func, key, args, kwargs)
                instance._cache[key] = entry
                result = entry.res
                instance._misses += 1
            instance.shrink()

            return result

    return _memoized
