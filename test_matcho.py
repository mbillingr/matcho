import pytest

from matcho import (
    bind,
    build_matcher,
    build_mismatch_skipper,
    build_template,
    default,
    insert,
    skip_mismatch,
    skip_missing_keys,
    KeyMismatch,
    LiteralMismatch,
    LengthMismatch,
    Repeating,
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


def test_contrived_example():
    data = {
        "id": 42,
        "measurements": [
            {
                "timestamp": 1,
                "recordings": [{"mean": 3.0, "std": 1.4}, [1, 2, 3, 4, 5]],
            },
            {
                "timestamp": 2,
                "recordings": [
                    {"mean": 3.0, "std": 1.6},
                ],
            },
            {
                "timestamp": 3,
                "recordings": [
                    {"mean": 3.0, "std": 1.6},
                    [1, 3, 5],
                ],
            },
            {
                "timestamp": 4,
            },
        ],
    }

    pattern = {
        "id": bind("global_id"),
        "measurements": [
            skip_missing_keys(
                ["recordings"],
                {
                    "timestamp": bind("t"),
                    "recordings": skip_mismatch([{}, [bind("x"), ...]]),
                },
            ),
            ...,
        ],
    }

    matcher = build_matcher(pattern)
    bindings = matcher(data)

    assert bindings == {
        "global_id": 42,
        "t": Repeating([1, 3]),
        "x": Repeating([Repeating([1, 2, 3, 4, 5]), Repeating([1, 3, 5])]),
    }


def test_trivial_templates_without_binding():
    assert build_template(42)({}) == 42
    assert build_template([])({}) == []
    assert build_template([1, 2, 3])({}) == [1, 2, 3]
    assert build_template({"x": "y"})({}) == {"x": "y"}


def test_bindings_dont_have_to_be_used():
    assert build_template(42)({"x": 1}) == 42  # does not raise


def test_inserting_unbound_names_is_an_error():
    template = build_template(insert("x"))
    with pytest.raises(KeyError):
        template({})


def test_insert_name_from_binding():
    template = build_template(insert("x"))
    assert template({"x": 42}) == 42


def test_insert_name_from_binding_nested_in_list():
    template = build_template([[insert("x")]])
    assert template({"x": 42}) == [[42]]


def test_insert_name_from_binding_nested_in_dict_value():
    template = build_template({"out": insert("x")})
    assert template({"x": 42}) == {"out": 42}


def test_insert_name_from_binding_nested_in_dict_key():
    template = build_template({insert("key"): 0})
    assert template({"key": "x"}) == {"x": 0}


def test_cant_insert_repeating_binding_in_simple_context():
    template = build_template(insert("x"))
    with pytest.raises(ValueError):
        template({"x": Repeating([])})


def test_insert_repeating_element():
    template = build_template([insert("x"), ...])
    assert template({"x": Repeating([])}) == []
    assert template({"x": Repeating([1])}) == [1]
    assert template({"x": Repeating([1, 2, 3])}) == [1, 2, 3]


def test_insert_repeating_element_with_prefix():
    template = build_template(["foo", "bar", insert("x"), ...])
    assert template({"x": Repeating([])}) == ["foo", "bar"]
    assert template({"x": Repeating([1])}) == ["foo", "bar", 1]
    assert template({"x": Repeating([1, 2, 3])}) == ["foo", "bar", 1, 2, 3]


def test_insert_repeating_element_with_dicts():
    template = build_template({"result": [insert("x"), ...]})
    assert template({"x": Repeating([1])}) == {"result": [1]}

    template = build_template([{"r": insert("x")}, ...])
    assert template({"x": Repeating([1, 2])}) == [{"r": 1}, {"r": 2}]


def test_nested_repeating_elements():
    template = build_template([[0, insert("x")], ...])
    assert template({"x": Repeating([])}) == []
    assert template({"x": Repeating([1])}) == [[0, 1]]
    assert template({"x": Repeating([1, 2])}) == [[0, 1], [0, 2]]


def test_simple_broadcasting():
    template = build_template([[insert("x"), insert("y")], ...])
    assert template({"x": 0, "y": Repeating([])}) == []
    assert template({"x": 0, "y": Repeating([1])}) == [[0, 1]]
    assert template({"x": 0, "y": Repeating([1, 2])}) == [[0, 1], [0, 2]]


def test_multi_level_broadcasting():
    template = build_template([[[insert("x"), insert("y"), insert("z")], ...], ...])
    assert template({"x": 0, "y": Repeating([]), "z": Repeating([])}) == []
    assert template(
        {"x": 0, "y": Repeating([1]), "z": Repeating([Repeating([7])])}
    ) == [[[0, 1, 7]]]
    assert template(
        {
            "x": 0,
            "y": Repeating([1, 2]),
            "z": Repeating([Repeating([7]), Repeating([8, 9])]),
        }
    ) == [[[0, 1, 7]], [[0, 2, 8], [0, 2, 9]]]


def test_flat_broadcasting():
    template = build_template([[insert("x"), insert("y"), insert("z")], ..., ...])
    assert template({"x": 0, "y": Repeating([]), "z": Repeating([])}) == []
    assert template(
        {"x": 0, "y": Repeating([1]), "z": Repeating([Repeating([7])])}
    ) == [[0, 1, 7]]
    assert template(
        {
            "x": 0,
            "y": Repeating([1, 2]),
            "z": Repeating([Repeating([7]), Repeating([8, 9])]),
        }
    ) == [[0, 1, 7], [0, 2, 8], [0, 2, 9]]


def test_deep_flat_broadcasting():
    template = build_template([[insert("x"), insert("y"), insert("z")], ..., ..., ...])

    bindings = {
        "x": Repeating([1, 2]),
        "y": Repeating([Repeating([3, 4]), Repeating([5, 6])]),
        "z": Repeating(
            [
                Repeating([Repeating([7, 8]), Repeating([7, 8])]),
                Repeating([Repeating([9, 0]), Repeating([9, 0])]),
            ]
        ),
    }

    assert template(bindings) == [
        [1, 3, 7],
        [1, 3, 8],
        [1, 4, 7],
        [1, 4, 8],
        [2, 5, 9],
        [2, 5, 0],
        [2, 6, 9],
        [2, 6, 0],
    ]


def test_repeat_length_mismatch():
    template = build_template([[insert("x"), insert("y")], ...])
    bindings = {"x": Repeating([1, 2, 3]), "y": Repeating([1, 2])}
    with pytest.raises(ValueError):
        template(bindings)


def test_invalid_ellipsis_position_in_template():
    with pytest.raises(ValueError, match="ellipsis"):
        build_template([..., 0])

    with pytest.raises(ValueError, match="ellipsis"):
        build_template([..., 0, 1])

    with pytest.raises(ValueError, match="ellipsis"):
        build_template([0, 1, ..., 2, 3])
