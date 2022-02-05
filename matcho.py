from dataclasses import dataclass
from functools import reduce
from operator import or_


class Mismatch(Exception):
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
        case _:
            return build_literal_matcher(pattern)


def build_literal_matcher(pattern):
    def literal_matcher(data):
        if data == pattern:
            return {}
        raise LiteralMismatch(data, pattern)

    return literal_matcher


def build_binding_matcher(name):
    return lambda data: {name: data}


def build_instance_matcher(expected_type):
    def instance_matcher(data):
        if isinstance(data, expected_type):
            return {}
        raise TypeMismatch(data, expected_type)

    return instance_matcher


def build_list_matcher(pattern):
    class Special:
        ELLIPSIS = ...

    match pattern:
        case [Special.ELLIPSIS]:
            return build_instance_matcher(list)
        case [item, Special.ELLIPSIS]:
            return build_repeating_list_matcher(item)
        case [*_, Special.ELLIPSIS]:
            raise NotImplementedError()
        case _:
            return build_fixed_list_matcher(pattern)


def build_fixed_list_matcher(pattern):
    matchers = [build_matcher(p) for p in pattern]

    def fixed_list_matcher(data):
        if not isinstance(data, list):
            raise ExpectedListMismatch(data)

        if len(data) != len(matchers):
            raise LengthMismatch(len(data), len(matchers))

        return reduce(or_, map(apply_first, zip(matchers, data)), {})

    return fixed_list_matcher


def build_repeating_list_matcher(pattern):
    item_matcher = build_matcher(pattern)

    def repeating_matcher(data):
        if not isinstance(data, list):
            raise ExpectedListMismatch(data)

        bindings = {}

        for d in data:
            bnd = item_matcher(d)

            for k, v in bnd.items():
                bindings.setdefault(k, Repeating([])).values.append(v)

        return bindings

    return repeating_matcher


def apply_first(seq):
    f, *args = seq
    return f(*args)
