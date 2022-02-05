import pytest

from matcho import (
    bind,
    build_matcher,
    default,
    skip_if_missing,
    KeyMismatch,
    LiteralMismatch,
    LengthMismatch,
    Repeating,
)


def test_match_literal():
    pattern = 123
    matcher = build_matcher(pattern)

    assert matcher(123) == {}

    with pytest.raises(LiteralMismatch):
        matcher(42)

    with pytest.raises(LiteralMismatch):
        matcher("")


def test_capture():
    pattern = bind("x")
    matcher = build_matcher(pattern)

    assert matcher(123) == {"x": 123}
    assert matcher("foo") == {"x": "foo"}


def test_simple_list_matching():
    assert build_matcher([])([]) == {}
    assert build_matcher([0])([0]) == {}
    assert build_matcher([1, 2, 3])([1, 2, 3]) == {}
    assert build_matcher([bind("x")])([0]) == {"x": 0}
    assert build_matcher([bind("x"), bind("y")])([1, 2]) == {"x": 1, "y": 2}

    with pytest.raises(LengthMismatch):
        build_matcher([bind("x"), bind("y")])([1])

    with pytest.raises(LengthMismatch):
        build_matcher([bind("x"), bind("y")])([1, 2, 3])


def test_repeating_list_matching():
    assert build_matcher([...])([]) == {}
    assert build_matcher([...])([1, 2, 3]) == {}
    assert build_matcher([1, ...])([1]) == {}
    assert build_matcher([1, ...])([1, 1, 1]) == {}

    with pytest.raises(LiteralMismatch):
        build_matcher([1, ...])([2])


def test_repeating_list_matching_with_binding():
    assert build_matcher([bind("x"), ...])([1]) == {"x": Repeating([1])}
    assert build_matcher([bind("x"), ...])([1, 2]) == {"x": Repeating([1, 2])}


def test_repeating_list_matching_with_multiple_bindings():
    assert build_matcher([[bind("x"), bind("y")], ...])([[1, 2], ["a", "b"]]) == {
        "x": Repeating([1, "a"]),
        "y": Repeating([2, "b"]),
    }


def test_repeating_list_matching_with_nested_bindings():
    assert build_matcher([[bind("x"), ...], ...])([[1, 2], [3]]) == {
        "x": Repeating([Repeating([1, 2]), Repeating([3])])
    }


def test_repeating_list_with_prefix():
    assert build_matcher([1, 2, 3, ...])([1, 2, 3]) == {}
    assert build_matcher([1, 2, 3, ...])([1, 2, 3, 3]) == {}
    assert build_matcher([1, 2, 3, ...])([1, 2, 3, 3, 3]) == {}

    with pytest.raises(LiteralMismatch):
        build_matcher([1, 2, 3, ...])([1, 2, 3, 4])

    with pytest.raises(LengthMismatch):
        build_matcher([1, 2, 3, ...])([1, 2])


def test_repeating_list_matching_with_prefix_and_binding():
    assert build_matcher([1, bind("x"), ...])([1, 2]) == {"x": Repeating([2])}
    assert build_matcher([1, bind("x"), ...])([1, 2, 3]) == {"x": Repeating([2, 3])}


def test_dictionary_matcher():
    assert build_matcher({})({}) == {}
    assert build_matcher({})({"x": 1}) == {}
    assert build_matcher({"x": 1})({"x": 1}) == {}
    assert build_matcher({1: 2})({1: 2}) == {}

    with pytest.raises(LiteralMismatch):
        build_matcher({"x": 1})({"x": 2})

    with pytest.raises(KeyMismatch):
        build_matcher({"x": 1})({})


def test_dictionary_matcher_with_bindings():
    assert build_matcher({})({}) == {}
    assert build_matcher({})({"x": 1}) == {}
    assert build_matcher({"x": bind("y")})({"x": 1}) == {"y": 1}


def test_binding_of_repetition_containing_dictionaries():
    assert build_matcher([{"x": bind("x")}, ...])([{"x": 1}, {"x": 2}]) == {
        "x": Repeating([1, 2])
    }


def test_missing_key_in_repeating_dictionary():
    with pytest.raises(KeyMismatch):
        build_matcher([{"x": bind("x")}, ...])([{"x": 1}, {}, {"x": 2}])


def test_key_with_defaults():
    assert build_matcher({default("x", 42): bind("y")})({}) == {"y": 42}


def test_skippable_key_failure():
    pattern = [skip_if_missing(["x"], {"x": bind("x")}), ...]
    data = [{"x": 1}, {}, {"x": 2}]
    assert build_matcher(pattern)(data) == {"x": Repeating([1, 2])}


# Matching Rules

## Literals
# Pattern | matches
#     42  | 42
#   "foo" | "foo"

## Capturing
# Pattern | matches
#     foo | ?

## Lists
# Pattern | matches
#      [] | []
#   [...] | [*]
# [0 ...] | [0 *]
# [x ...] | [? *]
# [1 x 2] | [1 ? 2]

## Dicts
#            Pattern | matches
#                 {} | any dictionary
#              {k:v} | any dictionary that contains key k whose value matches
# {default(k, d): v} | matches like {k:v} but if k not in dict, pretend its value is d


"""
data = {
    "x": 42,
    "more": [{"y": 1, "z": [1, 2]}, {"y": 2, "z": [1, 2]}, {"y": 3, "z": [0, 0]}],
}
pattern = {"x": bind("x"), "more": [{"y": bind("y"), "z": [bind("z"), ...]}, ...]}


VARIANT_A = {"x": 42, "y": [1, 2, 3], "z": [[1, 2], [1, 2], [0, 0]]}

VARIANT_B = (
    {"x: 42"},
    [
        ({"y": 1}, [({"z": 1},), ({"z": 2},)]),
        ({"y": 2}, [({"z": 1},), ({"z": 2},)]),
        ({"y": 3}, [({"z": 0},), ({"z": 0},)]),
    ],
)

#########################################################

data = [
    {"x": [1, 2], "y": 1, "z": [1, 2]},
    {"x": [3, 4], "y": 2, "z": [1, 2]},
    {"x": [5, 6], "y": 3, "z": [0, 0]},
]

pattern = [{"x": [bind("x"), ...], "y": bind("y"), "z": [bind("z"), ...]}, ...]


VARIANT_A = {
    "x": [[1, 2], [3, 4], [5, 6]],
    "y": [1, 2, 3],
    "z": [[1, 2], [1, 2], [0, 0]],
}

VARIANT_B = (
    {},
    [
        ({"y": 1}, [({"x": 1, "z": 1},), ({"x": 2, "z": 2},)]),
        ({"y": 2}, [({"x": 3, "z": 1},), ({"x": 4, "z": 2},)]),
        ({"y": 3}, [({"x": 5, "z": 0},), ({"x": 6, "z": 0},)]),
    ],
)

#########################################################

data = [
    {"x": [1, 2], "y": 1, "z": [1, 2]},
    {"x": [3], "y": 2, "z": [1, 2]},
    {"x": [], "y": 3, "z": [0, 0]},
]

pattern = [{"x": [bind("x"), ...], "y": bind("y"), "z": [bind("z"), ...]}, ...]


VARIANT_A = {
    "x": [[1, 2], [3], []],
    "y": [1, 2, 3],
    "z": [[1, 2], [1, 2], [0, 0]],
}

VARIANT_B = (
    {},
    [
        ({"y": 1}, [({"x": 1, "z": 1},), ({"x": 2, "z": 2},)]),
        ({"y": 2}, [({"x": 3, "z": 1},), ({"z": 2},)]),
        ({"y": 3}, [({"z": 0},), ({"z": 0},)]),
    ],
)
"""
