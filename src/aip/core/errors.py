"""Domain errors. The API layer maps them to HTTP status codes."""


class DomainError(Exception):
    """Base class for business-rule violations."""

    code = "domain_error"


class NotFound(DomainError):
    code = "not_found"


class ValidationFailed(DomainError):
    code = "validation_failed"


class UnderwritingReferral(DomainError):
    """The risk is outside automatic acceptance and needs an underwriter."""

    code = "underwriting_referral"


class InvalidTransition(DomainError):
    code = "invalid_transition"


class ForbiddenTransition(DomainError):
    """The transition exists, but this actor type may not perform it."""

    code = "forbidden_transition"
