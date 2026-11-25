# ШІ: Claude sonnet 5.5 – чернетка ProjectService, етапи 1–4 (учасники, проєкти, завдання, пошук, файли).
import logging
import threading

from datetime import date, datetime

from models.bug import Bug
from models.member import Member
from models.enums import Priority, Status
from models.milestone import Milestone
from models.project import Project
from models.task import Task
from repository.json_repository import JSONRepository
from repository.xml_report import XmlReportWriter


logger = logging.getLogger(__name__)


_PRIORITY_ORDER = {
    Priority.LOW: 0,
    Priority.MEDIUM: 1,
    Priority.HIGH: 2
}

_STATUS_ORDER = {
    Status.TODO: 0,
    Status.IN_PROGRESS: 1,
    Status.DONE: 2
}


def _is_empty(value):
    """None та порожній рядок означають «без фільтра»."""
    return value is None or (isinstance(value, str) and not value)


def _check_date(value, label):
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError(f"{label} має бути датою без часу.")


_SORT_KEYS = {
    "deadline": lambda item: item.deadline,
    "title": lambda item: item.title.casefold(),
    "priority": lambda item: _PRIORITY_ORDER[item.priority],
    "status": lambda item: _STATUS_ORDER[item.status]
}


class ProjectService:


    ITEM_TYPES = {
        "Task": Task,
        "Bug": Bug,
        "Milestone": Milestone
    }

    def __init__(self):

        self._lock = threading.RLock()
        self._members = []
        self._projects = []

    @property
    def members(self):
        with self._lock:
            return list(self._members)

    @property
    def projects(self):
        with self._lock:
            return list(self._projects)

    def _next_member_id(self):
        return max((m.id for m in self._members), default=0) + 1

    def _next_project_id(self):
        return max((p.id for p in self._projects), default=0) + 1

    def _next_item_id(self):

        return max(
            (item.id for p in self._projects for item in p.items),
            default=0
        ) + 1

    def _require_member(self, member, message="Учасника не знайдено."):

        if not any(existing is member for existing in self._members):
            raise ValueError(message)

    def _require_project(self, project):
        if not any(existing is project for existing in self._projects):
            raise ValueError("Проєкт не знайдено.")


    def add_member(self, name, role):
        with self._lock:
            member = Member(
                member_id=self._next_member_id(),
                name=name,
                role=role
            )
            self._members.append(member)
            logger.info(
                "Додано учасника №%s «%s» (%s)",
                member.id, member.name, member.role
            )
            return member

    def update_member(self, member, name=None, role=None):

        with self._lock:
            self._require_member(member)


            applied = []

            try:
                for attribute, value in (("name", name), ("role", role)):
                    if value is None:
                        continue

                    old_value = getattr(member, attribute)
                    setattr(member, attribute, value)
                    applied.append((attribute, old_value))

            except Exception:
                for attribute, old_value in reversed(applied):
                    setattr(member, attribute, old_value)
                raise

            if applied:
                logger.info(
                    "Змінено учасника №%s: %s",
                    member.id, ", ".join(field for field, _ in applied)
                )

    def count_member_items(self, member):
        with self._lock:
            return sum(
                1
                for project in self._projects
                for item in project.items
                if item.assignee.id == member.id
            )

    def delete_member(self, member):

        with self._lock:
            self._require_member(member)

            removed_count = self.count_member_items(member)

            for project in self._projects:
                project.remove_items_for_member(member)

            self._members.remove(member)
            logger.info(
                "Видалено учасника №%s «%s»; разом з ним видалено завдань: %s",
                member.id, member.name, removed_count
            )
            return removed_count

    def _is_project_name_taken(self, name, exclude=None):
        key = name.lower()
        return any(
            project.name.lower() == key
            for project in self._projects
            if project is not exclude
        )

    def add_project(self, name, start, end):
        with self._lock:

            project = Project(
                project_id=self._next_project_id(),
                name=name,
                start=start,
                end=end
            )

            if self._is_project_name_taken(project.name):
                raise ValueError(
                    f"Проєкт з назвою «{project.name}» уже існує."
                )

            self._projects.append(project)
            logger.info(
                "Додано проєкт №%s «%s» (%s — %s)",
                project.id, project.name, project.start, project.end
            )
            return project

    def update_project(self, project, name=None, start=None, end=None):

        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Назва проєкту має бути непорожнім рядком.")
            name = name.strip()

        if start is not None:
            _check_date(start, "Дата початку проєкту")

        if end is not None:
            _check_date(end, "Дата завершення проєкту")

        with self._lock:
            self._require_project(project)

            if name is not None and self._is_project_name_taken(
                name, exclude=project
            ):
                raise ValueError(f"Проєкт з назвою «{name}» уже існує.")


            if start is not None and end is not None and start > project.end:
                date_steps = [("end", end), ("start", start)]
            else:
                date_steps = [("start", start), ("end", end)]


            applied = []

            try:
                if name is not None:
                    old_value = project.name
                    project.name = name
                    applied.append(("name", old_value))

                for attribute, value in date_steps:
                    if value is None:
                        continue

                    old_value = getattr(project, attribute)
                    setattr(project, attribute, value)
                    applied.append((attribute, old_value))

            except Exception:

                for attribute, old_value in reversed(applied):
                    setattr(project, attribute, old_value)
                raise

            if applied:
                logger.info(
                    "Змінено проєкт №%s: %s",
                    project.id, ", ".join(field for field, _ in applied)
                )

    def delete_project(self, project):
        with self._lock:
            self._require_project(project)
            removed_items = len(project.items)
            self._projects.remove(project)
            logger.info(
                "Видалено проєкт №%s «%s» разом із завданнями: %s",
                project.id, project.name, removed_items
            )

    def add_item(self, project, item_type, title, assignee, priority,
                 status, deadline, estimate_hours):
        with self._lock:
            self._require_project(project)
            self._require_member(
                assignee, "Виконавця не знайдено серед учасників."
            )

            if (
                not isinstance(item_type, str)
                or item_type not in self.ITEM_TYPES
            ):
                raise ValueError(f"Невідомий тип завдання: {item_type!r}.")

            item = self.ITEM_TYPES[item_type](
                item_id=self._next_item_id(),
                title=title,
                assignee=assignee,
                priority=priority,
                status=status,
                deadline=deadline,
                estimate_hours=estimate_hours
            )

            project.add_item(item)
            logger.info(
                "Додано завдання №%s «%s» (%s) у проєкт №%s, виконавець №%s",
                item.id, item.title, item.item_type, project.id, assignee.id
            )
            return item

    def update_item(self, project, item, **changes):
        with self._lock:
            self._require_project(project)

            if "assignee" in changes:
                self._require_member(
                    changes["assignee"],
                    "Виконавця не знайдено серед учасників."
                )

            project.update_item(item, **changes)

            if changes:
                logger.info(
                    "Змінено завдання №%s у проєкті №%s: %s",
                    item.id, project.id, ", ".join(sorted(changes))
                )

    def delete_item(self, project, item):
        with self._lock:
            self._require_project(project)
            project.remove_item(item)
            logger.info(
                "Видалено завдання №%s «%s» з проєкту №%s",
                item.id, item.title, project.id
            )

    def snapshot_items(self):

        with self._lock:
            return [
                (project, item)
                for project in self._projects
                for item in project.items
            ]

    def find_items(self, project, text="", status=None, priority=None,
                   assignee=None, sort_by="deadline", descending=False):

        if not isinstance(sort_by, str) or sort_by not in _SORT_KEYS:
            raise ValueError(f"Невідоме поле сортування: {sort_by!r}.")

        with self._lock:
            self._require_project(project)

            items = project.items

        needle = (text or "").strip().casefold()

        result = [
            item for item in items
            if (not needle or needle in item.title.casefold())
            and (_is_empty(status) or item.status == status)
            and (_is_empty(priority) or item.priority == priority)
            and (_is_empty(assignee) or item.assignee.id == assignee.id)
        ]

        sort_key = _SORT_KEYS[sort_by]
        result.sort(
            key=lambda item: (sort_key(item), item.title.casefold(), item.id),
            reverse=descending
        )
        return result

    def load_file(self, path):

        members, projects = JSONRepository.load(path)

        with self._lock:
            self._members = members
            self._projects = projects

        logger.info(
            "Завантажено файл %s: учасників %s, проєктів %s, завдань %s",
            path, len(members), len(projects),
            sum(len(project.items) for project in projects)
        )

    def save_file(self, path):

        with self._lock:
            JSONRepository.save(path, list(self._members), list(self._projects))
            logger.info(
                "Збережено файл %s: учасників %s, проєктів %s, завдань %s",
                path, len(self._members), len(self._projects),
                sum(len(project.items) for project in self._projects)
            )

    def export_overdue_report(self, path, today):

        with self._lock:
            XmlReportWriter.write(path, list(self._projects), today)
            logger.info(
                "Записано XML-звіт %s на %s: прострочених завдань %s",
                path, today,
                sum(
                    1
                    for project in self._projects
                    for item in project.items
                    if item.is_overdue(today)
                )
            )