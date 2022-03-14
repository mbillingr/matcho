from dataclasses import dataclass
from functools import reduce, singledispatch
from operator import or_
from typing import Any, Set

from matcho.bindings import Repeating

__all__ = ["build_template", "insert"]


def insert(name: str):
    """Mark a place in the template where to insert the value bound to name."""
    return Insert(name)


@dataclass
class Insert:
    name: str

    def __hash__(self):
        return hash(self.name)


class Template:
    def instantiate(self, bindings, nesting_level):
        """Instantiate this template in the condext of some bindings and nesting level"""
        raise NotImplementedError(f"{self.__class__.__name__}.instantiate()")

    def insertions(self) -> Set[str]:
        raise NotImplementedError(f"{self.__class__.__name__}.insertions()")

    def __call__(self, bindings, nesting_level=()):
        return self.instantiate(bindings, nesting_level)


@dataclass
class LiteralTemplate(Template):
    value: Any

    def instantiate(self, bindings, nesting_level):
        return self.value

    def insertions(self) -> Set[str]:
        return set()

    def __hash__(self):
        return hash(self.value)


@singledispatch
def build_template(spec) -> Template:
    """Build a template from a specification.

    The resulting template is an object that when called with a set of
    bindings (as produced by a matcher from `build_matcher`), returns
    an instance of the template with names substituted by their bound values.

    This is a generic function. Support for additional template specifications
    can be added with the `build_template.register(<type>, <handler>)` function.
    See the documentation of `functools.singledispatch` for further information.
    """
    return LiteralTemplate(spec)


@build_template.register(Insert)
def _(insert_spec):
    return InsertionTemplate(insert_spec.name)


@dataclass
class InsertionTemplate(Template):
    """Template that is substituted with values bound to name."""

    name: str

    def instantiate(self, bindings, nesting_level):
        value = get_nested(bindings[self.name], nesting_level)
        if isinstance(value, Repeating):
            raise ValueError(f"{self.name} is still repeating at this level")
        return value

    def insertions(self) -> Set[str]:
        return {self.name}

    def __hash__(self):
        return hash(self.name)


@build_template.register(list)
def build_list_template(template):
    """Build a template that constructs lists.

    Typically, `build_template` should be used instead, which delegates to
    this function where appropriate.
    """
    if len(template) > 0 and template[0] is ...:
        raise ValueError("Ellipsis must be preceded by another list element")

    for a, b in zip(template, template[1:]):
        if a is ... and b is not ...:
            raise ValueError("Ellipsis can't be followed by non-ellipsis list elements")

    if len(template) > 2 and template[-2:] == [..., ...]:
        items = template[:-2]
        return FlattenListTemplate(items)

    if len(template) > 1 and template[-1] is ...:
        items1 = template[:-2]
        rep = template[-2]
        return VariableListTemplate(items1, rep)

    return FixedListTemplate(template)


class FlattenListTemplate(Template):
    """Template that flattens one level of nesting."""

    def __init__(self, items):
        self.deep_template = build_list_template([[*items, ...], ...])

    def instantiate(self, bindings, nesting_level):
        return flatten(self.deep_template(bindings, nesting_level))

    def insertions(self) -> Set[str]:
        return self.deep_template.insertions()


def flatten(sequence):
    """Remove one level of nesting from a sequence of sequences
    by concatenating all inner sequences to one list."""
    result = []
    for s in sequence:
        result.extend(s)
    return result


class FixedListTemplate(Template):
    """Template for lists of fixed length."""

    def __init__(self, list_template):
        self.templates = [build_template(t) for t in list_template]

    def instantiate(self, bindings, nesting_level):
        return [x(bindings, nesting_level) for x in self.templates]

    def insertions(self) -> Set[str]:
        return reduce(or_, (t.insertions() for t in self.templates), set())


class VariableListTemplate(Template):
    """Template for lists of variable length."""

    def __init__(self, items, rep):
        self.fixed_template = FixedListTemplate(items)
        self.repeated_template = build_template(rep)
        self.names_in_rep = self.repeated_template.insertions()

    def instantiate(self, bindings, nesting_level):
        fixed_part = self.fixed_template.instantiate(bindings, nesting_level)

        rep_len = common_repetition_length(bindings, nesting_level, self.names_in_rep)
        variable_part = [
            self.repeated_template.instantiate(bindings, nesting_level + (i,))
            for i in range(rep_len)
        ]
        return fixed_part + variable_part

    def insertions(self) -> Set[str]:
        return self.fixed_template.insertions() | self.repeated_template.insertions()


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


@build_template.register(dict)
class DictTemplate(Template):
    """Template for dictionaries"""

    def __init__(self, dict_spec):
        self.item_templates = {
            build_template(k): build_template(v) for k, v in dict_spec.items()
        }

    def instantiate(self, bindings, nesting_level):
        return {
            k(bindings, nesting_level): v(bindings, nesting_level)
            for k, v in self.item_templates.items()
        }

    def insertions(self) -> Set[str]:
        names = set()
        for k, v in self.item_templates.items():
            names |= k.insertions()
            names |= v.insertions()
        return names


def get_nested(value, nesting_level):
    """Get the value of nested repeated bindings."""
    while nesting_level != ():
        if not isinstance(value, Repeating):
            break
        value = value.values[nesting_level[0]]
        nesting_level = nesting_level[1:]
    return value
