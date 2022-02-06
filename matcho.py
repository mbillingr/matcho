from dataclasses import dataclass
from functools import reduce
from operator import or_


__version__ = "0.0.0"


from typing import Any, Hashable


class Mismatch(Exception):
    pass


class KeyMismatch(Mismatch):
    pass


class LiteralMismatch(Mismatch):
    pass


class TypeMismatch(Mismatch):
    pass


class LengthMismatch(Mismatch):
    pass


class Skip(Exception):
    pass


def bind(name: str):
    return Bind(name)


@dataclass
class Bind:
    name: str


def default(key: Hashable, value: Any):
    return Default(key, value)


@dataclass
class Default:
    key: Hashable
    default_value: Any

    def __hash__(self):
        return hash(self.key)


def skip_mismatch(pattern: Any):
    return SkipOnMismatch(pattern)


@dataclass
class SkipOnMismatch:
    pattern: Any


def skip_missing_keys(keys: list, pattern: Any):
    return SkipMissingKeys(keys, pattern)


@dataclass
class SkipMissingKeys:
    keys: list
    pattern: Any


@dataclass
class Repeating:
    values: list


def build_matcher(pattern):
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
    def match_literal(data):
        if data == pattern:
            return {}
        raise LiteralMismatch(data, pattern)

    return match_literal


def build_binding_matcher(name):
    return lambda data: {name: data}


def build_instance_matcher(expected_type):
    def match_instance(data):
        if isinstance(data, expected_type):
            return {}
        raise TypeMismatch(data, expected_type)

    return match_instance


def build_list_matcher(pattern):
    class Special:
        ELLIPSIS = ...

    match pattern:
        case [Special.ELLIPSIS]:
            return build_instance_matcher(list)
        case [*prefix, Special.ELLIPSIS]:
            return build_repeating_list_matcher(prefix)
        case _:
            return build_fixed_list_matcher(pattern)


def build_fixed_list_matcher(pattern):
    matchers = [build_matcher(p) for p in pattern]

    def match_fixed_list(data):
        if not isinstance(data, list):
            raise TypeMismatch(data, list)

        if len(data) != len(matchers):
            raise LengthMismatch(len(data), len(matchers))

        return reduce(or_, map(apply_first, zip(matchers, data)), {})

    return match_fixed_list


def build_repeating_list_matcher(patterns):
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
    matchers = {k: build_matcher(v) for k, v in pattern.items()}

    def match_dict(data):
        bindings = {}
        for k, m in matchers.items():
            d = lookup(data, k)
            bindings |= m(d)
        return bindings

    return match_dict


def build_mismatch_skipper(pattern, mismatch_type, predicate=lambda _: True):
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
    f, *args = seq
    return f(*args)


def lookup(mapping, key):
    if isinstance(key, Default):
        return mapping.get(key.key, key.default_value)

    try:
        return mapping[key]
    except KeyError:
        pass

    raise KeyMismatch(mapping, key)


def insert(name):
    return Insert(name)


@dataclass
class Insert:
    name: str

    def __hash__(self):
        return hash(self.name)


def build_template(template):
    match template:
        case Insert(name):
            return build_insertion_template(name)
        case list(_):
            return build_list_template(template)
        case dict(_):
            return build_dict_template(template)
        case _:
            return lambda *_: template


def build_insertion_template(name):
    def instantiate(bindings, nesting_level=()):
        value = get_nested(bindings[name], nesting_level)
        if isinstance(value, Repeating):
            raise ValueError(f"{name} is still repeating at this level")
        return value

    return instantiate


def build_list_template(template):
    class Special:
        ELLIPSIS = ...

    match template:
        case [*items, Special.ELLIPSIS, Special.ELLIPSIS]:
            return build_flattened_list(items)
        case [*items, rep, Special.ELLIPSIS]:
            return build_actual_list_template(items, rep)
        case [*items]:
            return build_actual_list_template(items)


def build_flattened_list(items):
    deep_template = build_list_template([[*items, ...], ...])

    def instantiate(bindings, nesting_level=()):
        return flatten(deep_template(bindings, nesting_level))

    return instantiate


def flatten(sequence):
    result = []
    for s in sequence:
        result.extend(s)
    return result


def build_actual_list_template(items, rep=None):
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
    length = None
    for name in used_names:
        value = get_nested(bindings[name], nesting_level)
        if isinstance(value, Repeating):
            if length is None:
                length = len(value.values)
            else:
                assert length == len(value.values)

    return length


def build_dict_template(template):
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
    while nesting_level != ():
        if not isinstance(value, Repeating):
            break
        value = value.values[nesting_level[0]]
        nesting_level = nesting_level[1:]
    return value
