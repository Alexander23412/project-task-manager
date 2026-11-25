# ШІ: Claude sonnet 5.5 – Перевірка коду
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from models.enums import Priority, Status
from repository.json_repository import JSONRepository
from tools.generate_data import generate, write_json

PROJECTS = 5
ITEMS = 12
MEMBERS = 6
SEED = 1

class GenerateDataTests(unittest.TestCase):

    def setUp(self):
        self.data = generate(PROJECTS, ITEMS, MEMBERS, SEED)

    def all_items(self, data=None):
        data = data or self.data
        return [i for p in data["projects"] for i in p["items"]]

    def test_sizes(self):
        self.assertEqual(len(self.data["members"]), MEMBERS)
        self.assertEqual(len(self.data["projects"]), PROJECTS)
        self.assertEqual(len(self.all_items()), PROJECTS * ITEMS)

    def test_same_seed_gives_same_data_and_other_seed_differs(self):
        self.assertEqual(self.data, generate(PROJECTS, ITEMS, MEMBERS, SEED))
        self.assertNotEqual(self.data, generate(PROJECTS, ITEMS, MEMBERS, 2))

    def test_ids_and_names_are_unique(self):
        item_ids = [i["id"] for i in self.all_items()]
        self.assertEqual(len(item_ids), len(set(item_ids)))

        project_names = [p["name"] for p in self.data["projects"]]
        self.assertEqual(len(project_names), len(set(project_names)))

        for project in self.data["projects"]:
            titles = [i["title"].casefold() for i in project["items"]]
            self.assertEqual(len(titles), len(set(titles)))

    def test_values_are_valid(self):
        member_ids = {m["id"] for m in self.data["members"]}
        statuses = {s.value for s in Status}
        priorities = {p.value for p in Priority}

        for project in self.data["projects"]:
            start, end = project["start"], project["end"]
            self.assertLess(start, end)

            for item in project["items"]:
                self.assertIn(item["assignee_id"], member_ids)
                self.assertIn(item["status"], statuses)
                self.assertIn(item["priority"], priorities)
                self.assertGreater(item["estimate_hours"], 0)
                self.assertTrue(start <= item["deadline"] <= end)
                date.fromisoformat(item["deadline"])  # формат YYYY-MM-DD

    def test_small_set_has_all_types_and_overdue_items(self):
        types = {i["type"] for i in self.all_items()}
        self.assertEqual(types, {"Task", "Bug", "Milestone"})

        overdue = [
            i for i in self.all_items()
            if i["deadline"] < "2026-06-01" and i["status"] != Status.DONE.value
        ]
        self.assertTrue(overdue)

    def test_generated_file_is_loaded_by_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "projects.json"
            write_json(path, self.data)

            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")), self.data
            )

            members, projects = JSONRepository.load(path)

        self.assertEqual(len(members), MEMBERS)
        self.assertEqual(len(projects), PROJECTS)
        self.assertEqual(sum(len(p.items) for p in projects), PROJECTS * ITEMS)

    def test_invalid_sizes_are_rejected(self):
        for args in ((0, 10, 5), (5, 0, 5), (5, 10, 0)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    generate(*args)

if __name__ == "__main__":
    unittest.main()