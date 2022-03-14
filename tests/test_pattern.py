import pytest

from matcho.bindings import Repeating
from matcho.pattern import build_mismatch_skipper, MatchAny
from matcho import (
    bind,
    bind_as,
    build_matcher,
    default,
    skip_mismatch,
    skip_missing_keys,
    KeyMismatch,
    LiteralMismatch,
    LengthMismatch,
    Mismatch,
    TypeMismatch,
    Skip,
    CastMismatch,
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
        build_matcher([])([1])

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
    with pytest.raises(ValueError, match="[Ee]llipsis"):
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
    matcher = build_matcher(pattern)
    data = [{"x": 1}, {}, {"x": 2}]
    assert matcher(data) == {"x": Repeating([1, 2])}


def test_mismatch_skipper_replaces_exception_with_skip():
    with pytest.raises(Skip):
        build_mismatch_skipper(0, lambda _: True)(1)


def test_mismatch_skipper_passes_through_if_predicate_returns_false():
    with pytest.raises(LiteralMismatch):
        build_mismatch_skipper(0, lambda _: False)(1)


def test_mismatch_skipper_predicate_receives_mismatch_info():
    class MockPredicate:
        called_with = None

        def __call__(self, exception):
            self.exception = exception
            return False

    pred = MockPredicate()
    try:
        build_mismatch_skipper(0, pred)(1)
    except LiteralMismatch:
        pass
    assert isinstance(pred.exception, LiteralMismatch)
    assert pred.exception.args == (1, 0)


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


def test_dictionary_raises_mismatch_if_data_is_no_dict():
    with pytest.raises(TypeMismatch):
        build_matcher({})("not-a-dict")


def test_casting_binds():
    matcher = build_matcher(bind("x", dtype=int))
    assert matcher(42) == {"x": 42}
    assert matcher("42") == {"x": 42}

    with pytest.raises(CastMismatch):
        matcher("not-an-int")


def test_bind_as():
    matcher = build_matcher(bind_as("x", [...]))
    assert matcher([1, 2]) == {"x": [1, 2]}

    with pytest.raises(Mismatch):
        matcher("not-a-list")


def test_bind_as_with_default():
    matcher = build_matcher(bind_as("x", default_value="D", pattern=[...]))
    assert matcher([1, 2]) == {"x": [1, 2]}
    assert matcher("not-a-list") == {"x": "D"}


def test_match_type():
    matcher = build_matcher(int)
    assert matcher(42) == {}
    assert matcher("42") == {}

    with pytest.raises(CastMismatch):
        matcher("not-an-int")


def test_bound_names():
    assert build_matcher("literal").bound_names() == {}
    assert build_matcher(bind("x")).bound_names() == {"x": 0}
    assert build_matcher(bind_as("x", "literal")).bound_names() == {"x": 0}
    assert build_matcher(bind_as("x", bind("y"))).bound_names() == {"x": 0, "y": 0}
    assert build_matcher(skip_mismatch(bind("x"))).bound_names() == {"x": 0}
    assert build_matcher(skip_missing_keys([], bind("x"))).bound_names() == {"x": 0}
    assert build_matcher([bind("x")]).bound_names() == {"x": 0}
    assert build_matcher([bind("x"), ...]).bound_names() == {"x": 1}
    assert build_matcher([bind("x"), bind("y"), ...]).bound_names() == {"x": 0, "y": 1}
    assert build_matcher({"K": bind("x")}).bound_names() == {"x": 0}


def test_matcher_any_always_matches():
    matcher = MatchAny()
    assert matcher(None) == {}
    assert matcher(123) == {}
    assert matcher("abc") == {}
