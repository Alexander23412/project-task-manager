# ШІ: Claude sonnet 5.5 – чернетка unittest-тестів для views (підписи, MainWindow, діалоги).
# Змінено: class ViewContractTests
import inspect
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from models.enums import Priority, Status
from repository.json_repository import JSONRepository
from services.project_service import ProjectService
from tools.generate_data import generate, write_json
from views.labels import (
    PRIORITY_LABELS, STATUS_LABELS, TYPE_LABELS,
    format_number, key_of, label_of, member_label
)

try:
    import tkinter as tk
except ImportError:              
    tk = None

if tk is not None:
    import main
    from presenters.main_presenter import MainView
    from views import dialogs
    from views.main_window import MainWindow


class LabelsTests(unittest.TestCase):


    CASES = (
        ("статус", STATUS_LABELS, [s.value for s in Status]),
        ("пріоритет", PRIORITY_LABELS, [p.value for p in Priority]),
        ("тип", TYPE_LABELS, list(ProjectService.ITEM_TYPES))
    )

    def test_every_value_has_exactly_one_label(self):
        for name, labels, keys in self.CASES:
            with self.subTest(name):
                self.assertEqual(set(labels), set(keys))

    def test_labels_are_not_empty_and_unique(self):
        for name, labels, _keys in self.CASES:
            with self.subTest(name):
                values = list(labels.values())
                self.assertTrue(all(v.strip() for v in values))
                self.assertEqual(len(values), len(set(values)))

    def test_label_of_and_key_of_are_inverse(self):
        for name, labels, keys in self.CASES:
            for key in keys:
                with self.subTest(name, key=key):
                    self.assertEqual(key_of(labels, label_of(labels, key)), key)

            for label in labels.values():
                with self.subTest(name, label=label):
                    self.assertEqual(label_of(labels, key_of(labels, label)), label)

    def test_unknown_values_are_handled(self):
        self.assertEqual(label_of(STATUS_LABELS, "нове"), "нове")
        self.assertIsNone(key_of(STATUS_LABELS, "Усі"))
        self.assertIsNone(key_of(STATUS_LABELS, ""))

    def test_item_type_registries_agree(self):

        self.assertEqual(
            set(JSONRepository.ITEM_TYPES), set(ProjectService.ITEM_TYPES)
        )

    def test_number_and_member_formatting(self):
        self.assertEqual(format_number(5), "5")
        self.assertEqual(format_number(8.0), "8")
        self.assertEqual(format_number(2.5), "2.5")
        self.assertEqual(
            member_label({"id": 3, "name": "Марія"}), "Марія (№3)"
        )


@unittest.skipIf(tk is None, "Tkinter не встановлено")
class ViewContractTests(unittest.TestCase):


    def test_window_implements_every_view_method(self):
        required = [
            name for name, value in vars(MainView).items()
            if not name.startswith("_") and callable(value)
        ]

        self.assertTrue(required)

        for name in required:
            with self.subTest(method=name):
                method = getattr(MainWindow, name, None)
                self.assertTrue(callable(method), f"немає методу {name}")
                self.assertEqual(
                    list(inspect.signature(method).parameters),
                    list(inspect.signature(getattr(MainView, name)).parameters),
                    f"інша сигнатура {name}"
                )


@unittest.skipIf(tk is None, "Tkinter не встановлено")
class WindowSmokeTests(unittest.TestCase):


    def setUp(self):
        patcher = mock.patch("views.main_window.messagebox")
        self.messagebox = patcher.start()
        self.addCleanup(patcher.stop)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    @staticmethod
    def _destroy(window):
        try:
            window.destroy()
        except tk.TclError:
            pass

    def open_window(self):
        try:
            window = MainWindow()
        except tk.TclError as error:
            self.skipTest(f"Немає дисплея: {error}")

        window.withdraw()
        self.addCleanup(self._destroy, window)
        return window

    def test_window_opens_updates_and_closes(self):
        window = self.open_window()

        window.update()
        window.destroy()

    def test_dialogs_build_and_collect_default_values(self):
        window = self.open_window()
        members = [
            {"id": 1, "name": "Олена", "role": "Developer"},
            {"id": 2, "name": "Іван", "role": "Tester"}
        ]

        project = dialogs.ProjectDialog(window, lambda values: True)
        member = dialogs.MemberDialog(window, lambda values: True)
        item = dialogs.ItemDialog(window, lambda values: True, members)
        table = dialogs.TableDialog(
            window, "Таблиця", [("name", "Ім'я", 100, "w")],
            [{"name": "Олена"}]
        )
        window.update()

        self.assertEqual(
            project._collect(), {"name": "", "start": "", "end": ""}
        )
        self.assertEqual(member._collect(), {"name": "", "role": ""})
        self.assertEqual(item._collect(), {
            "title": "", "item_type": "Task", "assignee_id": None,
            "priority": "medium", "status": "todo",
            "deadline": "", "estimate_hours": ""
        })

        for dialog in (project, member, item, table):
            dialog.destroy()

    def test_item_dialog_is_filled_from_row_and_maps_labels_back(self):
        window = self.open_window()
        members = [
            {"id": 1, "name": "Олена", "role": "Developer"},
            {"id": 2, "name": "Іван", "role": "Tester"}
        ]
        row = {
            "id": 5, "title": "Баг", "type": "Bug", "assignee_id": 2,
            "priority": "high", "status": "done", "deadline": "2026-06-01",
            "estimate_hours": 2.5
        }

        dialog = dialogs.ItemDialog(
            window, lambda values: True, members, initial=row
        )
        window.update()

        self.assertEqual(dialog._collect(), {
            "title": "Баг", "item_type": "Bug", "assignee_id": 2,
            "priority": "high", "status": "done",
            "deadline": "2026-06-01", "estimate_hours": "2.5"
        })
        dialog.destroy()

    def test_dialog_closes_only_after_successful_submit(self):
        window = self.open_window()
        answers = iter([False, True])
        received = []

        def on_submit(values):
            received.append(values)
            return next(answers)

        dialog = dialogs.MemberDialog(window, on_submit)
        dialog._vars["name"].set("Олена")
        dialog._vars["role"].set("Developer")
        window.update()

        dialog._submit()
        self.assertTrue(dialog.winfo_exists(), "при помилці діалог лишається")
        self.assertEqual(dialog._vars["name"].get(), "Олена")

        dialog._submit()
        self.assertFalse(dialog.winfo_exists(), "після успіху діалог закрито")
        self.assertEqual(len(received), 2)

    def test_app_wiring_and_background_import(self):
        try:
            service, tasks, window, presenter = main.create_app()
        except tk.TclError as error:
            self.skipTest(f"Немає дисплея: {error}")

        self.addCleanup(tasks.shutdown)
        self.addCleanup(self._destroy, window)
        window.withdraw()

        path = self.dir / "projects.json"
        write_json(path, generate(3, 5, 4, seed=7))

        presenter.start()
        presenter.import_file(path, announce=False)

        deadline = time.monotonic() + 10
        while presenter.is_busy:
            self.assertLess(time.monotonic(), deadline, "імпорт не завершився")
            window.update()
            presenter.process_messages()
            time.sleep(0.01)

        window.update()
        presenter.process_messages()

        self.assertEqual(window._projects_tree.get_children(), ("1", "2", "3"))
        self.assertEqual(len(window._members_tree.get_children()), 4)
        self.messagebox.showerror.assert_not_called()
        self.messagebox.showinfo.assert_not_called()


if __name__ == "__main__":
    unittest.main()