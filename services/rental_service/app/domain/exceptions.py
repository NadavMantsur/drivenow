class DomainError(Exception):
    pass


class NotFoundError(DomainError):
    pass


class ConflictError(DomainError):
    pass


class FleetServiceError(DomainError):
    pass
