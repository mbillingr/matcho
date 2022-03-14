from dataclasses import dataclass
from functools import reduce
from operator import or_
from typing import Any, Callable, Dict, Hashable, List, Optional

from matcho import (
    KeyMismatch,
    LengthMismatch,
    LiteralMismatch,
    Mismatch,
    Skip,
    TypeMismatch,
    CastMismatch,
)
from matcho.bindings import Repeating

__all__ = [
    "bind",
    "bind_as",
    "build_matcher",
    "default",
    "skip_mismatch",
    "skip_missing_keys",
]


def bind(name: str, dtype=None):
    """Match any data and bind it to the name."""
    return Bind(name, dtype)


@dataclass
class Bind:
    name: str
    dtype: Optional[type] = None

    def bind(self, value):
        if self.dtype is not None:
            try:
                value = self.dtype(value)
            except Exception:
                raise CastMismatch(value, self.dtype)
        return {self.name: value}


NOT_SET = object()


def bind_as(name: str, pattern: Any, default=NOT_SET):
    """Bind entire datum to name if it matches pattern"""
    return BindAs(name, pattern, default)


@dataclass
class BindAs:
    name: str
    pattern: Any
    default: Any = NOT_SET


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


class Matcher:
    def __call__(self, data):
        raise NotImplementedError(
            f"{self.__class__.__name__} must be callable to be a valid matcher."
        )


def build_matcher(pattern):
    """Build a matcher from the given pattern.

    The matcher is an object that can be called with the data to match against
    the pattern. If the match is successful, it returns a set of bindings.
    If the data can't be matched, a `Mismatch` exception is raised.

    The bindings may then be substituted in a template constructed by `build_template`.
    """
    match pattern:
        case Bind(_):
            return pattern.bind
        case BindAs(_):
            return build_binding_matcher(pattern)
        case SkipOnMismatch(pattern):
            return build_mismatch_skipper(pattern, lambda m: isinstance(m, Mismatch))
        case SkipMissingKeys(keys, pattern):
            return build_mismatch_skipper(
                pattern, lambda m: hasattr(m, "key") and m.key in keys
            )
        case [*_]:
            return build_list_matcher(pattern)
        case {}:
            return build_dict_matcher(pattern)
        case type():
            return build_type_matcher(pattern)
        case _:
            return LiteralMatcher(pattern)


class LiteralMatcher(Matcher):
    """Matches if data is equal to a literal pattern."""

    def __init__(self, literal):
        self.literal = literal

    def __call__(self, data):
        if data == self.literal:
            return {}
        raise LiteralMismatch(data, self.literal)


def build_binding_matcher(binder: BindAs):
    """Build a matcher that binds the data to the given name.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    inner_matcher = build_matcher(binder.pattern)
    return BindingMatcher(inner_matcher, binder.name, binder.default)


class BindingMatcher(Matcher):
    """Wrap another matcher. If that matches, bind its value to `name`.
    Otherwise, raise a `Mismatch` or bind the optional default value.
    """

    def __init__(self, matcher, name, default=NOT_SET):
        self.name = name
        self.matcher = matcher
        self.default = default

    def __call__(self, data):
        try:
            bindings = self.matcher(data)
            bindings |= {self.name: data}
        except Mismatch:
            if self.default is NOT_SET:
                raise
            bindings = {self.name: self.default}
        return bindings


def build_instance_matcher(expected_type):
    """Build a matcher that matches any data of given type.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    return InstanceMatcher(expected_type)


@dataclass
class InstanceMatcher(Matcher):
    """Match any value that is an instance of the expected type."""

    expected_type: type

    def __call__(self, data):
        if isinstance(data, self.expected_type):
            return {}
        raise TypeMismatch(data, self.expected_type)


def build_type_matcher(expected_type):
    """Build a matcher that matches any data that can be cast to given type.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    return TypeMatcher(expected_type)


@dataclass
class TypeMatcher(Matcher):
    """Match any value that can be cast to the expected type."""

    expected_type: type

    def transform(self, data):
        try:
            return self.expected_type(data)
        except Exception:
            raise CastMismatch(data, self.expected_type)

    def __call__(self, data):
        self.transform(data)
        return {}


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


def build_fixed_list_matcher(patterns):
    """Build a matcher that matches lists of fixed length.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matchers = [build_matcher(p) for p in patterns]
    return FixdListMatcher(matchers)


@dataclass
class FixdListMatcher(Matcher):
    """Match any list of correct length where each element
    matches its corresponding matcher."""

    element_matchers: List[Matcher]

    def __call__(self, data):
        if not isinstance(data, list):
            raise TypeMismatch(data, list)

        if len(data) != self.expected_length:
            raise LengthMismatch(len(data), self.expected_length)

        return reduce(or_, map(apply_first, zip(self.element_matchers, data)), {})

    @property
    def expected_length(self):
        return len(self.element_matchers)


def build_repeating_list_matcher(patterns):
    """Build a matcher that matches lists of variable length.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    repeating_matcher = build_matcher(patterns[-1])
    prefix_matcher = build_fixed_list_matcher(patterns[:-1])

    bound_optional_names = find_bindings(patterns[-1])

    return RepeatingListMatcher(prefix_matcher, repeating_matcher, bound_optional_names)


@dataclass
class RepeatingListMatcher(Matcher):
    """Match a list, where the last element may repeat zero or more times."""

    prefix_matcher: FixdListMatcher
    repeating_matcher: Matcher
    bound_optional_names: Dict

    def __call__(self, data):
        n_prefix = self.prefix_matcher.expected_length
        bindings = self.prefix_matcher(data[:n_prefix])

        for name in self.bound_optional_names:
            assert name not in bindings
            bindings[name] = Repeating([])

        for d in data[n_prefix:]:
            try:
                bnd = self.repeating_matcher(d)
            except Skip:
                continue

            for k, v in bnd.items():
                bindings[k].values.append(v)

        return bindings


def find_bindings(template, nesting_level=0):
    """find all names bound in given pattern and return their nesting levels"""
    bindings = {}
    match template:
        case Bind(name):
            bindings[name] = nesting_level
        case BindAs(name, pattern, _):
            bindings = find_bindings(pattern) | {name: nesting_level}
        case SkipMissingKeys(_, pattern) | SkipOnMismatch(pattern):
            bindings = find_bindings(pattern)
        case list():
            nesting_depth = sum(1 for x in template if x is ...)
            for x in template:
                bindings |= find_bindings(x, nesting_level + nesting_depth)
        case dict():
            for k, v in template.items():
                bindings |= find_bindings(v, nesting_level)
    return bindings


def build_dict_matcher(pattern):
    """Build a matcher that matches dictionaries.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matchers = {k: build_matcher(v) for k, v in pattern.items()}
    return DictMatcher(matchers)


@dataclass
class DictMatcher(Matcher):
    """Match dictionary values according to their keys."""

    item_matchers: Dict[Any, Matcher]

    def __call__(self, data):
        if not isinstance(data, dict):
            raise TypeMismatch(data, dict)

        bindings = {}
        for k, m in self.item_matchers.items():
            d = lookup(data, k)
            bindings |= m(d)
        return bindings


def build_mismatch_skipper(pattern, predicate):
    """Build a matcher that replaces exceptions of a given type with `Skip` exceptions.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matcher = build_matcher(pattern)
    return ErrorHandlingMatcher(matcher, predicate)


@dataclass
class ErrorHandlingMatcher:
    """Skip any `Mismatches` of the correct subtype raised by the
    wrapped matcher if they satisfy an optional predicate."""

    matcher: Matcher
    predicate: Callable

    def __call__(self, data):
        try:
            return self.matcher(data)
        except Exception as e:
            if self.predicate(e):
                raise Skip()
            raise


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
