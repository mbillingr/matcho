[![Tests](https://github.com/mbillingr/matcho/actions/workflows/python-tests.yml/badge.svg)](https://github.com/mbillingr/matcho/actions/workflows/python-tests.yml)
[
    ![PyPI](https://img.shields.io/pypi/v/matcho?label=pypi%20version&logo=pypi)
    ![PyPI - Downloads](https://img.shields.io/pypi/dm/matcho?label=pypi%20downloads&logo=pypi)
](https://pypi.org/project/matcho/)


# Matcho
A pattern matching and template library.

- Extract and convert hierarchically structured data using declarative input patterns and output templates.

Matcho was originally written by a need to convert hierarchical
JSON data into flattish data frames. It may yet transcend this purpose.

## Installation

```
pip install matcho
```

## Quick Start

```python
from matcho import build_matcher, build_template, bind, insert

# match a list of any length and bind "x" to its items
matcher = build_matcher([bind("x"), ...])

# match some data
bindings = matcher([1, 2, 3])

# a template that reconstructs the original list
template = build_template([insert("x"), ...])

assert template(bindings) == [1, 2, 3]
```

## Motivating example
What if you want to convert data from a deeply nested structure like JSON
to a flat tabular format?

For example, say we want to extract the columns "date", "time", "station" and 
"event_type" from the following structure:
```python
data = {
    "date": "2022-02-20",
    "uid": "DEADBEEF",
    "reports": [
        {
            "station": 7,
            "events": [
                {"time": 1300, "type": "ON"},
                {"time": 1700, "type": "OFF"}
            ]
        },
        {
            "station": 5,
            "events": [
                {"time": 1100, "type": "ON"},
                {"time": 1800, "type": "OFF"}
            ]
        }
    ]
}
```

That's how Matcho does it:

```python
from matcho import build_matcher, build_template, bind, insert

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
        ...,  # note that the number of ... matches the pattern
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
```

## Inspiration
Matcho was inspired by Scheme's `syntax-rules` pattern language. Scheme is a 
Lisp dialect that allows programmers to define macros using pattern matching and
template substitution. Since code in Scheme consists of list this enables cool
syntax transformations. In Python we are limited to transforming data, but 
that's cool enough.

## Why not just use Python 3.10's `match` syntax instead?
The new `match` syntax is great and it's even used by the implementation of
Macho. However, it has one shortcoming: names can only capture one value. While
it's possible to match an arbitary number of list items with `[*items]`, it's
not possible to do something like `[*{"nested": item}]`, where we would like
to capture values in a sequence of dictionaries. In Matcho, this is  possible
with a pattern of the form `[{"nested": item}, ...]`.
