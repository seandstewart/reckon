#!/usr/bin/env python
# -*- coding: UTF-8 -*-
from collections import deque
from itertools import chain
from sys import getsizeof, stderr
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


def size(o, *, handlers: Mapping[Type, Callable] = None, verbose: bool = False) -> int:
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
    default_size = getsizeof(0)  # estimate sizeof object without __sizeof__

    def sizeof(o: Any) -> int:
        if id(o) in seen:  # do not double count the same object
            return 0

        seen.add(id(o))
        s = getsizeof(o, default_size)

        if verbose:
            print(s, type(o), repr(o), file=stderr)

        typ = type(o)
        handler = handlers.get(typ) or _DEFAULT_SIZE_HANDLERS.get(typ)
        if handler:
            s += sum(map(sizeof, handler(o)))

        return s

    return sizeof(o)
