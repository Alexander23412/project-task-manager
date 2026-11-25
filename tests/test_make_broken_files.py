# ШІ: Claude sonnet 5.5 – Перевірка коду та структура коду
import contextlib
import io
import logging
import tempfile
import unittest
from pathlib import Path

from repository.json_repository import DataFormatError, JSONRepository
from tools.generate_data import generate, write_json
from tools.make_broken_files import CASES, build_files, main


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class BrokenFilesTests(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_valid_base_data_loads(self):

        path = self.dir / "valid.json"
        write_json(path, generate(projects=3, items_per_project=4,
                                  members=3, seed=1))

        members, projects = JSONRepository.load(path)

        self.assertEqual((len(members), len(projects)), (3, 3))

    def test_every_broken_file_is_rejected_by_import(self):
        with contextlib.redirect_stdout(io.StringIO()):
            main(["--output", str(self.dir)])

        for name, description, _how in CASES:
            with self.subTest(file=name, problem=description):
                with self.assertRaises(DataFormatError):
                    JSONRepository.load(self.dir / name)

    def test_file_set_is_complete_and_names_are_unique(self):
        files = build_files()

        self.assertEqual(len(files), len(CASES))
        self.assertEqual(len(set(files)), len(files))
        self.assertTrue(all(description for description, _ in files.values()))


if __name__ == "__main__":
    unittest.main()