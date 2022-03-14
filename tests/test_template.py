import pytest

from matcho.bindings import Repeating
from matcho import build_template, insert


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
    template = build_template(
        [[insert("x"), insert("y"), insert("z")], ..., ..., ..., ...]
    )

    bindings = {
        "x": Repeating([1, 2]),
        "y": Repeating([Repeating([3]), Repeating([4])]),
        "z": Repeating(
            [
                Repeating(
                    [
                        Repeating([Repeating([5, 6]), Repeating([7, 8])]),
                    ]
                ),
                Repeating(
                    [
                        Repeating([Repeating([9, 0]), Repeating([9, 0])]),
                    ]
                ),
            ]
        ),
    }

    assert template(bindings) == [
        [1, 3, 5],
        [1, 3, 6],
        [1, 3, 7],
        [1, 3, 8],
        [2, 4, 9],
        [2, 4, 0],
        [2, 4, 9],
        [2, 4, 0],
    ]


def test_repeat_length_mismatch():
    template = build_template([[insert("x"), insert("y")], ...])
    bindings = {"x": Repeating([1, 2, 3]), "y": Repeating([1, 2])}
    with pytest.raises(ValueError):
        template(bindings)


def test_invalid_ellipsis_position_in_template():
    with pytest.raises(ValueError, match="[Ee]llipsis"):
        build_template([...])

    with pytest.raises(ValueError, match="[Ee]llipsis"):
        build_template([..., 0])

    with pytest.raises(ValueError, match="[Ee]llipsis"):
        build_template([..., 0, 1])

    with pytest.raises(ValueError, match="[Ee]llipsis"):
        build_template([0, 1, ..., 2, 3])
