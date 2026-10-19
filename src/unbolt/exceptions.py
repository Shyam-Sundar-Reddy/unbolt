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


class UnknownTargetError(UnboltError):
    """recommend_mappings() was asked for a target with no rule set."""


class InvalidChoiceError(UnboltError):
    """An override picked a type that wasn't among the field's candidates."""


class UnapprovedMappingError(UnboltError):
    """A field has no override and no valid candidate to default to."""
