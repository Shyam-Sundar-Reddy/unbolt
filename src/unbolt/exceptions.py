class UnboltError(Exception):
    """Base class for every error unbolt raises on purpose."""


class InvalidInputError(UnboltError):
    """The input copybook is empty, unreadable, or has an invalid setting."""


class InputTooLargeError(UnboltError):
    """The input copybook exceeds the configured size limit."""


class UnsupportedPictureError(UnboltError):
    """A field has no defined numeric range (it's a group or alphanumeric)."""


class SchemaVersionError(UnboltError):
    """A serialized DSL's version does not match what was expected."""
