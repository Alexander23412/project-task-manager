# ШІ: Claude sonnet 5.5 – Перевірка коду
import json
import logging
import os
import re
import tempfile

from datetime import date
from pathlib import Path

from models.member import Member
from models.project import Project
from models.task import Task
from models.bug import Bug
from models.milestone import Milestone
from models.enums import Status, Priority


logger = logging.getLogger(__name__)


class DataFormatError(Exception):
    """Виняток для помилок читання, перевірки та запису даних."""


class JSONRepository:
    """Репозиторій для завантаження та збереження даних у форматі JSON."""

    ITEM_TYPES = {
        "Task": Task,
        "Bug": Bug,
        "Milestone": Milestone
    }

    @staticmethod
    def _check_fields(data, required_fields):
        missing_fields = sorted(set(required_fields) - set(data))

        if missing_fields:
            raise DataFormatError(
                f"Відсутні обов'язкові поля: {', '.join(missing_fields)}."
            )

    @staticmethod
    def _require_dict(value, description):
        if not isinstance(value, dict):
            raise DataFormatError(
                f"{description} має бути JSON-об’єктом."
            )

    @staticmethod
    def _require_list(value, description):
        if not isinstance(value, list):
            raise DataFormatError(
                f"{description} має бути списком."
            )

    @staticmethod
    def _parse_date(value, field_name):
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            raise DataFormatError(
                f"Некоректний формат дати у полі «{field_name}». "
                "Очікується YYYY-MM-DD."
            )

        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise DataFormatError(
                f"Некоректна дата у полі «{field_name}»: {value}."
            ) from error

    @staticmethod
    def load(path):

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

        except (OSError, json.JSONDecodeError) as error:
            message = f"Не вдалося прочитати JSON-файл «{path}»: {error}"
            logger.error(message)
            raise DataFormatError(message) from error

        try:
            JSONRepository._require_dict(data, "Кореневий елемент")

            JSONRepository._check_fields(
                data,
                {"members", "projects"}
            )

            JSONRepository._require_list(data["members"], "Поле «members»")
            JSONRepository._require_list(data["projects"], "Поле «projects»")

            members = []
            members_by_id = {}

            for index, member_data in enumerate(data["members"], start=1):
                try:
                    JSONRepository._require_dict(
                        member_data,
                        f"Учасник №{index}"
                    )

                    JSONRepository._check_fields(
                        member_data,
                        {"id", "name", "role"}
                    )

                    member = Member(
                        member_id=member_data["id"],
                        name=member_data["name"],
                        role=member_data["role"]
                    )

                    if member.id in members_by_id:
                        raise DataFormatError(
                            f"Повторюється ID учасника: {member.id}."
                        )

                    members.append(member)
                    members_by_id[member.id] = member

                except Exception as error:
                    message = (
                        f"Помилка в записі учасника №{index}: {error}"
                    )
                    raise DataFormatError(message) from error

            projects = []
            project_ids = set()
            project_names = set()
            item_ids = set()

            for project_index, project_data in enumerate(
                data["projects"], start=1
            ):
                try:
                    JSONRepository._require_dict(
                        project_data,
                        f"Проєкт №{project_index}"
                    )

                    JSONRepository._check_fields(
                        project_data,
                        {"id", "name", "start", "end", "items"}
                    )

                    project = Project(
                        project_id=project_data["id"],
                        name=project_data["name"],
                        start=JSONRepository._parse_date(
                            project_data["start"],
                            "start"
                        ),
                        end=JSONRepository._parse_date(
                            project_data["end"],
                            "end"
                        )
                    )

                    if project.id in project_ids:
                        raise DataFormatError(
                            f"Повторюється ID проєкту: {project.id}."
                        )

                    project_name_key = project.name.lower()

                    if project_name_key in project_names:
                        raise DataFormatError(
                            f"Повторюється назва проєкту: {project.name}."
                        )

                    project_ids.add(project.id)
                    project_names.add(project_name_key)

                    JSONRepository._require_list(
                        project_data["items"],
                        f"Список завдань проєкту №{project_index}"
                    )

                except Exception as error:
                    message = (
                        f"Помилка в записі проєкту №{project_index}: {error}"
                    )
                    raise DataFormatError(message) from error

                for item_index, item_data in enumerate(
                    project_data["items"], start=1
                ):
                    try:
                        JSONRepository._require_dict(
                            item_data,
                            f"Елемент №{item_index}"
                        )

                        JSONRepository._check_fields(
                            item_data,
                            {
                                "id",
                                "title",
                                "type",
                                "assignee_id",
                                "priority",
                                "status",
                                "deadline",
                                "estimate_hours"
                            }
                        )

                        item_type = item_data["type"]

                        if (
                            not isinstance(item_type, str)
                            or item_type not in JSONRepository.ITEM_TYPES
                        ):
                            raise DataFormatError(
                                f"Невідомий тип елемента: {item_type!r}."
                            )

                        assignee_id = item_data["assignee_id"]

                        if (
                            not isinstance(assignee_id, int)
                            or isinstance(assignee_id, bool)
                            or assignee_id <= 0
                        ):
                            raise DataFormatError(
                                "ID виконавця має бути додатним цілим числом."
                            )

                        if assignee_id not in members_by_id:
                            raise DataFormatError(
                                f"Неіснуючий виконавець з ID {assignee_id}."
                            )

                        try:
                            status = Status(item_data["status"])
                        except ValueError as error:
                            raise DataFormatError(
                                f"Невідомий статус: {item_data['status']!r}."
                            ) from error

                        try:
                            priority = Priority(item_data["priority"])
                        except ValueError as error:
                            raise DataFormatError(
                                f"Невідомий пріоритет: {item_data['priority']!r}."
                            ) from error

                        item_class = JSONRepository.ITEM_TYPES[item_type]

                        item = item_class(
                            item_id=item_data["id"],
                            title=item_data["title"],
                            assignee=members_by_id[assignee_id],
                            priority=priority,
                            status=status,
                            deadline=JSONRepository._parse_date(
                                item_data["deadline"],
                                "deadline"
                            ),
                            estimate_hours=item_data["estimate_hours"]
                        )

                        if item.id in item_ids:
                            raise DataFormatError(
                                f"Повторюється глобальний ID завдання: {item.id}."
                            )

                        item_ids.add(item.id)
                        project.add_item(item)

                    except Exception as error:
                        message = (
                            f"Помилка в проєкті №{project_index}, "
                            f"елементі №{item_index}: {error}"
                        )
                        raise DataFormatError(message) from error

                projects.append(project)

            return members, projects

        except DataFormatError:
            logger.error(
                "Помилка імпорту даних із файлу %s",
                path
            )
            raise

        except Exception as error:
            message = f"Некоректні дані у файлі «{path}»: {error}"
            logger.exception(message)
            raise DataFormatError(message) from error

    @staticmethod
    def save(path, members, projects):

        path = Path(path)
        temp_path = None

        try:
            data = {
                "members": [
                    {
                        "id": member.id,
                        "name": member.name,
                        "role": member.role
                    }
                    for member in members
                ],
                "projects": [
                    {
                        "id": project.id,
                        "name": project.name,
                        "start": project.start.isoformat(),
                        "end": project.end.isoformat(),
                        "items": [
                            {
                                "id": item.id,
                                "title": item.title,
                                "type": item.item_type,
                                "assignee_id": item.assignee.id,
                                "priority": item.priority.value,
                                "status": item.status.value,
                                "deadline": item.deadline.isoformat(),
                                "estimate_hours": item.estimate_hours
                            }
                            for item in project.items
                        ]
                    }
                    for project in projects
                ]
            }

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                suffix=".tmp",
                delete=False
            ) as temp_file:

                temp_path = temp_file.name

                json.dump(
                    data,
                    temp_file,
                    ensure_ascii=False,
                    indent=2
                )

            os.replace(temp_path, path)
            temp_path = None

        except Exception as error:
            message = f"Не вдалося зберегти дані у файл «{path}»: {error}"
            logger.exception(message)
            raise DataFormatError(message) from error

        finally:
            if temp_path is not None:
                try:
                    os.remove(temp_path)
                except OSError:
                    logger.warning(
                        "Не вдалося видалити тимчасовий файл %s",
                        temp_path
                    )