from dataclasses import dataclass
from functools import reduce
from operator import or_
from typing import Any, Hashable

from matcho import (
    KeyMismatch,
    LengthMismatch,
    LiteralMismatch,
    Mismatch,
    Skip,
    TypeMismatch,
)
from matcho.bindings import Repeating

__all__ = ["bind", "build_matcher", "default", "skip_mismatch", "skip_missing_keys"]


def bind(name: str):
    """Match any data and bind it to the name."""
    return Bind(name)


@dataclass
class Bind:
    name: str


def default(key: Hashable, value: Any):
    """Allow a key not to be present in the data by providing a default value."""
    return Default(key, value)


@dataclass
class Default:
    key: Hashable
    default_value: Any

    def __hash__(self):
        return hash(self.key)


def skip_mismatch(pattern: Any):
    """Skip the current item in a variable sequence matcher if the wrapped pattern does not match the data."""
    return SkipOnMismatch(pattern)


@dataclass
class SkipOnMismatch:
    pattern: Any


def skip_missing_keys(keys: list, pattern: Any):
    """Skip the current item in a variable sequence matcher if one of the given keys is not present in the data."""
    return SkipMissingKeys(keys, pattern)


@dataclass
class SkipMissingKeys:
    keys: list
    pattern: Any


def build_matcher(pattern):
    """Build a matcher from the given pattern.

    The matcher is an object that can be called with the data to match against
    the pattern. If the match is successful, it returns a set of bindings.
    If the data can't be matched, a `Mismatch` exception is raised.

    The bindings may then be substituted in a template constructed by `build_template`.
    """
    match pattern:
        case Bind(name):
            return build_binding_matcher(name)
        case SkipOnMismatch(pattern):
            return build_mismatch_skipper(pattern, Mismatch, lambda _: True)
        case SkipMissingKeys(keys, pattern):
            return build_mismatch_skipper(pattern, KeyMismatch, lambda k: k in keys)
        case [*_]:
            return build_list_matcher(pattern)
        case {}:
            return build_dict_matcher(pattern)
        case _:
            return build_literal_matcher(pattern)


def build_literal_matcher(pattern):
    """Build a matcher for data that must be equal to a pattern.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """

    def match_literal(data):
        if data == pattern:
            return {}
        raise LiteralMismatch(data, pattern)

    return match_literal


def build_binding_matcher(name):
    """Build a matcher that binds the data to the given name.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    return lambda data: {name: data}


def build_instance_matcher(expected_type):
    """Build a matcher that matches any data of given type.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """

    def match_instance(data):
        if isinstance(data, expected_type):
            return {}
        raise TypeMismatch(data, expected_type)

    return match_instance


def build_list_matcher(pattern):
    """Build a matcher that matches lists.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """

    class Special:
        ELLIPSIS = ...

    match pattern:
        case [*prefix, last] if last is not ... and ... in prefix:
            raise ValueError("Ellipsis can't be followed by non-ellipsis list elements")
        case [Special.ELLIPSIS]:
            return build_instance_matcher(list)
        case [*prefix, Special.ELLIPSIS]:
            return build_repeating_list_matcher(prefix)
        case _:
            return build_fixed_list_matcher(pattern)


def build_fixed_list_matcher(pattern):
    """Build a matcher that matches lists of fixed length.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matchers = [build_matcher(p) for p in pattern]

    def match_fixed_list(data):
        if not isinstance(data, list):
            raise TypeMismatch(data, list)

        if len(data) != len(matchers):
            raise LengthMismatch(len(data), len(matchers))

        return reduce(or_, map(apply_first, zip(matchers, data)), {})

    return match_fixed_list


def build_repeating_list_matcher(patterns):
    """Build a matcher that matches lists of variable length.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    repeating_matcher = build_matcher(patterns[-1])
    prefix_matchers = [build_matcher(p) for p in patterns[:-1]]
    n_prefix = len(prefix_matchers)

    def match_repeating(data):
        if not isinstance(data, list):
            raise TypeMismatch(data, list)

        if len(data) <= n_prefix:
            raise LengthMismatch(len(data), n_prefix + 1)

        bindings = reduce(
            or_, map(apply_first, zip(prefix_matchers[:n_prefix], data[:n_prefix])), {}
        )

        for d in data[n_prefix:]:
            try:
                bnd = repeating_matcher(d)
            except Skip:
                continue

            for k, v in bnd.items():
                bindings.setdefault(k, Repeating([])).values.append(v)

        return bindings

    return match_repeating


def build_dict_matcher(pattern):
    """Build a matcher that matches dictionaries.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matchers = {k: build_matcher(v) for k, v in pattern.items()}

    def match_dict(data):
        bindings = {}
        for k, m in matchers.items():
            d = lookup(data, k)
            bindings |= m(d)
        return bindings

    return match_dict


def build_mismatch_skipper(pattern, mismatch_type, predicate=lambda _: True):
    """Build a matcher that replaces exceptions of a given type with `Skip` exceptions.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matcher = build_matcher(pattern)

    def error_handling_matcher(data):
        try:
            return matcher(data)
        except mismatch_type as mm:
            if predicate(mm.args[1]):
                raise Skip()
            raise

    return error_handling_matcher


def apply_first(seq):
    """Call the first item in a sequence with the remaining
    sequence as positional arguments."""
    f, *args = seq
    return f(*args)


def lookup(mapping, key):
    """Lookup a key in a mapping.

    If the mapping does not contain the key a `KeyMismatch` is raised, unless
    the key is a `Default`. In the latter case, its default value is returned.
    """
    if isinstance(key, Default):
        return mapping.get(key.key, key.default_value)

    try:
        return mapping[key]
    except KeyError:
        pass

    raise KeyMismatch(mapping, key)
