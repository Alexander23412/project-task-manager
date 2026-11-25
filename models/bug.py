# ШІ: Claude sonnet 5.5 – Перевірка коду
from models.work_item import WorkItem
from models.enums import Status


class Bug(WorkItem):

    def progress(self) -> float:
        return float(self.status == Status.DONE)