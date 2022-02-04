import pytest

from matcho import bind, build_matcher, LiteralMismatch, LengthMismatch


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


def test_variable_length_list_matching():
    assert build_matcher([...])([]) == {}
    assert build_matcher([...])([1, 2, 3]) == {}


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
