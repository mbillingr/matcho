from dataclasses import dataclass
from functools import reduce
from operator import or_


class Mismatch(Exception):
    pass


class KeyMismatch(Mismatch):
    pass


class LiteralMismatch(Mismatch):
    pass


class TypeMismatch(Mismatch):
    pass


class ExpectedListMismatch(Mismatch):
    pass


class LengthMismatch(Mismatch):
    pass


def bind(name: str):
    return Bind(name)


@dataclass
class Bind:
    name: str


@dataclass
class Repeating:
    values: list


def build_matcher(pattern):
    match pattern:
        case Bind(name):
            return build_binding_matcher(name)
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
            raise ExpectedListMismatch(data)

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
            raise ExpectedListMismatch(data)

        if len(data) <= n_prefix:
            raise LengthMismatch(len(data), n_prefix + 1)

        bindings = reduce(
            or_, map(apply_first, zip(prefix_matchers[:n_prefix], data[:n_prefix])), {}
        )

        for d in data[n_prefix:]:
            bnd = repeating_matcher(d)

            for k, v in bnd.items():
                bindings.setdefault(k, Repeating([])).values.append(v)

        return bindings

    return match_repeating


def build_dict_matcher(pattern):
    matchers = {k: build_matcher(v) for k, v in pattern.items()}

    def match_dict(data):
        bindings = {}
        for k, m in matchers.items():
            if k not in data:
                raise KeyMismatch(data, k)
            bindings |= m(data[k])
        return bindings

    return match_dict


def apply_first(seq):
    f, *args = seq
    return f(*args)
