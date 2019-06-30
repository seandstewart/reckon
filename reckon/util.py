#!/usr/bin/env python
# -*- coding: UTF-8 -*-
from collections import deque
from itertools import chain
from sys import getsizeof
from typing import Mapping, Type, Callable, Any
from types import MappingProxyType


_DEFAULT_SIZE_HANDLERS = MappingProxyType(
    {
        tuple: iter,
        list: iter,
        deque: iter,
        dict: lambda d: chain.from_iterable(d.items()),
        set: iter,
        frozenset: iter,
    }
)
_DEFAULT_SIZE = getsizeof(0)  # estimate sizeof object without __sizeof__


def _sizeof(o: Any, seen: set, handlers: dict) -> int:
    if id(o) in seen:  # do not double count the same object
        return 0

    seen.add(id(o))
    s = getsizeof(o, _DEFAULT_SIZE)

    typ = type(o)
    handler = handlers.get(typ) or _DEFAULT_SIZE_HANDLERS.get(typ)
    if handler:
        s += sum(_sizeof(x, seen, handlers) for x in handler(o))

    return s


def size(o, *, handlers: Mapping[Type, Callable] = None) -> int:
    """Returns the approximate memory footprint an object and all of its contents.

    Other Parameters
    ----------------
    handlers
        Optionally supply a mapping of types or classes to handlers
    verbose
        Optionally pipe debug info to stderr
    """
    handlers = handlers or {}
    seen = set()  # track which object id's have already been seen

    return _sizeof(o, seen, handlers)
