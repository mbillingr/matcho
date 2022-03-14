from dataclasses import dataclass
from functools import reduce, singledispatch
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

NOT_SET = object()


def bind(name: str, dtype=None):
    """Match any data and bind it to the name."""
    return Bind(name, dtype)


def bind_as(name: str, pattern: Any, default_value=NOT_SET):
    """Bind entire datum to name if it matches pattern"""
    return BindAs(name, pattern, default_value)


def default(key: Hashable, value: Any):
    """Allow a key not to be present in the data by providing a default value."""
    return Default(key, value)


def skip_mismatch(pattern: Any):
    """Skip the current item in a variable sequence matcher if the wrapped pattern does not match the data."""
    return SkipOnMismatch(pattern)


def skip_missing_keys(keys: list, pattern: Any):
    """Skip the current item in a variable sequence matcher if one of the given keys is not present in the data."""
    return SkipMissingKeys(keys, pattern)


class Pattern:
    def build_matcher(self) -> "Matcher":
        raise NotImplementedError(f"{self.__class__.__name__}.build_matcher()")


@dataclass
class Bind(Pattern):
    name: str
    dtype: Optional[type] = None

    def build_matcher(self):
        if self.dtype is None:
            matcher = MatchAny()
        else:
            matcher = TypeMatcher(self.dtype)
        return BindingMatcher(matcher, self.name)


@dataclass
class BindAs(Pattern):
    name: str
    pattern: Any
    default: Any = NOT_SET

    def build_matcher(self):
        inner_matcher = build_matcher(self.pattern)
        return BindingMatcher(inner_matcher, self.name, self.default)


@dataclass
class Default:
    key: Hashable
    default_value: Any

    def __hash__(self):
        return hash(self.key)


@dataclass
class SkipOnMismatch(Pattern):
    pattern: Any

    def build_matcher(self) -> "Matcher":
        matcher = build_matcher(self.pattern)
        return ErrorHandlingMatcher(matcher, lambda m: isinstance(m, Mismatch))


@dataclass
class SkipMissingKeys(Pattern):
    keys: list
    pattern: Any

    def build_matcher(self) -> "Matcher":
        matcher = build_matcher(self.pattern)
        return ErrorHandlingMatcher(
            matcher, lambda m: hasattr(m, "key") and m.key in self.keys
        )


class Matcher:
    def match(self, data) -> (Any, Dict):
        raise NotImplementedError(f"{self.__class__.__name__}.match()")

    def bound_names(self, nesting_level=0):
        """return all names bound in this matcher and submatchers and return their nesting levels"""
        return {}

    def __call__(self, data):
        _, bindings = self.match(data)
        return bindings


class MatchAny(Matcher):
    """Matches any value."""

    def match(self, data):
        return data, {}


@dataclass
class LiteralMatcher(Matcher):
    """Matches if data is equal to a literal pattern."""

    literal: Any

    def match(self, data):
        if data == self.literal:
            return data, {}
        raise LiteralMismatch(data, self.literal)


@dataclass
class BindingMatcher(Matcher):
    """Wrap another matcher. If that matches, bind its value to `name`.
    Otherwise, raise a `Mismatch` or bind the optional default value.
    """

    matcher: Matcher
    name: str
    default: Any = NOT_SET

    def match(self, data):
        try:
            data_out, bindings = self.matcher.match(data)
            bindings[self.name] = data_out
        except Mismatch:
            if self.default is NOT_SET:
                raise
            bindings = {self.name: self.default}
        return data, bindings

    def bound_names(self, nesting_level=0):
        names = self.matcher.bound_names(nesting_level)
        names[self.name] = nesting_level
        return names


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

    def match(self, data):
        if isinstance(data, self.expected_type):
            return data, {}
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

    def match(self, data):
        try:
            return self.expected_type(data), {}
        except Exception:
            raise CastMismatch(data, self.expected_type)


def build_list_matcher(pattern):
    """Build a matcher that matches lists.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    if ... in pattern[:-1]:
        raise ValueError("Ellipsis is only allowed in the final position")

    if not pattern:
        return build_fixed_list_matcher(pattern)
    elif pattern == [...]:
        return build_instance_matcher(list)
    elif pattern[-1] is ...:
        return build_repeating_list_matcher(pattern[:-1])
    else:
        return build_fixed_list_matcher(pattern)


def build_fixed_list_matcher(patterns):
    """Build a matcher that matches lists of fixed length.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matchers = [build_matcher(p) for p in patterns]
    return FixedListMatcher(matchers)


@dataclass
class FixedListMatcher(Matcher):
    """Match any list of correct length where each element
    matches its corresponding matcher."""

    element_matchers: List[Matcher]

    def match(self, data):
        if not isinstance(data, list):
            raise TypeMismatch(data, list)

        if len(data) != self.expected_length:
            raise LengthMismatch(len(data), self.expected_length)

        return data, reduce(merge_dicts, map(apply_first, zip(self.element_matchers, data)), {})

    @property
    def expected_length(self):
        return len(self.element_matchers)

    def bound_names(self, nesting_level=0):
        return reduce(
            merge_dicts,
            (m.bound_names(nesting_level) for m in self.element_matchers),
            {},
        )


def build_repeating_list_matcher(patterns):
    """Build a matcher that matches lists of variable length.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    repeating_matcher = build_matcher(patterns[-1])
    prefix_matcher = build_fixed_list_matcher(patterns[:-1])

    bound_optional_names = repeating_matcher.bound_names()

    return RepeatingListMatcher(prefix_matcher, repeating_matcher, bound_optional_names)


@dataclass
class RepeatingListMatcher(Matcher):
    """Match a list, where the last element may repeat zero or more times."""

    prefix_matcher: FixedListMatcher
    repeating_matcher: Matcher
    bound_optional_names: Dict

    def match(self, data):
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

        return data, bindings

    def bound_names(self, nesting_level=0):
        bindings = self.prefix_matcher.bound_names(nesting_level)
        bindings.update(self.repeating_matcher.bound_names(nesting_level + 1))
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

    def match(self, data):
        if not isinstance(data, dict):
            raise TypeMismatch(data, dict)

        bindings = {}
        for k, m in self.item_matchers.items():
            d = lookup(data, k)
            bindings.update(m(d))
        return data, bindings

    def bound_names(self, nesting_level=0):
        return reduce(
            merge_dicts,
            (m.bound_names(nesting_level) for m in self.item_matchers.values()),
            {},
        )


def build_mismatch_skipper(pattern, predicate):
    """Build a matcher that replaces exceptions of a given type with `Skip` exceptions.

    Typically, `build_matcher` should be used instead, which delegates to
    this function where appropriate.
    """
    matcher = build_matcher(pattern)
    return ErrorHandlingMatcher(matcher, predicate)


@singledispatch
def build_matcher(pattern) -> Matcher:
    """Build a matcher from the given pattern.

    The matcher is an object that can be called with the data to match against
    the pattern. If the match is successful, it returns a set of bindings.
    If the data can't be matched, a `Mismatch` exception is raised.

    The bindings may then be substituted in a template constructed by `build_template`.

    This is a generic function. Support for additional patterns can be added with
    the `build_matcher.register(<type>, <handler>)` function. See the documentation
    of `functools.singledispatch` for further information.
    """
    return LiteralMatcher(pattern)


build_matcher.register(Pattern, lambda p: p.build_matcher())
build_matcher.register(list, build_list_matcher)
build_matcher.register(dict, build_dict_matcher)
build_matcher.register(type, build_type_matcher)


@dataclass
class ErrorHandlingMatcher(Matcher):
    """Skip any `Mismatches` of the correct subtype raised by the
    wrapped matcher if they satisfy an optional predicate."""

    matcher: Matcher
    predicate: Callable

    def match(self, data):
        try:
            return self.matcher.match(data)
        except Exception as e:
            if self.predicate(e):
                raise Skip()
            raise

    def bound_names(self, nesting_level=0):
        return self.matcher.bound_names(nesting_level)


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


def merge_dicts(a, b):
    """Return a new dict with items from two other dicts.
    This function exists for backward compatibility to replace Python 3.9's a|b.
    For performance reasons, there are no guarantees that a and b won't be modified.
    """
    a.update(b)
    return a