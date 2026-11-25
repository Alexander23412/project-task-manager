# ШІ: Claude sonnet 5.5 – чернетка unittest-тестів для MainPresenter (з фіктивним вікном).
# Змінено: class FakeTasks class CloseTests
import logging
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from models.enums import Priority, Status
from presenters.main_presenter import MainPresenter
from services.background_tasks import (
    DONE, ERROR, PROGRESS, RESULT, BackgroundTasks, Message
)
from services.project_service import ProjectService

START = date(2026, 1, 1)
END = date(2026, 12, 31)
TODAY = date(2026, 7, 1)


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeView:


    def __init__(self):
        self.projects = []
        self.selected_id = None
        self.members = []
        self.items = []
        self.errors = []
        self.infos = []
        self.confirms = []
        self.answer = True
        self.busy_states = []
        self.progress = []
        self.progress_stopped = 0
        self.workload = None
        self.overdue = None
        self.closed = False
        self.fail_on_progress = False

    def show_projects(self, rows, selected_id):
        self.projects = rows
        self.selected_id = selected_id

    def show_members(self, rows):
        self.members = rows

    def show_items(self, rows):
        self.items = rows

    def show_error(self, message):
        self.errors.append(message)

    def show_info(self, message):
        self.infos.append(message)

    def confirm(self, message):
        self.confirms.append(message)
        return self.answer

    def set_busy(self, is_busy):
        self.busy_states.append(is_busy)

    def show_progress(self, done, total):
        if self.fail_on_progress:
            raise RuntimeError("збій у вікні")
        self.progress.append((done, total))

    def stop_progress(self):
        self.progress_stopped += 1

    def show_workload(self, rows):
        self.workload = rows

    def show_overdue(self, rows):
        self.overdue = rows

    def close(self):
        self.closed = True


def pump(presenter, timeout=10.0):

    deadline = time.monotonic() + timeout

    while presenter.is_busy:
        if time.monotonic() > deadline:
            raise AssertionError("Фонова операція не завершилась вчасно.")
        presenter.process_messages()
        time.sleep(0.005)

    presenter.process_messages()


class PresenterTestCase(unittest.TestCase):


    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

        service = ProjectService()
        olena = service.add_member("Олена", "Developer")
        ivan = service.add_member("Іван", "Tester")
        alpha = service.add_project("Alpha", START, END)
        beta = service.add_project("Beta", START, END)

        def add(project, title, member, priority, status, deadline, hours):
            service.add_item(project, "Task", title, member, priority,
                             status, deadline, hours)

        add(alpha, "A1", olena, Priority.HIGH, Status.TODO,
            date(2026, 6, 1), 8)
        add(alpha, "A2", ivan, Priority.LOW, Status.IN_PROGRESS,
            date(2026, 5, 1), 4)
        add(alpha, "A3", olena, Priority.MEDIUM, Status.DONE,
            date(2026, 8, 1), 2)
        add(beta, "B1", olena, Priority.MEDIUM, Status.TODO,
            date(2026, 6, 10), 5)

        self.service = service
        self.tasks = BackgroundTasks(service, max_workers=2, chunk_size=2)
        self.addCleanup(self.tasks.shutdown)
        self.view = FakeView()
        self.presenter = MainPresenter(
            service, self.tasks, self.view, today_provider=lambda: TODAY
        )
        self.presenter.start()

    def item_ids(self):
        return [row["id"] for row in self.view.items]

    def member_ids(self):
        return [row["id"] for row in self.view.members]

    def project_ids(self):
        return [row["id"] for row in self.view.projects]


class RefreshTests(PresenterTestCase):

    def test_start_shows_projects_and_members_without_items(self):
        self.assertEqual(self.project_ids(), [1, 2])
        self.assertEqual(self.member_ids(), [1, 2])
        self.assertIsNone(self.view.selected_id)
        self.assertEqual(self.view.items, [])

    def test_project_row_has_plain_data(self):
        row = self.view.projects[0]

        self.assertEqual(row["name"], "Alpha")
        self.assertEqual(row["start"], "2026-01-01")
        self.assertEqual(row["end"], "2026-12-31")
        self.assertEqual(row["items"], 3)

    def test_select_project_shows_items_sorted_by_deadline(self):
        self.assertTrue(self.presenter.select_project(1))

        self.assertEqual(self.view.selected_id, 1)
        self.assertEqual(self.item_ids(), [2, 1, 3])

        overdue = {row["id"]: row["overdue"] for row in self.view.items}
        self.assertEqual(overdue, {1: True, 2: True, 3: False})

        row = self.view.items[1]
        self.assertEqual(row["assignee_id"], 1)
        self.assertEqual(row["priority"], "high")
        self.assertEqual(row["status"], "todo")
        self.assertEqual(row["assignee"], "Олена")

    def test_filters_and_sorting(self):
        self.presenter.select_project(1)

        self.presenter.set_filters(status="todo")
        self.assertEqual(self.item_ids(), [1])

        self.presenter.set_filters(status="done")
        self.assertEqual(self.item_ids(), [3])

        self.presenter.set_filters(assignee_id=2)
        self.assertEqual(self.item_ids(), [2])

        self.presenter.set_filters()
        self.presenter.set_sort("priority", descending=True)
        self.assertEqual(self.item_ids(), [1, 3, 2])

    def test_invalid_filter_and_sort_are_reported(self):
        self.presenter.select_project(1)

        self.assertFalse(self.presenter.set_filters(status="nope"))
        self.assertFalse(self.presenter.set_sort("color"))

        self.assertEqual(len(self.view.errors), 2)
        self.assertEqual(self.item_ids(), [2, 1, 3])

    def test_unknown_project_is_reported(self):
        self.assertFalse(self.presenter.select_project(99))

        self.assertTrue(self.view.errors)
        self.assertIsNone(self.view.selected_id)


class MemberTests(PresenterTestCase):

    def test_add_member(self):
        self.assertTrue(self.presenter.add_member("Марія", "Manager"))

        self.assertEqual(len(self.view.members), 3)
        self.assertEqual(self.view.members[-1]["name"], "Марія")

    def test_invalid_member_is_reported_and_not_added(self):
        self.assertFalse(self.presenter.add_member("", "Manager"))

        self.assertTrue(self.view.errors)
        self.assertEqual(len(self.view.members), 2)

    def test_update_member_is_atomic(self):
        self.assertFalse(self.presenter.update_member(1, "Нове", ""))

        self.assertTrue(self.view.errors)
        self.assertEqual(self.view.members[0]["name"], "Олена")

        self.assertTrue(self.presenter.update_member(1, "Нове", "Lead"))
        self.assertEqual(self.view.members[0]["name"], "Нове")

    def test_delete_member_asks_with_item_count_and_cascades(self):
        self.presenter.select_project(1)

        self.assertTrue(self.presenter.delete_member(1))

        self.assertEqual(len(self.view.confirms), 1)
        self.assertIn("3", self.view.confirms[0])
        self.assertEqual(self.member_ids(), [2])
        self.assertEqual(self.item_ids(), [2])
        self.assertEqual(self.view.projects[1]["items"], 0)

    def test_delete_member_declined_changes_nothing(self):
        self.view.answer = False

        self.assertFalse(self.presenter.delete_member(1))

        self.assertEqual(self.member_ids(), [1, 2])
        self.assertEqual(self.view.projects[0]["items"], 3)

    def test_delete_member_without_items(self):
        self.presenter.add_member("Марія", "Manager")

        self.assertTrue(self.presenter.delete_member(3))

        self.assertEqual(self.member_ids(), [1, 2])


class ProjectTests(PresenterTestCase):

    def test_add_project_selects_it(self):
        self.assertTrue(
            self.presenter.add_project("Gamma", "2026-01-01", "2026-06-30")
        )

        self.assertEqual(self.project_ids(), [1, 2, 3])
        self.assertEqual(self.view.selected_id, 3)

    def test_invalid_projects_are_reported(self):
        cases = [
            ("alpha", "2026-01-01", "2026-06-30"),
            ("Gamma", "01.02.2026", "2026-06-30"),   
            ("Gamma", "2026-13-45", "2026-06-30"),  
            ("Gamma", "2026-06-30", "2026-01-01")    
        ]

        for args in cases:
            with self.subTest(args=args):
                self.assertFalse(self.presenter.add_project(*args))

        self.assertEqual(len(self.view.errors), 4)
        self.assertEqual(self.project_ids(), [1, 2])

    def test_update_project_failure_changes_nothing(self):

        ok = self.presenter.update_project(
            1, "Нове", "2026-01-01", "2026-07-01"
        )

        self.assertFalse(ok)
        project = self.service.projects[0]
        self.assertEqual(project.name, "Alpha")
        self.assertEqual(project.end, END)

    def test_delete_project_requires_confirmation(self):
        self.view.answer = False
        self.assertFalse(self.presenter.delete_project(1))
        self.assertEqual(self.project_ids(), [1, 2])

        self.view.answer = True
        self.assertTrue(self.presenter.delete_project(1))
        self.assertEqual(self.project_ids(), [2])
        self.assertEqual(len(self.view.confirms), 2)


class ItemTests(PresenterTestCase):

    def add_item(self, **overrides):
        values = dict(
            item_type="Bug", title="Новий баг", assignee_id=2,
            priority="high", status="todo", deadline="2026-09-01",
            estimate_hours="2,5"
        )
        values.update(overrides)
        return self.presenter.add_item(**values)

    def test_add_item_requires_selected_project(self):
        self.assertFalse(self.add_item())

        self.assertIn("проєкт", self.view.errors[-1])

    def test_add_item(self):
        self.presenter.select_project(1)

        self.assertTrue(self.add_item())

        self.assertEqual(len(self.view.items), 4)
        row = next(r for r in self.view.items if r["title"] == "Новий баг")
        self.assertEqual(row["type"], "Bug")
        self.assertEqual(row["estimate_hours"], 2.5)

    def test_item_without_assignee_has_clear_error(self):
        self.presenter.select_project(1)

        self.assertFalse(self.add_item(assignee_id=None))

        self.assertEqual(self.view.errors[-1], "Виконавця не вибрано.")

    def test_invalid_items_are_reported(self):
        self.presenter.select_project(1)

        cases = [
            {"assignee_id": 99},                
            {"estimate_hours": "abc"},
            {"estimate_hours": "0"},
            {"deadline": "2099-01-01"},        
            {"priority": ""},
            {"item_type": "Epic"},
            {"title": "A1"}                    
        ]

        for overrides in cases:
            with self.subTest(overrides=overrides):
                self.assertFalse(self.add_item(**overrides))

        self.assertEqual(len(self.view.errors), len(cases))
        self.assertEqual(len(self.view.items), 3)

    def test_update_item(self):
        self.presenter.select_project(1)

        ok = self.presenter.update_item(
            1, "Нова назва", 2, "low", "done", "2026-06-02", "3"
        )

        self.assertTrue(ok)
        row = next(r for r in self.view.items if r["id"] == 1)
        self.assertEqual(row["title"], "Нова назва")
        self.assertEqual(row["assignee"], "Іван")
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["estimate_hours"], 3)

    def test_update_item_with_invalid_value_changes_nothing(self):
        self.presenter.select_project(1)

        ok = self.presenter.update_item(
            1, "Інша", 2, "low", "done", "2026-06-02", "abc"
        )

        self.assertFalse(ok)
        row = next(r for r in self.view.items if r["id"] == 1)
        self.assertEqual(row["title"], "A1")

    def test_update_item_that_is_not_displayed_is_reported(self):
        self.presenter.select_project(1)
        self.presenter.set_filters(status="done")     

        ok = self.presenter.update_item(
            1, "X", 1, "low", "todo", "2026-06-02", "1"
        )

        self.assertFalse(ok)
        self.assertTrue(self.view.errors)

    def test_delete_item_requires_confirmation(self):
        self.presenter.select_project(1)

        self.view.answer = False
        self.assertFalse(self.presenter.delete_item(1))
        self.assertEqual(len(self.view.items), 3)

        self.view.answer = True
        self.assertTrue(self.presenter.delete_item(1))
        self.assertEqual(self.item_ids(), [2, 3])


class FileTests(PresenterTestCase):

    def test_export_json_creates_file(self):
        path = self.dir / "out.json"

        self.assertTrue(self.presenter.export_json(path))

        self.assertTrue(path.exists())
        self.assertTrue(self.view.infos)

    def test_export_json_to_missing_folder_is_reported(self):
        path = self.dir / "no_such_folder" / "out.json"

        self.assertFalse(self.presenter.export_json(path))

        self.assertTrue(self.view.errors)

    def test_export_xml_uses_presenter_date(self):
        path = self.dir / "report.xml"

        self.assertTrue(self.presenter.export_xml_report(path))

        root = ET.parse(path).getroot()
        self.assertEqual(root.get("date"), "2026-07-01")
        counts = {p.get("name"): p.get("overdue_count")
                  for p in root.findall("project")}
        self.assertEqual(counts, {"Alpha": "2", "Beta": "1"})

    def test_import_replaces_data_and_resets_selection(self):
        other = ProjectService()
        other.add_member("Нова", "Analyst")
        other.add_project("Gamma", START, END)
        path = self.dir / "other.json"
        other.save_file(path)
        self.presenter.select_project(1)

        self.assertTrue(self.presenter.import_file(path))
        self.assertTrue(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states[-1], True)

        pump(self.presenter)

        self.assertFalse(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states[-1], False)
        self.assertGreaterEqual(self.view.progress_stopped, 1)
        self.assertIsNone(self.view.selected_id)
        self.assertEqual(self.view.items, [])
        self.assertEqual([m["name"] for m in self.view.members], ["Нова"])
        self.assertEqual([p["name"] for p in self.view.projects], ["Gamma"])
        self.assertTrue(any("Імпортовано" in text for text in self.view.infos))

    def test_import_of_broken_file_keeps_data_and_reports_error(self):
        path = self.dir / "broken.json"
        path.write_text('{"members": [', encoding="utf-8")

        self.presenter.import_file(path)
        pump(self.presenter)

        self.assertTrue(self.view.errors)
        self.assertEqual(self.member_ids(), [1, 2])
        self.assertEqual(self.project_ids(), [1, 2])
        self.assertFalse(self.presenter.is_busy)


class BackgroundTests(PresenterTestCase):

    def test_editing_is_blocked_while_busy(self):
        self.assertTrue(self.presenter.calculate_workload())

        self.assertFalse(self.presenter.add_member("Марія", "Manager"))
        self.assertFalse(self.presenter.calculate_workload())
        self.assertIn("Зачекайте", self.view.errors[-1])
        self.assertEqual(len(self.service.members), 2)

        pump(self.presenter)

        self.assertTrue(self.presenter.add_member("Марія", "Manager"))

    def test_workload_result(self):
        self.presenter.calculate_workload()
        pump(self.presenter)

        self.assertEqual(self.view.workload, [
            {"member_id": 1, "name": "Олена", "hours": 13},
            {"member_id": 2, "name": "Іван", "hours": 4}
        ])

    def test_progress_messages_do_not_go_backwards(self):
        self.presenter.calculate_workload()
        pump(self.presenter)

        determinate = [(d, t) for d, t in self.view.progress if t is not None]
        done_values = [d for d, _ in determinate]

        self.assertEqual(self.view.progress[0], (0, None))
        self.assertEqual(done_values, sorted(done_values))
        self.assertEqual(determinate[-1][0], determinate[-1][1])

    def test_overdue_result(self):
        self.presenter.find_overdue()
        pump(self.presenter)

        found = {(r["project"], r["item_id"], r["days_overdue"])
                 for r in self.view.overdue}
        self.assertEqual(found, {
            ("Alpha", 1, 30), ("Alpha", 2, 61), ("Beta", 4, 21)
        })

    def test_foreign_operation_messages_are_ignored(self):
        self.tasks.start_workload()         

        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            self.presenter.process_messages()
            time.sleep(0.01)

        self.assertIsNone(self.view.workload)
        self.assertFalse(self.presenter.is_busy)

    def test_window_error_does_not_stop_message_processing(self):
        self.presenter.calculate_workload()
        self.view.fail_on_progress = True   

        pump(self.presenter)            

        self.assertFalse(self.presenter.is_busy)
        self.assertTrue(self.view.errors)
        self.assertIsNotNone(self.view.workload)


class FakeTasks:


    def __init__(self):
        self.queue = []
        self.next_id = 0
        self.shutdown_calls = 0
        self.poll_error = None

    def _start(self):
        self.next_id += 1
        return self.next_id

    def start_import(self, path):
        return self._start()

    def start_workload(self):
        return self._start()

    def start_overdue(self, today):
        return self._start()

    def poll(self):
        if self.poll_error:
            raise self.poll_error
        messages, self.queue = self.queue, []
        return messages

    def shutdown(self):
        self.shutdown_calls += 1


class MessageHandlingTests(PresenterTestCase):


    def setUp(self):
        super().setUp()
        self.fake = FakeTasks()
        self.view = FakeView()
        self.presenter = MainPresenter(
            self.service, self.fake, self.view, today_provider=lambda: TODAY
        )
        self.presenter.start()

    def send(self, kind, operation_id, data=None):
        self.fake.queue.append(Message(kind, operation_id, data))
        self.presenter.process_messages()

    def test_start_blocks_editing_and_shows_indeterminate_progress(self):
        self.presenter.calculate_workload()

        self.assertTrue(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states, [True])
        self.assertEqual(self.view.progress, [(0, None)])

    def test_progress_message_updates_progress_bar(self):
        self.presenter.calculate_workload()

        self.send(PROGRESS, 1, {"done": 2, "total": 5})

        self.assertEqual(self.view.progress[-1], (2, 5))
        self.assertTrue(self.presenter.is_busy)

    def test_workload_result_is_sorted_with_names(self):
        self.presenter.calculate_workload()

        self.send(RESULT, 1, {"workload": {2: 4, 1: 13, 99: 1}})

        self.assertEqual(self.view.workload, [
            {"member_id": 1, "name": "Олена", "hours": 13},
            {"member_id": 2, "name": "Іван", "hours": 4},
            {"member_id": 99, "name": "#99", "hours": 1}
        ])

    def test_overdue_result_is_shown_with_item_details(self):
        self.presenter.find_overdue()

        self.send(RESULT, 1, {"overdue": [
            {"project_id": 1, "item_id": 1, "days_overdue": 30},
            {"project_id": 9, "item_id": 999, "days_overdue": 5}  
        ]})

        self.assertEqual(self.view.overdue, [{
            "project": "Alpha", "item_id": 1, "title": "A1",
            "assignee": "Олена", "deadline": "2026-06-01",
            "days_overdue": 30
        }])

    def test_import_result_refreshes_and_reports(self):
        self.presenter.select_project(1)
        self.presenter.import_file("any.json")
        self.service.add_member("Нова", "Analyst") 

        self.send(RESULT, 1, {"members": 3, "projects": 2})

        self.assertIsNone(self.view.selected_id)
        self.assertEqual(self.view.items, [])
        self.assertEqual(len(self.view.members), 3)
        self.assertTrue(any("Імпортовано" in text for text in self.view.infos))

    def test_error_message_is_shown_and_keeps_busy_until_done(self):
        self.presenter.import_file("any.json")

        self.send(ERROR, 1, "Не вдалося прочитати файл")

        self.assertEqual(self.view.errors, ["Не вдалося прочитати файл"])
        self.assertTrue(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states, [True])

    def test_done_unblocks_and_stops_progress(self):
        self.presenter.calculate_workload()

        self.send(DONE, 1)

        self.assertFalse(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states, [True, False])
        self.assertEqual(self.view.progress_stopped, 1)
        self.assertTrue(self.presenter.add_member("Марія", "Manager"))

    def test_editing_is_blocked_until_done(self):
        self.presenter.calculate_workload()

        self.assertFalse(self.presenter.add_member("Марія", "Manager"))
        self.assertIn("Зачекайте", self.view.errors[-1])

        self.send(RESULT, 1, {"workload": {}})
        self.assertFalse(self.presenter.add_member("Марія", "Manager"))

        self.send(DONE, 1)
        self.assertTrue(self.presenter.add_member("Марія", "Manager"))

    def test_foreign_operation_ids_are_ignored(self):
        self.presenter.calculate_workload()      
        errors_before = list(self.view.errors)
        progress_before = list(self.view.progress)

        self.send(PROGRESS, 77, {"done": 1, "total": 2})
        self.send(RESULT, 77, {"workload": {1: 5}})
        self.send(ERROR, 77, "чужа помилка")
        self.send(DONE, 77)

        self.assertEqual(self.view.errors, errors_before)
        self.assertEqual(self.view.progress, progress_before)
        self.assertIsNone(self.view.workload)
        self.assertTrue(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states, [True])

    def test_messages_after_done_are_ignored(self):
        self.presenter.calculate_workload()
        self.send(DONE, 1)

        self.send(RESULT, 1, {"workload": {1: 5}})

        self.assertIsNone(self.view.workload)

    def test_bad_result_does_not_stop_later_messages(self):
        self.presenter.calculate_workload()

        self.fake.queue.extend([
            Message(RESULT, 1, {"unexpected": True}),  
            Message(DONE, 1, None)
        ])
        self.presenter.process_messages()

        self.assertTrue(self.view.errors)
        self.assertFalse(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states, [True, False])

    def test_poll_failure_does_not_raise(self):
        self.fake.poll_error = RuntimeError("черга зламалась")

        self.presenter.process_messages()   

        self.fake.poll_error = None
        self.presenter.calculate_workload()
        self.send(DONE, 1)
        self.assertFalse(self.presenter.is_busy)

    def test_start_failure_is_reported_and_does_not_block(self):
        def broken(*args):
            raise RuntimeError("пул закрито")
        self.fake.start_workload = broken

        self.assertFalse(self.presenter.calculate_workload())

        self.assertIn("пул закрито", self.view.errors[-1])
        self.assertFalse(self.presenter.is_busy)
        self.assertEqual(self.view.busy_states, [])

    def test_exports_are_blocked_while_busy(self):
        json_path = self.dir / "out.json"
        xml_path = self.dir / "report.xml"
        self.presenter.import_file("any.json")

        self.assertFalse(self.presenter.export_json(json_path))
        self.assertFalse(self.presenter.export_xml_report(xml_path))

        self.assertEqual(
            self.view.errors.count("Зачекайте завершення поточної операції."), 2
        )
        self.assertFalse(json_path.exists())
        self.assertFalse(xml_path.exists())

        self.send(DONE, 1)

        self.assertTrue(self.presenter.export_json(json_path))
        self.assertTrue(self.presenter.export_xml_report(xml_path))
        self.assertTrue(json_path.exists() and xml_path.exists())

    def test_startup_import_refreshes_without_info_window(self):
        self.presenter.select_project(1)
        self.presenter.import_file("any.json", announce=False)
        self.service.add_member("Нова", "Analyst")  

        self.send(RESULT, 1, {"members": 3, "projects": 2})

        self.assertEqual(self.view.infos, [])
        self.assertIsNone(self.view.selected_id)
        self.assertEqual(len(self.view.members), 3)

    def test_startup_import_error_is_still_shown(self):
        self.presenter.import_file("any.json", announce=False)

        self.send(ERROR, 1, "Не вдалося прочитати файл")
        self.send(DONE, 1)

        self.assertEqual(self.view.errors, ["Не вдалося прочитати файл"])
        self.assertFalse(self.presenter.is_busy)

    def test_regular_import_still_shows_info_window(self):
        self.presenter.import_file("any.json")

        self.send(RESULT, 1, {"members": 2, "projects": 2})

        self.assertEqual(len(self.view.infos), 1)

    def test_close_while_busy_shuts_down_tasks_after_confirmation(self):
        self.presenter.calculate_workload()
        self.view.answer = False

        self.assertFalse(self.presenter.on_close())
        self.assertEqual(self.fake.shutdown_calls, 0)

        self.view.answer = True
        self.assertTrue(self.presenter.on_close())
        self.assertEqual(self.fake.shutdown_calls, 1)
        self.assertTrue(self.view.closed)

    def test_unexpected_error_is_shown(self):
        self.presenter.show_unexpected_error(ValueError("щось пішло не так"))

        self.assertIn("щось пішло не так", self.view.errors[-1])


class CloseTests(PresenterTestCase):

    def test_close_when_idle(self):
        self.assertTrue(self.presenter.on_close())

        self.assertTrue(self.view.closed)
        self.assertEqual(self.view.confirms, [])

    def test_close_when_busy_asks_confirmation(self):
        self.presenter.calculate_workload()
        self.view.answer = False

        self.assertFalse(self.presenter.on_close())
        self.assertFalse(self.view.closed)

        self.view.answer = True
        self.assertTrue(self.presenter.on_close())
        self.assertTrue(self.view.closed)


if __name__ == "__main__":
    unittest.main()