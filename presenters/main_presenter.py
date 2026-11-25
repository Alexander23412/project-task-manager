# ШІ: Claude sonnet 5.5 – чернетка MainPresenter (презентер головного вікна без Tkinter).
# Змінено: class MainView
import logging
import re
from datetime import date, datetime
from typing import Protocol

from models.enums import Priority, Status
from repository.json_repository import DataFormatError
from services.background_tasks import DONE, ERROR, PROGRESS, RESULT


logger = logging.getLogger(__name__)


class MainView(Protocol):

    def show_projects(self, rows, selected_id):
        """rows: {"id", "name", "start", "end", "items", "progress"}."""

    def show_members(self, rows):
        """rows: {"id", "name", "role"}."""

    def show_items(self, rows):
        """rows: {"id", "title", "type", "assignee", "assignee_id",
        "priority", "status", "deadline", "estimate_hours", "overdue"}.
        priority і status це значення перелічень ("low", "todo", ...),
        локалізує їх вікно. assignee_id потрібен формі редагування, бо
        імена учасників можуть повторюватись."""

    def show_error(self, message):
        """Показує повідомлення про помилку."""

    def show_info(self, message):
        """Показує інформаційне повідомлення."""

    def confirm(self, message) -> bool:
        """Питання «так / ні»; True, якщо користувач погодився."""

    def set_busy(self, is_busy):
        """True: заблокувати кнопки редагування; False: розблокувати."""

    def show_progress(self, done, total):
        """total=None: невизначений режим Progressbar."""

    def stop_progress(self):
        """Зупиняє індикатор."""

    def show_workload(self, rows):
        """rows: {"member_id", "name", "hours"}, за спаданням годин."""

    def show_overdue(self, rows):
        """rows: {"project", "item_id", "title", "assignee", "deadline",
        "days_overdue"}."""

    def close(self):
        """Закриває вікно."""


class MainPresenter:


    SORT_FIELDS = ("deadline", "title", "priority", "status")

    def __init__(self, service, tasks, view, today_provider=date.today):
        self._service = service
        self._tasks = tasks
        self._view = view
        self._today = today_provider

        self._selected_project_id = None
        self._search_text = ""
        self._status_filter = None
        self._priority_filter = None
        self._assignee_id = None
        self._sort_by = "deadline"
        self._descending = False


        self._items_by_id = {}

        self._operations = {}

    @property
    def is_busy(self):
        return bool(self._operations)

    def start(self):
        self.refresh()

    def refresh(self):
        """Єдине місце, де вікно синхронізується з даними сервісу."""
        today = self._today()
        members = self._service.members
        projects = self._service.projects

        if not any(p.id == self._selected_project_id for p in projects):
            self._selected_project_id = None

        assignee = next(
            (m for m in members if m.id == self._assignee_id), None
        )
        if assignee is None:
            self._assignee_id = None

        project = next(
            (p for p in projects if p.id == self._selected_project_id), None
        )

        items = []
        if project is not None:
            items = self._service.find_items(
                project,
                text=self._search_text,
                status=self._status_filter,
                priority=self._priority_filter,
                assignee=assignee,
                sort_by=self._sort_by,
                descending=self._descending
            )

        self._items_by_id = {item.id: item for item in items}

        self._view.show_projects(
            [
                {
                    "id": p.id,
                    "name": p.name,
                    "start": p.start.isoformat(),
                    "end": p.end.isoformat(),
                    "items": len(p.items),
                    "progress": p.progress()
                }
                for p in projects
            ],
            self._selected_project_id
        )
        self._view.show_members([
            {"id": m.id, "name": m.name, "role": m.role} for m in members
        ])
        self._view.show_items([
            {
                "id": item.id,
                "title": item.title,
                "type": item.item_type,
                "assignee": item.assignee.name,
                "assignee_id": item.assignee.id,
                "priority": item.priority.value,
                "status": item.status.value,
                "deadline": item.deadline.isoformat(),
                "estimate_hours": item.estimate_hours,
                "overdue": item.is_overdue(today)
            }
            for item in items
        ])

    def select_project(self, project_id):
        def action():
            if project_id is None:
                self._selected_project_id = None
            else:
                self._selected_project_id = self._find_project(project_id).id

        return self._run(action)

    def set_filters(self, text="", status=None, priority=None,
                    assignee_id=None):
        def action():
            new_status = self._to_enum(Status, status, "Статус")
            new_priority = self._to_enum(Priority, priority, "Пріоритет")
            new_assignee = (
                None if self._is_empty(assignee_id)
                else self._find_member(assignee_id).id
            )

            self._search_text = text or ""
            self._status_filter = new_status
            self._priority_filter = new_priority
            self._assignee_id = new_assignee

        return self._run(action)

    def set_sort(self, sort_by, descending=False):
        def action():
            if sort_by not in self.SORT_FIELDS:
                raise ValueError(f"Невідоме поле сортування: {sort_by!r}.")

            self._sort_by = sort_by
            self._descending = bool(descending)

        return self._run(action)

    def add_member(self, name, role):
        if self._is_blocked():
            return False

        return self._run(lambda: self._service.add_member(name, role))

    def update_member(self, member_id, name, role):
        if self._is_blocked():
            return False

        return self._run(lambda: self._service.update_member(
            self._find_member(member_id), name=name, role=role
        ))

    def delete_member(self, member_id):
        if self._is_blocked():
            return False

        def action():
            member = self._find_member(member_id)
            count = self._service.count_member_items(member)

            if count:
                question = (
                    f"У учасника «{member.name}» {count} завдань, "
                    "вони теж будуть видалені. Продовжити?"
                )
            else:
                question = f"Видалити учасника «{member.name}»?"

            if not self._view.confirm(question):
                return False

            self._service.delete_member(member)

        return self._run(action)
    
    def add_project(self, name, start, end):
        if self._is_blocked():
            return False

        def action():
            project = self._service.add_project(
                name,
                self._parse_date(start, "Дата початку"),
                self._parse_date(end, "Дата завершення")
            )
            self._selected_project_id = project.id

        return self._run(action)

    def update_project(self, project_id, name, start, end):
        if self._is_blocked():
            return False

        return self._run(lambda: self._service.update_project(
            self._find_project(project_id),
            name=name,
            start=self._parse_date(start, "Дата початку"),
            end=self._parse_date(end, "Дата завершення")
        ))

    def delete_project(self, project_id):
        if self._is_blocked():
            return False

        def action():
            project = self._find_project(project_id)
            question = (
                f"Видалити проєкт «{project.name}» разом з усіма його "
                f"завданнями ({len(project.items)})?"
            )

            if not self._view.confirm(question):
                return False

            self._service.delete_project(project)

        return self._run(action)

    def add_item(self, item_type, title, assignee_id, priority, status,
                 deadline, estimate_hours):
        if self._is_blocked():
            return False

        def action():
            self._service.add_item(
                self._require_selected_project(),
                item_type,
                title,
                self._find_member(assignee_id),
                self._to_enum(Priority, priority, "Пріоритет", required=True),
                self._to_enum(Status, status, "Статус", required=True),
                self._parse_date(deadline, "Дедлайн"),
                self._parse_hours(estimate_hours)
            )

        return self._run(action)

    def update_item(self, item_id, title, assignee_id, priority, status,
                    deadline, estimate_hours):
        if self._is_blocked():
            return False

        def action():
            self._service.update_item(
                self._require_selected_project(),
                self._find_item(item_id),
                title=title,
                assignee=self._find_member(assignee_id),
                priority=self._to_enum(
                    Priority, priority, "Пріоритет", required=True
                ),
                status=self._to_enum(Status, status, "Статус", required=True),
                deadline=self._parse_date(deadline, "Дедлайн"),
                estimate_hours=self._parse_hours(estimate_hours)
            )

        return self._run(action)

    def delete_item(self, item_id):
        if self._is_blocked():
            return False

        def action():
            item = self._find_item(item_id)

            if not self._view.confirm(f"Видалити завдання «{item.title}»?"):
                return False

            self._service.delete_item(self._require_selected_project(), item)

        return self._run(action)

    def export_json(self, path):
        if self._is_blocked():
            return False

        def action():
            self._service.save_file(path)
            self._view.show_info(f"Дані збережено: {path}")

        return self._run(action)

    def export_xml_report(self, path):
        if self._is_blocked():
            return False

        def action():
            self._service.export_overdue_report(path, self._today())
            self._view.show_info(f"XML-звіт збережено: {path}")

        return self._run(action)

    def import_file(self, path, announce=True):

        return self._start_operation(
            "import" if announce else "startup_import",
            lambda: self._tasks.start_import(path)
        )

    def calculate_workload(self):
        return self._start_operation(
            "workload", self._tasks.start_workload
        )

    def find_overdue(self):
        return self._start_operation(
            "overdue", lambda: self._tasks.start_overdue(self._today())
        )

    def process_messages(self):

        try:
            messages = self._tasks.poll()
        except Exception:
            logger.exception("Не вдалося прочитати чергу повідомлень")
            return

        for message in messages:
            try:
                self._handle_message(message)
            except Exception:
                logger.exception("Помилка обробки повідомлення %s", message)
                self._safe_show_error("Помилка під час обробки результату.")

    def _handle_message(self, message):
        name = self._operations.get(message.operation_id)

        if name is None:
            return  

        if message.kind == PROGRESS:
            self._view.show_progress(
                message.data["done"], message.data["total"]
            )

        elif message.kind == RESULT:
            self._handle_result(name, message.data)

        elif message.kind == ERROR:
            self._view.show_error(str(message.data))

        elif message.kind == DONE:
            del self._operations[message.operation_id]

            if not self._operations:
                self._view.set_busy(False)
                self._view.stop_progress()

    def _handle_result(self, name, data):
        if name in ("import", "startup_import"):

            self._selected_project_id = None
            self.refresh()

            if name == "startup_import":
                return

            self._view.show_info(
                f"Імпортовано: учасників {data['members']}, "
                f"проєктів {data['projects']}."
            )

        elif name == "workload":
            names = {m.id: m.name for m in self._service.members}
            rows = [
                {
                    "member_id": member_id,
                    "name": names.get(member_id, f"#{member_id}"),
                    "hours": hours
                }
                for member_id, hours in data["workload"].items()
            ]
            rows.sort(key=lambda row: (-row["hours"], row["name"]))
            self._view.show_workload(rows)

        elif name == "overdue":
            found = {
                item.id: (project, item)
                for project, item in self._service.snapshot_items()
            }
            rows = []

            for entry in data["overdue"]:
                pair = found.get(entry["item_id"])

                if pair is None:
                    continue

                project, item = pair
                rows.append({
                    "project": project.name,
                    "item_id": item.id,
                    "title": item.title,
                    "assignee": item.assignee.name,
                    "deadline": item.deadline.isoformat(),
                    "days_overdue": entry["days_overdue"]
                })

            self._view.show_overdue(rows)

    def show_unexpected_error(self, error):

        self._safe_show_error(f"Неочікувана помилка: {error}")


    def on_close(self):
        if self.is_busy and not self._view.confirm(
            "Виконується фонова операція. Закрити програму?"
        ):
            return False

        self._tasks.shutdown()
        self._view.close()
        return True

    def _safe_show_error(self, message):
        try:
            self._view.show_error(message)
        except Exception:
            logger.exception("Не вдалося показати повідомлення про помилку")

    def _is_blocked(self):
        if self._operations:
            self._view.show_error("Зачекайте завершення поточної операції.")
            return True

        return False

    def _run(self, action):

        try:
            if action() is False:
                return False

        except (ValueError, DataFormatError) as error:
            self._view.show_error(str(error))
            return False

        except Exception as error:
            logger.exception("Неочікувана помилка")
            self._view.show_error(f"Неочікувана помилка: {error}")
            return False

        self.refresh()
        return True

    def _start_operation(self, name, starter):
        if self._is_blocked():
            return False

        try:
            operation_id = starter()
        except Exception as error:
            logger.exception("Не вдалося запустити операцію %s", name)
            self._view.show_error(f"Не вдалося запустити операцію: {error}")
            return False

        self._operations[operation_id] = name
        self._view.set_busy(True)
        self._view.show_progress(0, None)
        return True

    @staticmethod
    def _is_empty(value):
        return value is None or (isinstance(value, str) and not value)

    @staticmethod
    def _as_id(value):
        if isinstance(value, bool):
            raise ValueError("Некоректний ідентифікатор.")

        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError("Некоректний ідентифікатор.") from None

    def _find_member(self, member_id):
        if self._is_empty(member_id):
            raise ValueError("Виконавця не вибрано.")

        wanted = self._as_id(member_id)

        for member in self._service.members:
            if member.id == wanted:
                return member

        raise ValueError("Учасника не знайдено.")

    def _find_project(self, project_id):
        wanted = self._as_id(project_id)

        for project in self._service.projects:
            if project.id == wanted:
                return project

        raise ValueError("Проєкт не знайдено.")

    def _require_selected_project(self):
        if self._selected_project_id is None:
            raise ValueError("Спочатку виберіть проєкт.")

        return self._find_project(self._selected_project_id)

    def _find_item(self, item_id):
        item = self._items_by_id.get(self._as_id(item_id))

        if item is None:
            raise ValueError("Завдання не вибрано або воно вже не існує.")

        return item

    @staticmethod
    def _to_enum(enum_class, value, label, required=False):
        if value is None or value == "":
            if required:
                raise ValueError(f"{label} не вибрано.")
            return None

        if isinstance(value, enum_class):
            return value

        try:
            return enum_class(value)
        except ValueError:
            raise ValueError(f"Невідоме значення поля «{label}»: {value!r}.") from None

    @staticmethod
    def _parse_date(value, label):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value

        if isinstance(value, str):
            text = value.strip()

            if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
                try:
                    return date.fromisoformat(text)
                except ValueError:
                    pass

        raise ValueError(f"{label}: очікується коректна дата YYYY-MM-DD.")

    @staticmethod
    def _parse_hours(value):
        message = "Оцінка часу має бути додатним числом."

        if isinstance(value, bool):
            raise ValueError(message)

        if isinstance(value, (int, float)):
            return value

        if isinstance(value, str):
            try:
                number = float(value.strip().replace(",", "."))
            except ValueError:
                raise ValueError(message) from None

            return int(number) if number.is_integer() else number

        raise ValueError(message)