# ШІ: Claude sonnet 5.5 – Перевірка коду
import logging
import os
import tempfile
import xml.etree.ElementTree as ET

from pathlib import Path

from repository.json_repository import DataFormatError


logger = logging.getLogger(__name__)


class XmlReportWriter:
    """Записує XML-звіт про прострочені завдання за проєктами.

    Клас лише пише файл; читати XML він не вміє і не повинен.
    """

    @staticmethod
    def _build_report(projects, today):
        root = ET.Element("report", {"date": today.isoformat()})

        for project in projects:
            overdue_items = [
                item for item in project.items if item.is_overdue(today)
            ]

            project_element = ET.SubElement(
                root,
                "project",
                {
                    "id": str(project.id),
                    "name": project.name,
                    "overdue_count": str(len(overdue_items))
                }
            )

            for item in overdue_items:
                item_element = ET.SubElement(
                    project_element,
                    "item",
                    {"id": str(item.id), "type": item.item_type}
                )

                fields = [
                    ("title", item.title),
                    ("assignee", item.assignee.name),
                    ("deadline", item.deadline.isoformat()),
                    ("status", item.status.value),
                    ("priority", item.priority.value),
                    ("days_overdue", str((today - item.deadline).days))
                ]

                for tag, text in fields:
                    ET.SubElement(item_element, tag).text = text

        return root

    @staticmethod
    def write(path, projects, today):
        path = Path(path)
        temp_path = None

        try:
            root = XmlReportWriter._build_report(projects, today)
            ET.indent(root)

            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                suffix=".tmp",
                delete=False
            ) as temp_file:

                temp_path = temp_file.name

                ET.ElementTree(root).write(
                    temp_file,
                    encoding="utf-8",
                    xml_declaration=True
                )

            os.replace(temp_path, path)
            temp_path = None

        except Exception as error:
            message = f"Не вдалося записати XML-звіт у файл «{path}»: {error}"
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