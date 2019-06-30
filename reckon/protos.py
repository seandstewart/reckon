#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import abc
import dataclasses
import enum
import functools
import inspect
import threading
from collections import deque
from gc import collect as gc_collect
from time import time
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
    Iterable,
    Deque,
    Iterator,
    MutableMapping
)

import psutil

from .util import size


class CacheStrategy(str, enum.Enum):
    """An enumeration of the different caching strategies."""

    TTL = "ttl"  # doc: Use a 'time-to-live' caching strategy.
    LRU = "lru"  # doc: Use a 'least-recently-used' caching strategy.
    DYN = (
        "dynamic"
    )  # doc: Use a dynamic caching strategy based upon size of the cache and overall memory usage.


_DEFAULT_TTL_SECS = 300


@functools.total_ordering
@dataclasses.dataclass
class CacheEntry:
    """An entry in the cache."""

    func: Callable
    key: Hashable
    duration: float
    result: Any
    args: Tuple
    kwargs: Dict[str, Any]
    expiration: Optional[int] = None
    lock: threading.RLock = dataclasses.field(default_factory=threading.RLock)
    strategy: CacheStrategy = CacheStrategy.DYN

    def __post_init__(self):
        self._size = None
        with self.lock:
            self.last_used = time()
            self.ttl = None
            if self.strategy == CacheStrategy.TTL and not self.expiration:
                self.expiration = _DEFAULT_TTL_SECS
            self.update_ttl()
            self._get_score = (
                self._dynamic_score
                if self.strategy == CacheStrategy.DYN
                else (
                    self._lru_score
                    if self.strategy == CacheStrategy.LRU
                    else self._ttl_score
                )
            )

    def __eq__(self, other):
        with self.lock:
            return self.score == other.score

    def __lt__(self, other):
        with self.lock:
            return self.score < other.score

    def __hash__(self):
        with self.lock:
            return self.key

    def __sizeof__(self) -> float:
        return self.size

    @property
    def size(self):
        with self.lock:
            if self._size is None:
                self._size = size(self.result)
        return self._size

    @property
    def age(self) -> float:
        with self.lock:
            return time() - self.last_used

    def _dynamic_score(self) -> float:
        """Return a score based on a factor of size, duration, and age.

        The higher the value, the sooner it's evicted.
        """
        return (self.size * self.duration) / (self.age ** 2)

    def _lru_score(self) -> float:
        """Return a score based on when this entry was last used.

        The higher the value, the older it is.
        """
        return self.age

    def _ttl_score(self) -> float:
        """Return a score based on time to live.

        Positive values indicate the entry has expired, the higher the value the older the item.
        """
        return self.ttl - time()

    def _get_score(self) -> float:
        # assigned on init
        pass

    @property
    def score(self) -> float:
        with self.lock:
            return self._get_score()

    def update_ttl(self):
        with self.lock:
            self.ttl = time() + self.expiration if self.expiration else None

    def refresh(self, now: float):
        if self.ttl and now > self.ttl:
            self.result = self.func(*self.args, **self.kwargs)
            self._size = None
        self.update_ttl()

    @property
    def res(self) -> Any:
        with self.lock:
            now = time()
            self.refresh(now)
            self.last_used = now
            return self.result


class CacheInfo(NamedTuple):
    strategy: CacheStrategy
    entries: int
    size: float
    usage: float
    max: float
    hits: int
    misses: int


class ProtoCache(abc.ABC, MutableMapping):
    """An abstract class for implementing a thread-safe cache."""

    TARGET_RATIO = 90.0
    strategy: CacheStrategy
    _lock: threading.RLock
    _cache: Dict[Hashable, CacheEntry]
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
    def keys(self) -> Iterable[Hashable]:
        pass

    @abc.abstractmethod
    def values(self) -> Deque[CacheEntry]:
        pass

    @abc.abstractmethod
    def items(self) -> Iterator[Tuple[Hashable, CacheEntry]]:
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


def cache_info(instance: CacheType) -> CacheInfo:
    return CacheInfo(
        strategy=instance.strategy,
        entries=len(instance._cache),
        size=instance.size(),
        usage=instance.usage(),
        max=instance.TARGET_RATIO,
        hits=instance._hits,
        misses=instance._misses,
    )


def cache_keys(instance: CacheType) -> Iterable[Hashable]:
    return instance._cache.keys()


def cache_values(instance: CacheType) -> Deque[CacheEntry]:
    return deque(sorted(instance._cache.values()))


def cache_items(instance: CacheType) -> Iterator[Tuple[Hashable, CacheEntry]]:
    return ((x.key, x) for x in instance.values())


def cache_getitem(instance: CacheType, key: Hashable) -> CacheEntry:
    return instance._cache.__getitem__(key)


def cache_get(
    instance: CacheType, key: Hashable, default: CacheEntry = None
) -> Optional[CacheEntry]:
    return instance._cache.get(key, default=default)


def cache_size(instance: CacheType) -> int:
    return size(instance) + size(instance._cache)


def _should_shrink(
    current: float, target: float, start: float, instance: CacheType
) -> bool:
    return (
        (current is None or current > target)
        and time() - start < _MAX_SHRINK_TIME
        and instance._cache
    )


def shrink_dynamic_cache(instance: CacheType):
    """Shrink the cache until the pct avail memory is under the target usage.

    Calculate the current size of our global cache, get the current size of free memory,
    and delete cache entries until the ratio of cache size to free memory is under the
    target ratio.
    """
    target_usage = instance.TARGET_RATIO
    should_delete = functools.partial(
        _should_shrink, target=target_usage, start=time(), instance=instance
    )

    with instance._lock:
        # Localizing variables for faster access in the while loop.
        cacheusage = instance.usage
        mem_ratio = _get_mem().percent
        cleanup = mem_ratio > target_usage

        if cleanup:
            entries = instance.values()
            entriespop = entries.popleft
            cachepop = instance._cache.pop
            while entries and should_delete(mem_ratio):
                entry = entriespop()
                cachepop(entry.key)
                del entry
                mem_ratio = _get_mem().percent

            gc_collect()


# Using the same algo for now, since the effective diff is determined by the score....
# may change if we decide to do based on num entries rather than size.
shrink_lru_cache = shrink_dynamic_cache


def shrink_ttl_cache(instance: CacheType):
    """Clean up all entries which are older then the TTL."""
    entries = instance.values()
    entriespop = entries.popleft
    score = entries[-1].score

    while entries and score >= 0:
        entry = entriespop()
        score = entry.score
        del entry


def shrink(instance: CacheType):
    if instance.strategy == CacheStrategy.DYN:
        shrink_dynamic_cache(instance)
    elif instance.strategy == CacheStrategy.TTL:
        shrink_ttl_cache(instance)
    else:
        shrink_lru_cache(instance)


_get_mem = psutil.virtual_memory


def memory_usage_ratio(instance: CacheType):
    """Estimate the ratio of used RAM to available RAM by this cache.

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
        gc_collect()


def set_target_memory_use_ratio(instance: CacheType, ratio: float):
    """Set the target ratio of available memory to maintain.

    Keep in mind, setting this too low could result in effectively no cache usage.
    """
    with instance._lock:
        instance.target_memory_use_ratio = ratio


def _create_entry(
    func: Callable,
    key: int,
    args: Tuple[Hashable, ...],
    kwargs: Dict[str, Any],
    *,
    expiration: int = None,
    strategy: CacheStrategy = CacheStrategy.DYN
) -> CacheEntry:
    start = time()
    result = func(*args, **kwargs)
    end = time()
    duration = end - start

    entry = CacheEntry(
        func=func,
        key=key,
        duration=duration,
        result=result,
        expiration=expiration,
        args=args,
        kwargs=kwargs,
        strategy=strategy,
    )
    return entry


def memoize(instance: CacheType, func: Callable, *, expiration: int = None) -> Callable:
    """Maintain a dynamically sized cache for memoized function calls.

    Return cached results if possible.

    Entries are sorted by initial execution time and overall size:
        - Larger results are ranked higher,
        - Longer execution times are ranked lower,
        - Entries are evicted from highest to lowest ranking.

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
                entry = _create_entry(
                    func=func,
                    key=key,
                    args=args,
                    kwargs=kwargs,
                    expiration=expiration,
                    strategy=instance.strategy,
                )
                instance._cache[key] = entry
                result = entry.res
                instance._misses += 1
            instance.shrink()

            return result

    return _memoized
