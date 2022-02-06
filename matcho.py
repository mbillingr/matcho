"""
Structural pattern matching and template reconstruction.

The two primary API functions are `build_matcher` and `build_template`.
A few helper functions complement the matcher: `bind`, `default`, `skip_mismatch`, `skip_missing_keys`.
Templates may use the `insert` helper function.
"""

from dataclasses import dataclass
from functools import reduce
from operator import or_


__version__ = "0.0.0"


from typing import Any, Hashable


class Mismatch(Exception):
    """The data does not match the pattern"""


class KeyMismatch(Mismatch):
    """The data does not contain a dictionary key required by the pattern."""


class LiteralMismatch(Mismatch):
    """The data is not equal to the pattern."""


class TypeMismatch(Mismatch):
    """The data has the wrong type."""


class LengthMismatch(Mismatch):
    """The data has the wrong length."""


class Skip(Exception):
    """If inside a variable sequence matcher, skip the current element."""


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


@dataclass
class Repeating:
    """A repeated binding."""

    values: list


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


def insert(name):
    """Mark a place in the template where to insert the value bound to name."""
    return Insert(name)


@dataclass
class Insert:
    name: str

    def __hash__(self):
        return hash(self.name)


def build_template(spec):
    """Build a template from a specification.

    The resulting template is an object that when called with a set of
    bindings (as produced by a matcher from `build_matcher`), returns
    an instance of the template with names substituted by their bound values.
    """
    match spec:
        case Insert(name):
            return build_insertion_template(name)
        case list(_):
            return build_list_template(spec)
        case dict(_):
            return build_dict_template(spec)
        case _:
            return lambda *_: spec


def build_insertion_template(name):
    """Build a template that is substituted with values bound to name.

    Typically, `build_template` should be used instead, which delegates to
    this function where appropriate.
    """

    def instantiate(bindings, nesting_level=()):
        value = get_nested(bindings[name], nesting_level)
        if isinstance(value, Repeating):
            raise ValueError(f"{name} is still repeating at this level")
        return value

    return instantiate


def build_list_template(template):
    """Build a template that constructs lists.

    Typically, `build_template` should be used instead, which delegates to
    this function where appropriate.
    """

    class Special:
        ELLIPSIS = ...

    match template:
        case [*prefix, last] if last is not ... and ... in prefix:
            raise ValueError("Ellipsis can't be followed by non-ellipsis list elements")
        case [*items, Special.ELLIPSIS, Special.ELLIPSIS]:
            return build_flattened_list(items)
        case [*items, rep, Special.ELLIPSIS]:
            return build_actual_list_template(items, rep)
        case [*items]:
            return build_actual_list_template(items)


def build_flattened_list(items):
    """Build a template that flattens one level of nesting.

    Typically, `build_template` should be used instead, which delegates to
    this function where appropriate.
    """
    deep_template = build_list_template([[*items, ...], ...])

    def instantiate(bindings, nesting_level=()):
        return flatten(deep_template(bindings, nesting_level))

    return instantiate


def flatten(sequence):
    """Remove one level of nesting from a sequence of sequences
    by concatenating all inner sequences to one list."""
    result = []
    for s in sequence:
        result.extend(s)
    return result


def build_actual_list_template(items, rep=None):
    """Build a template that constructs lists.

    Typically, `build_template` should be used instead, which delegates to
    this function where appropriate.
    """
    fixed_instantiators = [build_template(t) for t in items]

    def instantiate(bindings, nesting_level=()):
        return [x(bindings, nesting_level) for x in fixed_instantiators]

    if rep is None:
        return instantiate

    names_in_rep = find_insertions(rep)
    rep_instantiator = build_template(rep)

    def instantiate_repeating(bindings, nesting_level=()):
        fixed_part = instantiate(bindings)

        rep_len = common_repetition_length(bindings, nesting_level, names_in_rep)
        variable_part = [
            rep_instantiator(bindings, nesting_level + (i,)) for i in range(rep_len)
        ]
        return fixed_part + variable_part

    return instantiate_repeating


def find_insertions(template):
    """find all names inserted in given template"""
    names = set()
    match template:
        case Insert(name):
            names.add(name)
        case list():
            for x in template:
                names |= find_insertions(x)
        case dict():
            for k, v in template.items():
                names |= find_insertions(k)
                names |= find_insertions(v)
    return names


def common_repetition_length(bindings, nesting_level, used_names):
    """Try to find a common length suitable for all used bindings at given nesting level."""
    length = None
    for name in used_names:
        value = get_nested(bindings[name], nesting_level)
        if isinstance(value, Repeating):
            multiplicity = len(value.values)
            if length is None:
                length = multiplicity
            else:
                if multiplicity != length:
                    raise ValueError(
                        f"{name}'s number of values {multiplicity} "
                        f"does not match other bindings of length {length}"
                    )
                assert length == multiplicity

    if length is None:
        raise ValueError("no repeated bindings")

    return length


def build_dict_template(template):
    """Build a template that constructs lists.

    Typically, `build_template` should be used instead, which delegates to
    this function where appropriate.
    """
    item_instantiators = {
        build_template(k): build_template(v) for k, v in template.items()
    }

    def instantiate(bindings, nesting_level=()):
        return {
            k(bindings, nesting_level): v(bindings, nesting_level)
            for k, v in item_instantiators.items()
        }

    return instantiate


def get_nested(value, nesting_level):
    """Get the value of nested repeated bindings."""
    while nesting_level != ():
        if not isinstance(value, Repeating):
            break
        value = value.values[nesting_level[0]]
        nesting_level = nesting_level[1:]
    return value
