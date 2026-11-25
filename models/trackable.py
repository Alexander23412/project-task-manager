# ШІ: Claude sonnet 5.5 – Перевірка коду
from abc import ABC, abstractmethod
from datetime import date


class Trackable(ABC):

    @abstractmethod
    def progress(self) -> float:
        pass

    @abstractmethod
    def is_overdue(self, today: date) -> bool:
        pass