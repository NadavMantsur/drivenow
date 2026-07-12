from abc import ABC, abstractmethod

from drivenow_shared.events import DomainEvent


class EventPublisher(ABC):
    """Port for domain events. Phase 1: no-op. Phase 2: RabbitMQ."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        raise NotImplementedError


class NoOpEventPublisher(EventPublisher):
    def publish(self, event: DomainEvent) -> None:
        return None
