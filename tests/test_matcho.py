from matcho.bindings import Repeating
from matcho import (
    bind,
    build_matcher,
    build_template,
    insert,
    skip_mismatch,
    skip_missing_keys,
)


def test_readme():
    matcher = build_matcher([bind("x"), ...])
    bindings = matcher([1, 2, 3])
    template = build_template([insert("x"), ...])
    assert template(bindings) == [1, 2, 3]

    data = {
        "date": "2022-02-20",
        "uid": "DEADBEEF",
        "reports": [
            {
                "station": 7,
                "events": [{"time": 1300, "type": "ON"}, {"time": 1700, "type": "OFF"}],
            },
            {
                "station": 5,
                "events": [{"time": 1100, "type": "ON"}, {"time": 1800, "type": "OFF"}],
            },
        ],
    }

    pattern = {
        "date": bind("date"),
        "reports": [
            {
                "station": bind("station"),
                "events": [{"time": bind("time"), "type": bind("event_type")}, ...],
            },
            ...,  # note that the ... really are Python syntax
        ],
    }

    template_spec = [
        [insert("date"), insert("time"), insert("station"), insert("event_type")],
        ...,
        ...,
    ]

    matcher = build_matcher(pattern)
    bindings = matcher(data)

    template = build_template(template_spec)
    table = template(bindings)

    assert table == [
        ["2022-02-20", 1300, 7, "ON"],
        ["2022-02-20", 1700, 7, "OFF"],
        ["2022-02-20", 1100, 5, "ON"],
        ["2022-02-20", 1800, 5, "OFF"],
    ]


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
