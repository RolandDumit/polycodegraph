from abc import ABC, abstractmethod


class Repository(ABC):
    @abstractmethod
    def fetch(self) -> str:
        raise NotImplementedError


class MemoryRepository(Repository):
    def __init__(self, prefix: str = "user") -> None:
        self.prefix = prefix

    def fetch(self) -> str:
        return self.prefix

    @property
    def label(self) -> str:
        return self.prefix


class Unrelated:
    def fetch(self) -> str:
        return "decoy"
