# ШІ: Claude sonnet 5.5 – чернетка unittest-тестів для XmlReportWriter.
# Змінено: XmlReportTestCase
import logging
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from models.bug import Bug
from models.enums import Priority, Status
from models.member import Member
from models.project import Project
from models.task import Task
from repository.json_repository import DataFormatError
from repository.xml_report import XmlReportWriter

TODAY = date(2026, 6, 15)


def setUpModule():

    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def make_item(item_class, item_id, title, deadline, assignee,
              status=Status.TODO):
    return item_class(
        item_id=item_id,
        title=title,
        assignee=assignee,
        priority=Priority.HIGH,
        status=status,
        deadline=deadline,
        estimate_hours=8
    )


def make_project(project_id, name, items):
    project = Project(
        project_id=project_id,
        name=name,
        start=date(2026, 1, 1),
        end=date(2026, 12, 31)
    )
    for item in items:
        project.add_item(item)
    return project


def build_projects():

    member = Member(member_id=1, name="Олена", role="Developer")

    alpha = make_project(1, "Alpha", [
        make_item(Task, 1, "Просрочене завдання", date(2026, 6, 10), member),
        make_item(Bug, 2, "Критичний баг", date(2026, 6, 1), member,
                  status=Status.IN_PROGRESS),
        make_item(Task, 3, "Дедлайн сьогодні", TODAY, member),
        make_item(Task, 4, "Виконане давно", date(2026, 6, 1), member,
                  status=Status.DONE),
        make_item(Task, 5, "Майбутнє завдання", date(2026, 7, 1), member)
    ])

    beta = make_project(2, "Beta", [
        make_item(Task, 6, "Ще не час", date(2026, 8, 1), member)
    ])

    gamma = make_project(3, 'R&D <Фаза> "1"', [
        make_item(Task, 7, 'Тест <b> & "цитата"', date(2026, 6, 14), member)
    ])

    return [alpha, beta, gamma]


class XmlReportTestCase(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.path = self.dir / "report.xml"

    def write_and_parse(self, projects):
        XmlReportWriter.write(self.path, projects, TODAY)
        return ET.parse(self.path).getroot()

    @staticmethod
    def project_element(root, project_id):
        for element in root.findall("project"):
            if element.get("id") == str(project_id):
                return element
        raise AssertionError(f"У звіті немає проєкту {project_id}")

    @staticmethod
    def item_ids(root):
        return {item.get("id") for item in root.iter("item")}


class ReportContentTests(XmlReportTestCase):

    def test_root_has_report_date(self):
        root = self.write_and_parse(build_projects())

        self.assertEqual(root.tag, "report")
        self.assertEqual(root.get("date"), "2026-06-15")

    def test_project_with_overdue_items(self):
        root = self.write_and_parse(build_projects())
        alpha = self.project_element(root, 1)

        self.assertEqual(alpha.get("name"), "Alpha")
        self.assertEqual(alpha.get("overdue_count"), "2")

        items = {item.get("id"): item for item in alpha.findall("item")}
        self.assertEqual(set(items), {"1", "2"})

        task = items["1"]
        self.assertEqual(task.get("type"), "Task")
        self.assertEqual(task.findtext("title"), "Просрочене завдання")
        self.assertEqual(task.findtext("assignee"), "Олена")
        self.assertEqual(task.findtext("deadline"), "2026-06-10")
        self.assertEqual(task.findtext("status"), "todo")
        self.assertEqual(task.findtext("priority"), "high")
        self.assertEqual(task.findtext("days_overdue"), "5")

        bug = items["2"]
        self.assertEqual(bug.get("type"), "Bug")
        self.assertEqual(bug.findtext("status"), "in_progress")
        self.assertEqual(bug.findtext("days_overdue"), "14")

    def test_project_without_overdue_is_listed_with_zero(self):
        root = self.write_and_parse(build_projects())
        beta = self.project_element(root, 2)

        self.assertEqual(beta.get("overdue_count"), "0")
        self.assertEqual(beta.findall("item"), [])

    def test_deadline_today_is_not_overdue(self):
        root = self.write_and_parse(build_projects())

        self.assertNotIn("3", self.item_ids(root))

    def test_done_item_is_not_overdue(self):
        root = self.write_and_parse(build_projects())

        self.assertNotIn("4", self.item_ids(root))

    def test_future_item_is_not_overdue(self):
        root = self.write_and_parse(build_projects())

        self.assertNotIn("5", self.item_ids(root))

    def test_special_characters_and_cyrillic_survive(self):
        root = self.write_and_parse(build_projects())
        gamma = self.project_element(root, 3)

        self.assertEqual(gamma.get("name"), 'R&D <Фаза> "1"')
        item = gamma.find("item")
        self.assertEqual(item.findtext("title"), 'Тест <b> & "цитата"')

    def test_projects_keep_order_and_count(self):
        root = self.write_and_parse(build_projects())
        projects = root.findall("project")

        self.assertEqual([p.get("id") for p in projects], ["1", "2", "3"])
        self.assertEqual(
            [p.get("name") for p in projects],
            ["Alpha", "Beta", 'R&D <Фаза> "1"']
        )

    def test_empty_project_list(self):
        root = self.write_and_parse([])

        self.assertEqual(root.get("date"), "2026-06-15")
        self.assertEqual(root.findall("project"), [])


class ReportWriteFailureTests(XmlReportTestCase):

    def test_missing_folder_raises(self):
        target = self.dir / "no_such_folder" / "report.xml"

        with self.assertRaises(DataFormatError):
            XmlReportWriter.write(target, build_projects(), TODAY)

    def test_failed_write_keeps_existing_file(self):
        self.path.write_text("СТАРИЙ ЗВІТ", encoding="utf-8")

        broken = SimpleNamespace(id=1, name="X", items=[object()])

        with self.assertRaises(DataFormatError):
            XmlReportWriter.write(self.path, [broken], TODAY)

        self.assertEqual(
            self.path.read_text(encoding="utf-8"), "СТАРИЙ ЗВІТ"
        )
        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_no_temp_files_after_successful_write(self):
        XmlReportWriter.write(self.path, build_projects(), TODAY)

        self.assertEqual(list(self.dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()