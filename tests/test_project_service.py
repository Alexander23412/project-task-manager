# ШІ: Claude sonnet 5.5 – чернетка unittest-тестів для ProjectService (етапи 1–4).
# Змінено: class CopyTests
import logging
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

from models.bug import Bug
from models.enums import Priority, Status
from models.task import Task
from repository.json_repository import DataFormatError
from services.project_service import ProjectService

START = date(2026, 1, 1)
END = date(2026, 12, 31)


def setUpModule():

    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def add_task(project, item_id, assignee, title=None):
    task = Task(
        item_id=item_id,
        title=title or f"Завдання {item_id}",
        assignee=assignee,
        priority=Priority.MEDIUM,
        status=Status.TODO,
        deadline=date(2026, 6, 1),
        estimate_hours=8
    )
    project.add_item(task)
    return task


class MemberTests(unittest.TestCase):

    def setUp(self):
        self.service = ProjectService()

    def test_add_member_gives_unique_ids(self):
        first = self.service.add_member("Олена", "Developer")
        second = self.service.add_member("Іван", "Tester")

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(self.service.members), 2)

    def test_update_member(self):
        member = self.service.add_member("Олена", "Developer")

        self.service.update_member(member, name="Олена К.", role="Lead")

        self.assertEqual(member.name, "Олена К.")
        self.assertEqual(member.role, "Lead")

    def test_name_is_rolled_back_when_role_is_invalid(self):
        member = self.service.add_member("Олена", "Developer")

        with self.assertRaises(ValueError):
            self.service.update_member(member, name="Нове", role="")

        self.assertEqual(member.name, "Олена")
        self.assertEqual(member.role, "Developer")

    def test_role_is_unchanged_when_name_is_invalid(self):
        member = self.service.add_member("Олена", "Developer")

        with self.assertRaises(ValueError):
            self.service.update_member(member, name="", role="Lead")

        self.assertEqual(member.name, "Олена")
        self.assertEqual(member.role, "Developer")

    def test_update_unknown_member_raises(self):
        stranger = ProjectService().add_member("Чужий", "Dev")

        with self.assertRaises(ValueError):
            self.service.update_member(stranger, name="X")

    def test_delete_member_cascades_and_counts(self):
        olena = self.service.add_member("Олена", "Developer")
        ivan = self.service.add_member("Іван", "Tester")
        alpha = self.service.add_project("Alpha", START, END)
        beta = self.service.add_project("Beta", START, END)

        add_task(alpha, 1, olena)
        add_task(alpha, 2, olena)
        add_task(alpha, 3, ivan)
        add_task(beta, 4, olena)

        self.assertEqual(self.service.count_member_items(olena), 3)

        removed = self.service.delete_member(olena)

        self.assertEqual(removed, 3)
        self.assertEqual(self.service.members, [ivan])
        self.assertEqual([i.id for i in alpha.items], [3])
        self.assertEqual(beta.items, [])

    def test_delete_member_without_items(self):
        member = self.service.add_member("Олена", "Developer")

        self.assertEqual(self.service.delete_member(member), 0)
        self.assertEqual(self.service.members, [])


class ProjectTests(unittest.TestCase):

    def setUp(self):
        self.service = ProjectService()

    def test_add_project(self):
        project = self.service.add_project("Alpha", START, END)

        self.assertEqual(self.service.projects, [project])

    def test_duplicate_name_in_other_case_is_rejected(self):
        self.service.add_project("Alpha", START, END)

        with self.assertRaises(ValueError):
            self.service.add_project("ALPHA", START, END)

        self.assertEqual(len(self.service.projects), 1)

    def test_rename_to_other_project_name_is_rejected(self):
        self.service.add_project("Alpha", START, END)
        beta = self.service.add_project("Beta", START, END)

        with self.assertRaises(ValueError):
            self.service.update_project(beta, name="alpha")

        self.assertEqual(beta.name, "Beta")

    def test_rename_to_own_name_in_other_case_is_allowed(self):
        alpha = self.service.add_project("Alpha", START, END)

        self.service.update_project(alpha, name="ALPHA")

        self.assertEqual(alpha.name, "ALPHA")

    def test_delete_project(self):
        alpha = self.service.add_project("Alpha", START, END)

        self.service.delete_project(alpha)

        self.assertEqual(self.service.projects, [])

    def test_delete_unknown_project_raises(self):
        stranger = ProjectService().add_project("Чужий", START, END)

        with self.assertRaises(ValueError):
            self.service.delete_project(stranger)


class ItemTests(unittest.TestCase):

    def setUp(self):
        self.service = ProjectService()
        self.member = self.service.add_member("Олена", "Developer")
        self.alpha = self.service.add_project("Alpha", START, END)
        self.beta = self.service.add_project("Beta", START, END)

    def add(self, project, title, item_type="Task", assignee=None,
            deadline=date(2026, 6, 1)):
        return self.service.add_item(
            project,
            item_type,
            title,
            assignee or self.member,
            Priority.MEDIUM,
            Status.TODO,
            deadline,
            8
        )

    def test_item_with_unknown_assignee_is_rejected(self):
        stranger = ProjectService().add_member("Чужий", "Dev")

        with self.assertRaises(ValueError):
            self.add(self.alpha, "Завдання", assignee=stranger)

        self.assertEqual(self.alpha.items, [])

    def test_item_ids_are_globally_unique(self):
        items = [
            self.add(self.alpha, "A1"),
            self.add(self.alpha, "A2"),
            self.add(self.beta, "B1"),
            self.add(self.beta, "B2")
        ]

        ids = [item.id for item in items]
        self.assertEqual(len(set(ids)), 4)

    def test_item_class_matches_type(self):
        bug = self.add(self.alpha, "Баг", item_type="Bug")

        self.assertIsInstance(bug, Bug)
        self.assertEqual(bug.item_type, "Bug")

    def test_unknown_item_type_is_rejected(self):
        with self.assertRaises(ValueError):
            self.add(self.alpha, "Завдання", item_type="Epic")

        self.assertEqual(self.alpha.items, [])

    def test_deadline_outside_project_is_rejected(self):
        with self.assertRaises(ValueError):
            self.add(self.alpha, "Завдання", deadline=date(2099, 1, 1))

        self.assertEqual(self.alpha.items, [])

    def test_duplicate_title_only_inside_one_project(self):
        self.add(self.alpha, "Спільна назва")

        with self.assertRaises(ValueError):
            self.add(self.alpha, "спільна НАЗВА")

        self.add(self.beta, "Спільна назва")
        self.assertEqual(len(self.beta.items), 1)

    def test_update_item_changes_fields(self):
        item = self.add(self.alpha, "Завдання")
        other = self.service.add_member("Іван", "Tester")

        self.service.update_item(
            self.alpha,
            item,
            title="Нова назва",
            priority=Priority.HIGH,
            assignee=other
        )

        self.assertEqual(item.title, "Нова назва")
        self.assertEqual(item.priority, Priority.HIGH)
        self.assertIs(item.assignee, other)

    def test_update_item_with_unknown_assignee_changes_nothing(self):
        item = self.add(self.alpha, "Завдання")
        stranger = ProjectService().add_member("Чужий", "Dev")

        with self.assertRaises(ValueError):
            self.service.update_item(
                self.alpha, item, title="Інша", assignee=stranger
            )

        self.assertEqual(item.title, "Завдання")
        self.assertIs(item.assignee, self.member)

    def test_update_item_unknown_field_is_rejected(self):
        item = self.add(self.alpha, "Завдання")

        with self.assertRaises(ValueError):
            self.service.update_item(self.alpha, item, color="red")

    def test_delete_item(self):
        item = self.add(self.alpha, "Завдання")

        self.service.delete_item(self.alpha, item)

        self.assertEqual(self.alpha.items, [])

    def test_snapshot_items_returns_pairs_from_all_projects(self):
        first = self.add(self.alpha, "A1")
        second = self.add(self.beta, "B1")

        pairs = self.service.snapshot_items()

        self.assertEqual(pairs, [(self.alpha, first), (self.beta, second)])
        pairs.clear()
        self.assertEqual(len(self.service.snapshot_items()), 2)

    def test_delete_item_from_wrong_project_raises(self):
        item = self.add(self.alpha, "Завдання")

        with self.assertRaises(ValueError):
            self.service.delete_item(self.beta, item)

        self.assertEqual(self.alpha.items, [item])


class SearchTests(unittest.TestCase):

    def setUp(self):
        self.service = ProjectService()
        self.olena = self.service.add_member("Олена", "Developer")
        self.ivan = self.service.add_member("Іван", "Tester")
        self.project = self.service.add_project("Alpha", START, END)

   
        self.add("Налаштувати сервер", "Task", Priority.HIGH,
                 Status.TODO, date(2026, 6, 10), self.olena)
        self.add("Написати документацію", "Task", Priority.LOW,
                 Status.DONE, date(2026, 5, 1), self.ivan)
        self.add("Виправити сервер баг", "Bug", Priority.MEDIUM,
                 Status.IN_PROGRESS, date(2026, 7, 1), self.olena)
        self.add("Реліз", "Milestone", Priority.HIGH,
                 Status.TODO, date(2026, 6, 1), self.ivan)

    def add(self, title, item_type, priority, status, deadline, assignee):
        return self.service.add_item(
            self.project, item_type, title, assignee,
            priority, status, deadline, 8
        )

    def ids(self, **kwargs):
        items = self.service.find_items(self.project, **kwargs)
        return [item.id for item in items]

    def test_empty_filters_return_everything(self):
        self.assertEqual(sorted(self.ids()), [1, 2, 3, 4])

    def test_empty_string_filters_mean_everything(self):
        self.assertEqual(
            sorted(self.ids(text="", status="", priority="", assignee="")),
            [1, 2, 3, 4]
        )

    def test_search_by_substring_ignores_case(self):
        self.assertEqual(sorted(self.ids(text="СЕРВЕР")), [1, 3])
        self.assertEqual(sorted(self.ids(text="  серв ")), [1, 3])

    def test_search_without_matches(self):
        self.assertEqual(self.ids(text="немає такого"), [])

    def test_filters_combine_with_and(self):
        self.assertEqual(
            sorted(self.ids(status=Status.TODO, priority=Priority.HIGH)),
            [1, 4]
        )
        self.assertEqual(
            self.ids(status=Status.TODO, priority=Priority.HIGH,
                     assignee=self.olena),
            [1]
        )
        self.assertEqual(
            self.ids(text="сервер", status=Status.IN_PROGRESS),
            [3]
        )
        self.assertEqual(
            self.ids(status=Status.TODO, priority=Priority.LOW), []
        )

    def test_sort_by_deadline(self):
        self.assertEqual(self.ids(sort_by="deadline"), [2, 4, 1, 3])
        self.assertEqual(
            self.ids(sort_by="deadline", descending=True), [3, 1, 4, 2]
        )

    def test_sort_by_priority_uses_low_medium_high_order(self):
 
        self.assertEqual(self.ids(sort_by="priority"), [2, 3, 1, 4])
        self.assertEqual(
            self.ids(sort_by="priority", descending=True), [4, 1, 3, 2]
        )

    def test_sort_by_title(self):
        self.assertEqual(self.ids(sort_by="title"), [3, 1, 2, 4])

    def test_unknown_sort_field_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.find_items(self.project, sort_by="color")

    def test_unknown_project_is_rejected(self):
        stranger = ProjectService().add_project("Чужий", START, END)

        with self.assertRaises(ValueError):
            self.service.find_items(stranger)

    def test_result_is_a_new_list_and_source_is_unchanged(self):
        result = self.service.find_items(
            self.project, sort_by="deadline", descending=True
        )
        result.clear()

        self.assertEqual(
            [item.id for item in self.project.items], [1, 2, 3, 4]
        )


class UpdateProjectTests(unittest.TestCase):

    def setUp(self):
        self.service = ProjectService()
        self.member = self.service.add_member("Олена", "Developer")
        self.project = self.service.add_project("Alpha", START, END)
        self.service.add_item(
            self.project, "Task", "Завдання", self.member,
            Priority.MEDIUM, Status.TODO, date(2026, 6, 1), 8
        )

    def assert_unchanged(self):
        self.assertEqual(self.project.name, "Alpha")
        self.assertEqual(self.project.start, START)
        self.assertEqual(self.project.end, END)

    def test_name_is_rolled_back_when_start_is_rejected(self):

        with self.assertRaises(ValueError):
            self.service.update_project(
                self.project, name="Нове", start=date(2026, 7, 1)
            )

        self.assert_unchanged()

    def test_name_is_rolled_back_when_end_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.update_project(
                self.project, name="Нове", end=date(2026, 5, 1)
            )

        self.assert_unchanged()

    def test_applied_end_is_rolled_back_when_start_is_rejected(self):

        with self.assertRaises(ValueError):
            self.service.update_project(
                self.project,
                name="Нове",
                start=date(2027, 1, 1),
                end=date(2027, 12, 31)
            )

        self.assert_unchanged()

    def test_successful_update_of_all_fields(self):
        empty = self.service.add_project("Порожній", START, END)

        self.service.update_project(
            empty,
            name="Новий",
            start=date(2027, 1, 1),
            end=date(2027, 12, 31)
        )

        self.assertEqual(empty.name, "Новий")
        self.assertEqual(empty.start, date(2027, 1, 1))
        self.assertEqual(empty.end, date(2027, 12, 31))

    def test_non_string_name_raises_value_error(self):
        for bad_name in (123, "", "   "):
            with self.subTest(name=bad_name):
                with self.assertRaises(ValueError):
                    self.service.update_project(self.project, name=bad_name)

        self.assert_unchanged()

    def test_wrong_date_types_raise_value_error(self):
        for field in ("start", "end"):
            for bad_value in ("2026-01-01", datetime(2026, 6, 1, 12, 0), 5):
                with self.subTest(field=field, value=bad_value):
                    with self.assertRaises(ValueError):
                        self.service.update_project(
                            self.project, **{field: bad_value}
                        )

        self.assert_unchanged()

    def test_duplicate_name_is_compared_after_strip(self):
        self.service.add_project("Beta", START, END)

        with self.assertRaises(ValueError):
            self.service.update_project(self.project, name="  beta ")

        self.assert_unchanged()


def snapshot(service):

    members = [(m.id, m.name, m.role) for m in service.members]
    projects = [
        (
            p.id, p.name, p.start, p.end,
            [
                (i.id, i.title, i.item_type, i.assignee.id, i.priority,
                 i.status, i.deadline, i.estimate_hours)
                for i in p.items
            ]
        )
        for p in service.projects
    ]
    return members, projects


def make_filled_service():
    service = ProjectService()
    olena = service.add_member("Олена", "Developer")
    ivan = service.add_member("Іван", "Tester")
    alpha = service.add_project("Alpha", START, END)
    beta = service.add_project("Beta", START, END)

    service.add_item(alpha, "Task", "Task A1", olena, Priority.HIGH,
                     Status.TODO, date(2026, 6, 1), 8)
    service.add_item(alpha, "Bug", "Bug A2", ivan, Priority.LOW,
                     Status.IN_PROGRESS, date(2026, 5, 1), 4)
    service.add_item(beta, "Milestone", "Mile B1", olena, Priority.MEDIUM,
                     Status.DONE, date(2026, 8, 1), 2)
    return service


class FileTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_save_then_load_into_new_service(self):
        source = make_filled_service()
        path = self.dir / "data.json"

        source.save_file(path)
        target = ProjectService()
        target.load_file(path)

        self.assertEqual(snapshot(target), snapshot(source))

    def test_corrupted_file_keeps_existing_data(self):
        service = make_filled_service()
        before = snapshot(service)
        members_before = service.members
        projects_before = service.projects
        path = self.dir / "broken.json"
        path.write_text('{"members": [', encoding="utf-8")

        with self.assertRaises(DataFormatError):
            service.load_file(path)

        self.assertEqual(snapshot(service), before)
        self.assertEqual(service.members, members_before)
        self.assertEqual(service.projects, projects_before)

    def test_missing_file_keeps_existing_data(self):
        service = make_filled_service()
        before = snapshot(service)

        with self.assertRaises(DataFormatError):
            service.load_file(self.dir / "does_not_exist.json")

        self.assertEqual(snapshot(service), before)

    def test_load_replaces_data_and_ids_continue(self):
        source = make_filled_service()
        path = self.dir / "data.json"
        source.save_file(path)

        target = ProjectService()
        target.add_member("Тимчасовий", "Temp")
        target.load_file(path)

        self.assertEqual(snapshot(target), snapshot(source))

        member = target.add_member("Нова", "Dev")
        project = target.add_project("Gamma", START, END)
        item = target.add_item(
            target.projects[0], "Task", "Нове завдання", target.members[0],
            Priority.LOW, Status.TODO, date(2026, 6, 2), 1
        )

        self.assertEqual(member.id, 3)
        self.assertEqual(project.id, 3)
        self.assertEqual(item.id, 4)

    def test_save_to_missing_folder_raises(self):
        service = make_filled_service()

        with self.assertRaises(DataFormatError):
            service.save_file(self.dir / "no_such_folder" / "data.json")

    def test_export_overdue_report_creates_readable_xml(self):
        service = make_filled_service()
        path = self.dir / "report.xml"

        service.export_overdue_report(path, date(2026, 7, 1))

        root = ET.parse(path).getroot()
        self.assertEqual(root.get("date"), "2026-07-01")
        counts = {p.get("name"): p.get("overdue_count")
                  for p in root.findall("project")}
        self.assertEqual(counts, {"Alpha": "2", "Beta": "0"})


class CopyTests(unittest.TestCase):

    def test_members_and_projects_return_copies(self):
        service = ProjectService()
        service.add_member("Олена", "Developer")
        service.add_project("Alpha", START, END)

        service.members.clear()
        service.projects.clear()

        self.assertEqual(len(service.members), 1)
        self.assertEqual(len(service.projects), 1)


if __name__ == "__main__":
    unittest.main()


class LoggingTests(unittest.TestCase):


    def setUp(self):
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable, logging.CRITICAL)

    def test_cascade_deletion_logs_removed_count(self):
        service = ProjectService()
        member = service.add_member("Олена", "Dev")
        project = service.add_project("Проєкт", date(2026, 1, 1), date(2026, 12, 31))
        for n in range(3):
            service.add_item(
                project, "Task", f"Завдання {n}", member,
                Priority.LOW, Status.TODO, date(2026, 5, 1), 1
            )

        with self.assertLogs("services.project_service", "INFO") as logs:
            removed = service.delete_member(member)

        self.assertEqual(removed, 3)
        self.assertIn("видалено завдань: 3", "\n".join(logs.output))

    def test_failed_operation_is_not_logged_as_success(self):
        service = ProjectService()
        service.add_project("Проєкт", date(2026, 1, 1), date(2026, 12, 31))

        with self.assertLogs("services.project_service", "INFO") as logs:
            logging.getLogger("services.project_service").info("маркер")
            with self.assertRaises(ValueError):
                service.add_project("проєкт", date(2026, 1, 1), date(2026, 12, 31))

        self.assertEqual(len(logs.output), 1)