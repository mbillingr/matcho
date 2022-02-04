from dataclasses import dataclass
from functools import reduce
from operator import or_


class Mismatch(Exception): pass
class LiteralMismatch(Mismatch): pass
class ExpectedListMismatch(Mismatch): pass
class LengthMismatch(Mismatch): pass


def bind(name: str):
    return Bind(name)


@dataclass
class Bind:
    name: str


def build_matcher(pattern):
    match pattern:
        case Bind(name): return build_binding_matcher(name)
        case [*_]: return build_list_matcher(pattern)
        case _: return build_literal_matcher(pattern)


def build_literal_matcher(pattern):
    def literal_matcher(data):
        if data == pattern:
            return {}
        raise LiteralMismatch(data, pattern)
    return literal_matcher


def build_binding_matcher(name):
    return lambda data: {name: data}


def build_list_matcher(pattern):
    class Special:
        ELLIPSIS = ...
    match pattern:
        case [*_, Special.ELLIPSIS]: raise NotImplementedError(...)
        case _: return build_fixed_list_matcher(pattern)


def build_fixed_list_matcher(pattern):
    matchers = [build_matcher(p) for p in pattern]

    def fixed_list_matcher(data):
        if not isinstance(data, list):
            raise ExpectedListMismatch(data)

        if len(data) != len(matchers):
            raise LengthMismatch(len(data), len(matchers))

        return reduce(or_, map(apply_first, zip(matchers, data)), {})

    return fixed_list_matcher


def apply_first(seq):
    f, *args = seq
    return f(*args)
