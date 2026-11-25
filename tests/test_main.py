# ШІ: Claude sonnet 5.5 – Перевірка коду 
import logging
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter  
except ImportError:                     
    tkinter = None

if tkinter is not None:
    import main
from tests.test_main_presenter import FakeView
from tools.generate_data import generate, write_json


def setUpModule():
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeWindow(FakeView):


    last = None

    def __init__(self):
        super().__init__()
        self.presenter = None
        self.report_callback_exception = None
        FakeWindow.last = self

    def attach(self, presenter):
        self.presenter = presenter

    def mainloop(self):

        deadline = time.monotonic() + 10

        while self.presenter.is_busy:
            self.assertion_guard(time.monotonic() < deadline)
            self.presenter.process_messages()
            time.sleep(0.005)

        self.presenter.process_messages()

    @staticmethod
    def assertion_guard(condition):
        if not condition:
            raise AssertionError("Стартове завантаження не завершилось.")


@unittest.skipIf(tkinter is None, "Tkinter не встановлено")
class MainTestCase(unittest.TestCase):

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

        for patcher in (
            mock.patch.object(main, "MainWindow", FakeWindow),
            mock.patch.object(main, "setup_logging")
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.data_path = self.dir / "projects.json"
        write_json(self.data_path, generate(3, 5, 4, seed=7))

    def run_main(self, *args):
        main.main(list(args))
        return FakeWindow.last


class CreateAppTests(MainTestCase):

    def test_components_are_wired_together(self):
        service, tasks, window, presenter = main.create_app()
        self.addCleanup(tasks.shutdown)

        self.assertIs(window.presenter, presenter)
        self.assertTrue(callable(window.report_callback_exception))

    def test_unhandled_callback_exception_is_shown_not_raised(self):
        _service, tasks, window, _presenter = main.create_app()
        self.addCleanup(tasks.shutdown)

        try:
            raise RuntimeError("збій обробника кнопки")
        except RuntimeError as error:
            window.report_callback_exception(
                type(error), error, error.__traceback__
            )

        self.assertEqual(len(window.errors), 1)
        self.assertIn("збій обробника кнопки", window.errors[0])


class StartupTests(MainTestCase):

    def test_data_file_is_loaded_in_background_without_info_window(self):
        window = self.run_main("--file", str(self.data_path))

        self.assertEqual([p["id"] for p in window.projects], [1, 2, 3])
        self.assertEqual(len(window.members), 4)
        self.assertEqual(window.infos, [])
        self.assertEqual(window.errors, [])

    def test_empty_flag_skips_loading(self):
        window = self.run_main("--file", str(self.data_path), "--empty")

        self.assertEqual(window.projects, [])
        self.assertEqual(window.members, [])

    def test_missing_file_is_skipped_silently(self):
        window = self.run_main("--file", str(self.dir / "немає.json"))

        self.assertEqual(window.projects, [])
        self.assertEqual(window.errors, [])

    def test_corrupted_file_shows_error_and_keeps_empty_data(self):
        broken = self.dir / "broken.json"
        broken.write_text('{"members": [', encoding="utf-8")

        window = self.run_main("--file", str(broken))

        self.assertEqual(window.projects, [])
        self.assertEqual(len(window.errors), 1)


@unittest.skipIf(tkinter is None, "Tkinter не встановлено")
class ArgumentTests(unittest.TestCase):

    def test_defaults(self):
        args = main.parse_args([])

        self.assertEqual(args.file, main.DEFAULT_DATA_PATH)
        self.assertFalse(args.empty)


if __name__ == "__main__":
    unittest.main()