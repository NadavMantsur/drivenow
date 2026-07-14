class DomainError(Exception):
    """Base domain exception."""


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class InvalidStatusTransitionError(DomainError):
    pass
