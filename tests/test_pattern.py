import pytest

from matcho.bindings import Repeating
from matcho.pattern import build_mismatch_skipper
from matcho import (
    bind,
    build_matcher,
    default,
    skip_mismatch,
    skip_missing_keys,
    KeyMismatch,
    LiteralMismatch,
    LengthMismatch,
    TypeMismatch,
    Skip,
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

    with pytest.raises(TypeMismatch):
        build_matcher([])("not-a-list")


def test_repeating_list_matching():
    assert build_matcher([...])([]) == {}
    assert build_matcher([...])([1, 2, 3]) == {}
    assert build_matcher([1, ...])([1]) == {}
    assert build_matcher([1, ...])([1, 1, 1]) == {}

    with pytest.raises(LiteralMismatch):
        build_matcher([1, ...])([2])

    with pytest.raises(TypeMismatch):
        build_matcher([...])("not-a-list")

    with pytest.raises(TypeMismatch):
        build_matcher([1, ...])("not-a-list")


def test_list_with_ellipsis_matches_zero_or_more():
    assert build_matcher([bind("x"), ...])([]) == {"x": Repeating([])}
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
    assert build_matcher([1, 2, 3, ...])([1, 2]) == {}
    assert build_matcher([1, 2, 3, ...])([1, 2, 3]) == {}
    assert build_matcher([1, 2, 3, ...])([1, 2, 3, 3]) == {}
    assert build_matcher([1, 2, 3, ...])([1, 2, 3, 3, 3]) == {}

    with pytest.raises(LiteralMismatch):
        build_matcher([1, 2, 3, ...])([1, 2, 3, 4])


def test_repeating_list_matching_with_prefix_and_binding():
    assert build_matcher([1, bind("x"), ...])([1, 2]) == {"x": Repeating([2])}
    assert build_matcher([1, bind("x"), ...])([1, 2, 3]) == {"x": Repeating([2, 3])}


def test_invalid_ellipsis_position_in_matcher():
    with pytest.raises(ValueError, match="ellipsis"):
        build_matcher([0, 1, ..., 2, 3])


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
    pattern = [skip_missing_keys(["x"], {"x": bind("x")}), ...]
    data = [{"x": 1}, {}, {"x": 2}]
    assert build_matcher(pattern)(data) == {"x": Repeating([1, 2])}


def test_mismatch_skipper_replaces_selected_exception_with_skip():
    with pytest.raises(Skip):
        build_mismatch_skipper(0, LiteralMismatch)(1)


def test_mismatch_skipper_passes_through_other_exceptions():
    with pytest.raises(LiteralMismatch):
        build_mismatch_skipper(0, LengthMismatch)(1)


def test_mismatch_skipper_passes_through_if_predicate_returns_false():
    with pytest.raises(LiteralMismatch):
        build_mismatch_skipper(0, LiteralMismatch, lambda _: False)(1)


def test_mismatch_skipper_predicate_recieves_expectation():
    class MockPredicate:
        called_with = None

        def __call__(self, *args):
            self.called_with = args
            return False

    pred = MockPredicate()
    try:
        build_mismatch_skipper(0, LiteralMismatch, pred)(1)
    except LiteralMismatch:
        pass
    assert pred.called_with == (0,)


def test_skippable_list_item():
    pattern = [skip_mismatch([1, bind("x")]), ...]
    data = [[1, 2], [1], [1, 3]]
    assert build_matcher(pattern)(data) == {"x": Repeating([2, 3])}


def test_skip_fields_together():
    pattern = [skip_missing_keys(["x", "y"], {"x": bind("x"), "y": bind("y")}), ...]
    data = [{"x": 1, "y": 10}, {"x": 2}, {"y": 30}, {"x": 4, "y": 40}]
    assert build_matcher(pattern)(data) == {
        "x": Repeating([1, 4]),
        "y": Repeating([10, 40]),
    }


def test_zero_length_in_parallel_nesting():
    pattern = [{"x": bind("x"), "Y": [bind("y"), ...]}, ...]
    data = [{"x": 1, "Y": [10]}, {"x": 2, "Y": []}]
    matcher = build_matcher(pattern)
    assert matcher(data) == {
        "x": Repeating([1, 2]),
        "y": Repeating([Repeating([10]), Repeating([])]),
    }
