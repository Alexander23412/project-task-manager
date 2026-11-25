# ШІ: Claude sonnet 5.5 – Перевірка коду
from models.work_item import WorkItem
from models.enums import Status


PROGRESS_BY_STATUS = {
    Status.TODO: 0.0,
    Status.IN_PROGRESS: 0.5,
    Status.DONE: 1.0
}


class Task(WorkItem):

    def progress(self) -> float:
        return PROGRESS_BY_STATUS[self.status]