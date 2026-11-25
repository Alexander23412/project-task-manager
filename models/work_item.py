# ШІ: Claude sonnet 5.5 – Перевірка коду
from datetime import date, datetime
import math

from models.trackable import Trackable
from models.member import Member
from models.enums import Status, Priority


class WorkItem(Trackable):

    def __init__(self, item_id, title, assignee, priority, status, deadline, estimate_hours):
        if not isinstance(item_id, int) or isinstance(item_id, bool) or item_id <= 0:
            raise ValueError("ID завдання має бути додатним цілим числом.")

        self._id = item_id
        self.title = title
        self.assignee = assignee
        self.priority = priority
        self.status = status
        self.deadline = deadline
        self.estimate_hours = estimate_hours

    @property
    def id(self):
        return self._id

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Назва завдання має бути непорожнім рядком.")
        self._title = value.strip()

    @property
    def assignee(self):
        return self._assignee

    @assignee.setter
    def assignee(self, value):
        if not isinstance(value, Member):
            raise ValueError("Виконавець має бути об'єктом Member.")
        self._assignee = value

    @property
    def priority(self):
        return self._priority

    @priority.setter
    def priority(self, value):
        if not isinstance(value, Priority):
            raise ValueError("Пріоритет має бути елементом Priority.")
        self._priority = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        if not isinstance(value, Status):
            raise ValueError("Статус має бути елементом Status.")
        self._status = value

    @property
    def deadline(self):
        return self._deadline

    @deadline.setter
    def deadline(self, value):
        if isinstance(value, datetime) or not isinstance(value, date):
            raise ValueError("Кінцевий термін має бути датою без часу.")
        self._deadline = value

    @property
    def estimate_hours(self):
        return self._estimate_hours

    @estimate_hours.setter
    def estimate_hours(self, value):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not value > 0
            or (isinstance(value, float) and not math.isfinite(value))
        ):
            raise ValueError("Оцінка часу має бути додатним скінченним числом.")

        self._estimate_hours = value

    @property
    def item_type(self):
        return type(self).__name__

    def is_overdue(self, today: date) -> bool:
        return self.deadline < today and self.status != Status.DONE