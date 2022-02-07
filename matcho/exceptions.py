class Mismatch(Exception):
    """The data does not match the pattern"""


class KeyMismatch(Mismatch):
    """The data does not contain a dictionary key required by the pattern."""


class LiteralMismatch(Mismatch):
    """The data is not equal to the pattern."""


class TypeMismatch(Mismatch):
    """The data has the wrong type."""


class CastMismatch(Mismatch):
    """The data can't be cast to the desired type."""


class LengthMismatch(Mismatch):
    """The data has the wrong length."""


class Skip(Exception):
    """If inside a variable sequence matcher, skip the current element."""
