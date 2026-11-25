# ШІ: Claude sonnet 5.5 – чернетка unittest-тестів для JSONRepository.load і save.
# Змінено: class LoadUniquenessTests
import json
import logging
import tempfile
import unittest
from functools import reduce
from pathlib import Path
from types import SimpleNamespace

from models.enums import Priority, Status
from models.bug import Bug
from models.milestone import Milestone
from models.task import Task
from repository.json_repository import DataFormatError, JSONRepository

STATUS = Status.TODO.value
PRIORITY = Priority.LOW.value


def setUpModule():
   
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


def make_data():
    

    def item(item_id, title, item_type, assignee_id):
        return {
            "id": item_id,
            "title": title,
            "type": item_type,
            "assignee_id": assignee_id,
            "priority": PRIORITY,
            "status": STATUS,
            "deadline": "2026-06-01",
            "estimate_hours": 8
        }

    return {
        "members": [
            {"id": 1, "name": "Олена", "role": "Developer"},
            {"id": 2, "name": "Іван", "role": "Tester"},
            {"id": 3, "name": "Марія", "role": "Manager"}
        ],
        "projects": [
            {
                "id": 1,
                "name": "Alpha",
                "start": "2026-01-01",
                "end": "2026-12-31",
                "items": [
                    item(1, "Task A1", "Task", 1),
                    item(2, "Bug A2", "Bug", 2),
                    item(3, "Milestone A3", "Milestone", 3)
                ]
            },
            {
                "id": 2,
                "name": "Beta",
                "start": "2026-02-01",
                "end": "2026-11-30",
                "items": [
                    item(4, "Task B1", "Task", 2),
                    item(5, "Bug B2", "Bug", 1)
                ]
            }
        ]
    }


def _get(data, path):
    return reduce(lambda node, key: node[key], path, data)


def setter(path, value):
    def mutate(data):
        _get(data, path[:-1])[path[-1]] = value
    return mutate


def copier(source_path, target_path):
    def mutate(data):
        _get(data, target_path[:-1])[target_path[-1]] = _get(
            data, source_path
        )
    return mutate


def deleter(path):
    def mutate(data):
        del _get(data, path[:-1])[path[-1]]
    return mutate


ITEM0 = ("projects", 0, "items", 0)


class RepositoryTestCase(unittest.TestCase):

    
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def write_json(self, data, name="projects.json"):
        path = self.dir / name
        path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        return path

    def write_text(self, text, name="projects.json"):
        path = self.dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def assert_rejected(self, data):
        with self.assertRaises(DataFormatError):
            JSONRepository.load(self.write_json(data))

    def run_cases(self, cases):
        for name, mutate in cases:
            with self.subTest(case=name):
                data = make_data()
                mutate(data)
                self.assert_rejected(data)


class LoadValidDataTests(RepositoryTestCase):

    def test_loads_all_projects_and_items(self):
        members, projects = JSONRepository.load(
            self.write_json(make_data())
        )

        self.assertEqual(len(members), 3)
        self.assertEqual(len(projects), 2)
        self.assertEqual([len(p.items) for p in projects], [3, 2])

    def test_item_types_are_correct(self):
        _, projects = JSONRepository.load(self.write_json(make_data()))

        first_items = projects[0].items
        self.assertIsInstance(first_items[0], Task)
        self.assertIsInstance(first_items[1], Bug)
        self.assertIsInstance(first_items[2], Milestone)

    def test_empty_projects_returns_empty_list(self):
        data = make_data()
        data["projects"] = []

        result = JSONRepository.load(self.write_json(data))

        self.assertIsNotNone(result)
        members, projects = result
        self.assertEqual(len(members), 3)
        self.assertEqual(projects, [])


class LoadBrokenFileTests(RepositoryTestCase):

    def test_truncated_json(self):
        text = json.dumps(make_data())[:-1]
        with self.assertRaises(DataFormatError):
            JSONRepository.load(self.write_text(text))

    def test_empty_file(self):
        with self.assertRaises(DataFormatError):
            JSONRepository.load(self.write_text(""))

    def test_missing_file(self):
        with self.assertRaises(DataFormatError):
            JSONRepository.load(self.dir / "does_not_exist.json")

    def test_root_is_not_object(self):
        with self.assertRaises(DataFormatError):
            JSONRepository.load(self.write_text("[]"))


class LoadStructureTests(RepositoryTestCase):

    def test_missing_keys(self):
        self.run_cases([
            ("немає members", deleter(("members",))),
            ("немає projects", deleter(("projects",))),
            ("у проєкті немає name", deleter(("projects", 0, "name"))),
            ("у проєкті немає items", deleter(("projects", 0, "items")))
        ])

    def test_items_is_not_list(self):
        self.run_cases([
            ("items – об'єкт", setter(("projects", 0, "items"), {})),
            ("items – рядок", setter(("projects", 0, "items"), "abc"))
        ])

    def test_error_message_points_to_location(self):
        data = make_data()
        setter(("projects", 0, "items", 0, "type"), "Epic")(data)

        with self.assertRaisesRegex(
            DataFormatError, "проєкті №1, елементі №1"
        ):
            JSONRepository.load(self.write_json(data))


class LoadValueTests(RepositoryTestCase):

    def test_unknown_enum_values(self):
        self.run_cases([
            ("невідомий type", setter(ITEM0 + ("type",), "Epic")),
            ("невідомий status", setter(ITEM0 + ("status",), "nope")),
            ("невідомий priority", setter(ITEM0 + ("priority",), "nope"))
        ])

    def test_status_and_priority_are_case_sensitive(self):
        
        self.run_cases([
            ("status в іншому регістрі", setter(
                ITEM0 + ("status",), STATUS.swapcase()
            )),
            ("priority в іншому регістрі", setter(
                ITEM0 + ("priority",), PRIORITY.swapcase()
            ))
        ])

    def test_unknown_assignee(self):
        self.run_cases([
            ("виконавця немає", setter(ITEM0 + ("assignee_id",), 999)),
            ("виконавець 0", setter(ITEM0 + ("assignee_id",), 0)),
            ("виконавець рядок", setter(ITEM0 + ("assignee_id",), "1"))
        ])

    def test_invalid_dates(self):
        self.run_cases([
            ("дедлайн 2026-13-45", setter(ITEM0 + ("deadline",), "2026-13-45")),
            ("дедлайн 01.02.2026", setter(ITEM0 + ("deadline",), "01.02.2026")),
            ("start 2026-13-45", setter(("projects", 0, "start"), "2026-13-45")),
            ("end 01.02.2026", setter(("projects", 0, "end"), "01.02.2026"))
        ])

    def test_invalid_estimate_hours(self):
        self.run_cases([
            ("estimate_hours = 0", setter(ITEM0 + ("estimate_hours",), 0)),
            ("estimate_hours < 0", setter(ITEM0 + ("estimate_hours",), -5)),
            ("estimate_hours рядок", setter(ITEM0 + ("estimate_hours",), "8"))
        ])

    def test_empty_strings(self):
        self.run_cases([
            ("порожній title", setter(ITEM0 + ("title",), "")),
            ("порожнє name учасника", setter(("members", 0, "name"), ""))
        ])

    def test_deadline_outside_project(self):
        self.run_cases([
            ("дедлайн після end", setter(ITEM0 + ("deadline",), "2099-01-01")),
            ("дедлайн до start", setter(ITEM0 + ("deadline",), "2000-01-01"))
        ])


class LoadUniquenessTests(RepositoryTestCase):

    def test_duplicate_ids(self):
        self.run_cases([
            ("ID учасника", copier(
                ("members", 0, "id"), ("members", 1, "id")
            )),
            ("ID проєкту", copier(
                ("projects", 0, "id"), ("projects", 1, "id")
            )),
            ("ID завдання між проєктами", copier(
                ITEM0 + ("id",), ("projects", 1, "items", 0, "id")
            ))
        ])

    def test_duplicate_names(self):
        self.run_cases([
            ("назва проєкту", copier(
                ("projects", 0, "name"), ("projects", 1, "name")
            )),
            ("назва проєкту в іншому регістрі", setter(
                ("projects", 1, "name"), "ALPHA"
            )),
            ("назва завдання в проєкті", copier(
                ITEM0 + ("title",), ("projects", 0, "items", 1, "title")
            ))
        ])


class SaveTests(RepositoryTestCase):

    def test_save_then_load_gives_same_data(self):
        original = make_data()
        members, projects = JSONRepository.load(self.write_json(original))

        saved_path = self.dir / "saved.json"
        JSONRepository.save(saved_path, members, projects)

        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertEqual(saved, original)

        members2, projects2 = JSONRepository.load(saved_path)
        self.assertEqual(len(members2), len(members))
        self.assertEqual(len(projects2), len(projects))

        again_path = self.dir / "saved_again.json"
        JSONRepository.save(again_path, members2, projects2)
        again = json.loads(again_path.read_text(encoding="utf-8"))
        self.assertEqual(again, original)

    def test_save_leaves_no_temp_files(self):
        members, projects = JSONRepository.load(
            self.write_json(make_data())
        )
        JSONRepository.save(self.dir / "out.json", members, projects)

        self.assertEqual(list(self.dir.glob("*.tmp")), [])

    def test_save_to_missing_folder_raises(self):
        members, projects = JSONRepository.load(
            self.write_json(make_data())
        )
        target = self.dir / "no_such_folder" / "out.json"

        with self.assertRaises(DataFormatError):
            JSONRepository.save(target, members, projects)

    def test_failed_save_keeps_existing_file(self):
        target = self.write_text("СТАРИЙ ВМІСТ", name="existing.json")
        
        broken_member = SimpleNamespace(id=1, name=object(), role="Dev")

        with self.assertRaises(DataFormatError):
            JSONRepository.save(target, [broken_member], [])

        self.assertEqual(
            target.read_text(encoding="utf-8"), "СТАРИЙ ВМІСТ"
        )
        self.assertEqual(list(self.dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()