# ШІ: Claude sonnet 5.5 – Перевірка коду
from datetime import date, datetime

from models.work_item import WorkItem
from models.member import Member


class Project:

    _EDITABLE_FIELDS = {
        "title",
        "assignee",
        "priority",
        "status",
        "deadline",
        "estimate_hours"
    }

    def __init__(self, project_id, name, start, end):
        if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
            raise ValueError("ID проєкту має бути додатним цілим числом.")

        self._id = project_id
        self._items = []

        self._validate_date(start, "Дата початку проєкту")
        self._validate_date(end, "Дата завершення проєкту")

        if start > end:
            raise ValueError("Дата початку проєкту не може бути пізніше дати завершення.")

        self._start = start
        self._end = end
        self._name = None
        self.name = name

    @staticmethod
    def _validate_date(value, field_name):
        if isinstance(value, datetime) or not isinstance(value, date):
            raise ValueError(f"{field_name} має бути датою без часу.")

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Назва проєкту має бути непорожнім рядком.")
        self._name = value.strip()

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        self._validate_date(value, "Дата початку проєкту")

        if value > self._end:
            raise ValueError("Дата початку не може бути пізніше дати завершення.")

        if any(item.deadline < value for item in self._items):
            raise ValueError("Нова дата початку виходить за межі дедлайнів завдань.")

        self._start = value

    @property
    def end(self):
        return self._end

    @end.setter
    def end(self, value):
        self._validate_date(value, "Дата завершення проєкту")

        if value < self._start:
            raise ValueError("Дата завершення не може бути раніше дати початку.")

        if any(item.deadline > value for item in self._items):
            raise ValueError("Нова дата завершення виходить за межі дедлайнів завдань.")

        self._end = value

    @property
    def items(self):
        return self._items.copy()

    def add_item(self, item):
        if not isinstance(item, WorkItem):
            raise ValueError("Елемент має бути об'єктом WorkItem.")

        if any(existing is item for existing in self._items):
            raise ValueError("Це завдання вже додано до проєкту.")

        if not self.start <= item.deadline <= self.end:
            raise ValueError("Дедлайн завдання має бути в межах проєкту.")

        if any(existing.id == item.id for existing in self._items):
            raise ValueError("Завдання з таким ID вже існує в проєкті.")

        if any(
            existing.title.casefold() == item.title.casefold()
            for existing in self._items
        ):
            raise ValueError("Назва завдання має бути унікальною в проєкті.")

        self._items.append(item)

    def remove_item(self, item):
        item_index = next(
            (index for index, existing in enumerate(self._items) if existing is item),
            None
        )

        if item_index is None:
            raise ValueError("Завдання не знайдено в проєкті.")

        del self._items[item_index]

    def update_item(self, item, **changes):
        if not any(existing is item for existing in self._items):
            raise ValueError("Завдання не належить цьому проєкту.")

        if not changes:
            return

        unknown_fields = set(changes) - self._EDITABLE_FIELDS

        if unknown_fields:
            raise ValueError(
                f"Невідомі поля для редагування: {sorted(unknown_fields)}"
            )

        if "deadline" in changes:
            new_deadline = changes["deadline"]
            self._validate_date(new_deadline, "Дедлайн завдання")

            if not self.start <= new_deadline <= self.end:
                raise ValueError("Дедлайн завдання має бути в межах проєкту.")

        if "title" in changes:
            new_title = changes["title"]

            if not isinstance(new_title, str) or not new_title.strip():
                raise ValueError("Назва завдання має бути непорожнім рядком.")

            normalized_title = new_title.strip().casefold()

            if any(
                existing is not item
                and existing.title.casefold() == normalized_title
                for existing in self._items
            ):
                raise ValueError("Назва завдання має бути унікальною в проєкті.")

        old_values = {
            field: getattr(item, field)
            for field in changes
        }

        try:
            for field, value in changes.items():
                setattr(item, field, value)

        except Exception:
            for field, value in old_values.items():
                setattr(item, field, value)

            raise

    def progress(self) -> float:
        if not self._items:
            return 0.0

        return sum(item.progress() for item in self._items) / len(self._items)

    def count_items_for_member(self, member: Member) -> int:
        return sum(
            item.assignee.id == member.id
            for item in self._items
        )

    def remove_items_for_member(self, member: Member) -> int:
        before = len(self._items)

        self._items = [
            item for item in self._items
            if item.assignee.id != member.id
        ]

        return before - len(self._items)

    def overdue_items(self, today: date) -> list:
        return [
            item for item in self._items
            if item.is_overdue(today)
        ]