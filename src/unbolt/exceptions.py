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


class RecordLengthMismatchError(UnboltError):
    """A record's byte length doesn't match its layout (decision 0010:
    reject by default, never a silent best-effort decode)."""


class InvalidSignNibbleError(UnboltError):
    """A signed DISPLAY field's overpunched last byte has a zone nibble
    that isn't a recognized sign (C/D) or unsigned zone (F), or a
    non-digit byte appears where a digit was expected."""


class UnsupportedDecodeError(UnboltError):
    """The field or clause combination isn't decodable yet (COMP-1/
    COMP-2 - no safe default, goal.md §5.4; alphanumeric/edited/
    national fields; OCCURS tables - later Phase 8 slices)."""


class RdwHeaderError(UnboltError):
    """An RDW (Record Descriptor Word) header is malformed: shorter
    than 4 bytes, declares a length under 4 or past the end of the
    buffer, or its reserved bytes are non-zero (a spanned-record
    segment descriptor - spanned records aren't supported)."""
