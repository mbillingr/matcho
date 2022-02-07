from dataclasses import dataclass

from matcho.bindings import Repeating

__all__ = ["build_template", "insert"]


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
    if isinstance(spec, Insert):
        return build_insertion_template(spec.name)
    elif isinstance(spec, list):
        return build_list_template(spec)
    elif isinstance(spec, dict):
        return build_dict_template(spec)
    else:
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
    if len(template) >= 2 and template[-1] is not ... and ... in template:
        raise ValueError("Ellipsis can't be followed by non-ellipsis list elements")
    elif template[-2:] == [..., ...]:
        return build_flattened_list(template[:-2])
    elif len(template) >= 2 and template[-1] is ...:
        return build_actual_list_template(template[:-2], template[-2])
    else:
        return build_actual_list_template(template)


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
    if isinstance(template, Insert):
        names.add(template.name)
    elif isinstance(template, list):
        for x in template:
            names |= find_insertions(x)
    elif isinstance(template, dict):
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
