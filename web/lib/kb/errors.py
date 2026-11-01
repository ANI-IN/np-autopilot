"""Typed failures. Each maps to one HTTP status and one MCP error shape.

The message is written for a person: it says what happened and what to do.
`details` carries the machine-readable half (the current record on a conflict,
the existing record on a duplicate).
"""
from __future__ import annotations


class KbError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details

    def payload(self) -> dict:
        out = {"error": self.code, "message": self.message}
        out.update(self.details)
        return out


class Invalid(KbError):
    status, code = 422, "validation_error"


class Forbidden(KbError):
    status, code = 403, "permission_denied"


class NotFound(KbError):
    status, code = 404, "not_found"


class Conflict(KbError):
    """Optimistic-lock failure. `current` is the record as it is now."""
    status, code = 409, "version_conflict"


class Duplicate(KbError):
    """A live record already holds this name/URL/edge. `existing` names it."""
    status, code = 409, "duplicate"


class NeedsApproval(KbError):
    """The change was recorded as a proposal, not executed."""
    status, code = 202, "approval_required"
