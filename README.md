reckon: Dead-simple, dynamic memoization
==============================================================================
[![image](https://img.shields.io/pypi/v/reckon.svg)](https://pypi.org/project/reckon/)
[![image](https://img.shields.io/pypi/l/reckon.svg)](https://pypi.org/project/reckon/)
[![image](https://img.shields.io/pypi/pyversions/reckon.svg)](https://pypi.org/project/reckon/)
[![image](https://img.shields.io/github/languages/code-size/seandstewart/reckon.svg?style=flat)](https://github.com/seandstewart/reckon)
[![image](https://img.shields.io/travis/seandstewart/reckon.svg)](https://travis-ci.org/seandstewart/reckon)
[![codecov](https://codecov.io/gh/seandstewart/reckon/branch/master/graph/badge.svg)](https://codecov.io/gh/seandstewart/reckon)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/ambv/black)

## Installation

In order to install the latest version, simply `pip3 install
-U reckon`.

This library requires Python 3.6 or greater.


## What is it?
`reckon` implements a dynamic LRU cache by automatically
monitoring the memory usage of your machine and purging
entries as it approaches a pre-defined ratio (defaults to
90%).

`reckon` is largely inspired by the `global_lru_cache`
package, so credit should be given for the initial
implementation. This package brings those ideas into python3
and adds a local cache implementation as well.


## Usage
Usage is simple:

```python
import reckon

@reckon.memoize
def some_expensive_func(foo: int, bar: int):
    return foo ** bar
```

`reckon` will automatically make use of the global cache. 

While the global cache is automatically maintained, it may
be necessary to managed the cache manually. To that purpose,
reckon provides the following global methods:
- `reckon.glob.clear`: Clear the global cache.
- `reckon.glob.shrink`: Shrink the global cache.
- `reckon.glob.usage`: Check the current usage ratio.
- `reckon.glob.set_usage`: Set the max memory usage ratio
  for the global cache.
- `reckon.glob.info`: View high-level information about the
  cache - similar to `functools.lru_cache.cache_info`

If you wish to only maintain a cache local to a function you
can simply pass a flag to the decorator:

```python
import reckon

@reckon.memoize(locale="local")
def some_expensive_func(foo: int, bar: int):
    return foo ** bar
```

Additionally, if you wish to maintain a cache local to a
module, you can initialize your own instance of the
`LocalCache` object:

```python
import reckon

cache = reckon.local()

@cache.memoize
def some_expensive_func(foo: int, bar: int):
    return foo ** bar
```

The local cache instance maintains the same high-level API
for management as the global cache:

- `LocalCache.clear`: Clear the local cache.
- `LocalCache.shrink`: Shrink the local cache.
- `LocalCache.usage`: Check the current usage ratio.
- `LocalCache.set_usage`: Set the max memory usage ratio for
  the local cache.
- `LocalCache.info`: View high-level information about the
  cache - similar to `functools.lru_cache.cache_info`

All memoized functions have introspection into their cache
via the `cache` attribute.

## Documentation

Full documentation coming soon!


## How to Contribute
1.  Check for open issues or open a fresh issue to start a 
    discussion around a feature idea or a bug.
2.  Create a branch on Github for your issue or fork
    [the repository](https://github.com/seandstewart/reckon)
    on GitHub to start making your changes to the **master**
    branch.
3.  Write a test which shows that the bug was fixed or that 
    the feature works as expected.
4.  Send a pull request and bug the maintainer until it gets
     merged and published. :)
