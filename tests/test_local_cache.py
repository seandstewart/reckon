#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import reckon

cache = reckon.local()


@cache.memoize
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def test_instance():
    assert fib.cache is cache


def test_cache_info_equal():
    [fib(n) for n in range(16)]
    expected = cache.info()
    info = fib.cache.info()
    assert expected == info


def test_cache_info_values():
    [fib(n) for n in range(16)]
    info = cache.info()
    assert info.entries == len(cache.keys())
    assert info.size == cache.size()
    assert info.usage == cache.usage()
    assert info.max == cache.TARGET_RATIO
    assert info.hits == cache._hits
    assert info.misses == cache._misses


def test_cache_clear():
    [fib(n) for n in range(16)]
    assert cache.keys()
    cache.clear()
    assert not cache.keys()
