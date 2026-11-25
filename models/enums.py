# ШІ: Claude sonnet 5.5 – Перевірка коду
from enum import Enum


class Status(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"

    @property
    def label(self):
        labels = {
            Status.TODO: "Не виконано",
            Status.IN_PROGRESS: "У роботі",
            Status.DONE: "Виконано"
        }
        return labels[self]


class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def label(self):
        labels = {
            Priority.LOW: "Низький",
            Priority.MEDIUM: "Середній",
            Priority.HIGH: "Високий"
        }
        return labels[self]