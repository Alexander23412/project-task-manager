# ШІ: Claude sonnet 5.5 – чернетка unittest-тестів для BackgroundTasks.
# Змінено: class BackgroundTestCase
import logging
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from models.enums import Priority, Status
from services import background_tasks
from services.background_tasks import (
    DONE, ERROR, PROGRESS, RESULT, BackgroundTasks
)
from services.project_service import ProjectService

START = date(2026, 1, 1)
END = date(2026, 12, 31)
TODAY = date(2026, 7, 1)

PROJECTS = 4
ITEMS_PER_PROJECT = 30
CHUNK_SIZE = 20          


def setUpModule():

    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def build_service(project_count=PROJECTS, items_per_project=ITEMS_PER_PROJECT):
    service = ProjectService()
    members = [service.add_member(f"Учасник {n}", "Dev") for n in range(3)]
    statuses = list(Status)
    priorities = list(Priority)

    for p in range(project_count):
        project = service.add_project(f"Проєкт {p}", START, END)

        for i in range(items_per_project):
            service.add_item(
                project, "Task", f"Завдання {p}-{i}",
                members[i % 3], priorities[i % 3], statuses[i % 3],
                date(2026, 1 + i % 12, 1 + i % 28),
                1 + i % 5
            )

    return service


def summary(service):
    return (
        [m.id for m in service.members],
        [(p.id, [i.id for i in p.items]) for p in service.projects]
    )


def collect(tasks, operation_id, timeout=10.0):

    deadline = time.monotonic() + timeout
    messages = []

    while time.monotonic() < deadline:
        for message in tasks.poll():
            if message.operation_id == operation_id:
                messages.append(message)

        if messages and messages[-1].kind == DONE:
            return messages

        time.sleep(0.005)

    raise AssertionError("Операція не завершилась вчасно.")


def kinds(messages):
    return [m.kind for m in messages]


class BackgroundTestCase(unittest.TestCase):

    def make_tasks(self, service, workers=4, chunk_size=CHUNK_SIZE):
        tasks = BackgroundTasks(
            service, max_workers=workers, chunk_size=chunk_size
        )
        self.addCleanup(tasks.shutdown)
        return tasks


class ImportTests(BackgroundTestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_valid_file_finishes_with_done_and_replaces_data(self):
        source = build_service()
        path = self.dir / "data.json"
        source.save_file(path)

        target = ProjectService()
        tasks = self.make_tasks(target)

        operation_id = tasks.start_import(path)
        messages = collect(tasks, operation_id)

        self.assertEqual(messages[-1].kind, DONE)
        self.assertIn(RESULT, kinds(messages))
        self.assertNotIn(ERROR, kinds(messages))

        result = next(m for m in messages if m.kind == RESULT)
        self.assertEqual(result.data, {"members": 3, "projects": PROJECTS})
        self.assertEqual(summary(target), summary(source))
        self.assertFalse(tasks.is_busy)

    def test_corrupted_file_gives_error_and_keeps_data(self):
        target = build_service(project_count=1, items_per_project=5)
        before = summary(target)
        path = self.dir / "broken.json"
        path.write_text('{"members": [', encoding="utf-8")
        tasks = self.make_tasks(target)

        operation_id = tasks.start_import(path)
        messages = collect(tasks, operation_id)

        self.assertIn(ERROR, kinds(messages))
        self.assertNotIn(RESULT, kinds(messages))
        self.assertEqual(messages[-1].kind, DONE)

        error = next(m for m in messages if m.kind == ERROR)
        self.assertTrue(error.data)
        self.assertEqual(summary(target), before)


class WorkloadTests(BackgroundTestCase):

    @staticmethod
    def expected_workload(service):
        totals = {}

        for project in service.projects:
            for item in project.items:
                if item.status != Status.DONE:
                    member_id = item.assignee.id
                    totals[member_id] = (
                        totals.get(member_id, 0) + item.estimate_hours
                    )

        return totals

    def test_pool_result_matches_plain_loop(self):
        service = build_service()
        expected = self.expected_workload(service)
        self.assertTrue(expected)

        for workers in (1, 4):
            with self.subTest(workers=workers):
                tasks = self.make_tasks(service, workers=workers)
                operation_id = tasks.start_workload()
                messages = collect(tasks, operation_id)

                result = next(m for m in messages if m.kind == RESULT)
                self.assertEqual(result.data["workload"], expected)

    def test_progress_grows_and_ends_with_total(self):
        service = build_service()
        total_items = PROJECTS * ITEMS_PER_PROJECT
        expected_chunks = -(-total_items // CHUNK_SIZE)

        for workers in (1, 4):
            with self.subTest(workers=workers):
                tasks = self.make_tasks(service, workers=workers)
                operation_id = tasks.start_workload()
                messages = collect(tasks, operation_id)

                progress = [m.data for m in messages if m.kind == PROGRESS]
                done_values = [p["done"] for p in progress]

                self.assertEqual(
                    done_values, list(range(expected_chunks + 1))
                )
                self.assertTrue(
                    all(p["total"] == expected_chunks for p in progress)
                )
                self.assertEqual(progress[-1]["done"], progress[-1]["total"])

    def test_empty_service_gives_empty_result(self):
        tasks = self.make_tasks(ProjectService())

        operation_id = tasks.start_workload()
        messages = collect(tasks, operation_id)

        result = next(m for m in messages if m.kind == RESULT)
        self.assertEqual(result.data["workload"], {})
        self.assertEqual(messages[-1].kind, DONE)


class OverdueTests(BackgroundTestCase):

    def test_result_matches_project_overdue_items(self):
        service = build_service()
        expected = {
            (project.id, item.id)
            for project in service.projects
            for item in project.overdue_items(TODAY)
        }
        self.assertTrue(expected)

        for workers in (1, 4):
            with self.subTest(workers=workers):
                tasks = self.make_tasks(service, workers=workers)
                operation_id = tasks.start_overdue(TODAY)
                messages = collect(tasks, operation_id)

                result = next(m for m in messages if m.kind == RESULT)
                found = [
                    (e["project_id"], e["item_id"])
                    for e in result.data["overdue"]
                ]

                self.assertEqual(len(found), len(set(found)))
                self.assertEqual(set(found), expected)

    def test_days_overdue_are_correct(self):
        service = build_service()
        deadlines = {
            item.id: item.deadline
            for _project, item in service.snapshot_items()
        }
        tasks = self.make_tasks(service)

        operation_id = tasks.start_overdue(TODAY)
        messages = collect(tasks, operation_id)

        result = next(m for m in messages if m.kind == RESULT)
        for entry in result.data["overdue"]:
            expected_days = (TODAY - deadlines[entry["item_id"]]).days
            self.assertEqual(entry["days_overdue"], expected_days)


class SafetyTests(BackgroundTestCase):

    def test_error_inside_chunk_is_reported_not_lost(self):
        service = build_service()
        tasks = self.make_tasks(service)

        with mock.patch.object(
            background_tasks, "_workload_chunk",
            side_effect=RuntimeError("boom")
        ):
            operation_id = tasks.start_workload()
            messages = collect(tasks, operation_id)

        self.assertIn(ERROR, kinds(messages))
        self.assertNotIn(RESULT, kinds(messages))
        self.assertEqual(messages[-1].kind, DONE)

        error = next(m for m in messages if m.kind == ERROR)
        self.assertIn("boom", error.data)
        self.assertFalse(tasks.is_busy)

    def test_operation_ids_are_unique_and_messages_do_not_mix(self):
        service = build_service()
        tasks = self.make_tasks(service)

        first = tasks.start_workload()
        second = tasks.start_overdue(TODAY)
        self.assertNotEqual(first, second)

        deadline = time.monotonic() + 10
        finished = set()
        by_operation = {first: [], second: []}

        while len(finished) < 2 and time.monotonic() < deadline:
            for message in tasks.poll():
                by_operation[message.operation_id].append(message)
                if message.kind == DONE:
                    finished.add(message.operation_id)
            time.sleep(0.005)

        self.assertEqual(finished, {first, second})

        first_result = next(
            m for m in by_operation[first] if m.kind == RESULT
        )
        second_result = next(
            m for m in by_operation[second] if m.kind == RESULT
        )
        self.assertIn("workload", first_result.data)
        self.assertIn("overdue", second_result.data)

    def test_shutdown_does_not_hang(self):
        service = build_service()
        tasks = BackgroundTasks(service, max_workers=2, chunk_size=5)
        operation_id = tasks.start_workload()

        started = time.monotonic()
        tasks.shutdown()
        tasks.shutdown()          
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 2.0)

        messages = collect(tasks, operation_id)
        self.assertEqual(messages[-1].kind, DONE)
        self.assertFalse(tasks.is_busy)

    def test_get_message_waits_for_message_or_times_out(self):
        tasks = self.make_tasks(ProjectService())

        self.assertIsNone(tasks.get_message(timeout=0.05))

        operation_id = tasks.start_workload()
        message = tasks.get_message(timeout=5)

        self.assertIsNotNone(message)
        self.assertEqual(message.operation_id, operation_id)

    def test_invalid_parameters_are_rejected(self):
        service = ProjectService()

        for kwargs in ({"max_workers": 0}, {"chunk_size": 0},
                       {"max_workers": "4"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    BackgroundTasks(service, **kwargs)


if __name__ == "__main__":
    unittest.main()


class LoggingTests(BackgroundTestCase):


    def setUp(self):

        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable, logging.CRITICAL)

    def test_workload_logs_start_chunks_and_finish(self):
        tasks = self.make_tasks(build_service())

        with self.assertLogs("services.background_tasks", "INFO") as logs:
            operation_id = tasks.start_workload()
            collect(tasks, operation_id)

        text = "\n".join(logs.output)
        self.assertIn(f"№{operation_id}", text)
        self.assertIn("запущено", text)
        self.assertIn("частин", text)
        self.assertIn("завершено успішно за", text)