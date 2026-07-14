class DomainError(Exception):
    """Base domain exception."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ForbiddenError(DomainError):
    """Caller is not allowed to perform this operation (e.g. in_use without internal token)."""


class InvalidStatusTransitionError(DomainError):
    pass
