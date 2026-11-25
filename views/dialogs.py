# ШІ: Claude sonnet 5.5 – перевірка коду та написання class TableDialog
import tkinter as tk
from tkinter import ttk

from views.labels import (
    PRIORITY_LABELS, STATUS_LABELS, TYPE_LABELS,
    format_number, key_of, label_of, member_label
)


class BaseDialog(tk.Toplevel):


    def __init__(self, parent, title, on_submit):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)

        self._parent = parent
        self._on_submit = on_submit
        self._vars = {}
        self._first_widget = None
        self._row = 0

        self._form = ttk.Frame(self, padding=(12, 12, 12, 6))
        self._form.grid(row=0, column=0, sticky="nsew")
        self._form.columnconfigure(1, weight=1)

    def _add_entry(self, key, label, value=""):
        variable = tk.StringVar(master=self, value=value)
        self._vars[key] = variable

        ttk.Label(self._form, text=label).grid(
            row=self._row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        entry = ttk.Entry(self._form, textvariable=variable, width=34)
        entry.grid(row=self._row, column=1, sticky="ew", pady=3)

        self._remember_first(entry)
        self._row += 1
        return entry

    def _add_combobox(self, key, label, labels, selected="", state="readonly"):
        variable = tk.StringVar(master=self, value=selected)
        self._vars[key] = variable

        ttk.Label(self._form, text=label).grid(
            row=self._row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        combobox = ttk.Combobox(
            self._form, textvariable=variable, values=list(labels),
            state=state, width=31
        )
        combobox.grid(row=self._row, column=1, sticky="ew", pady=3)

        self._remember_first(combobox)
        self._row += 1
        return combobox

    def _remember_first(self, widget):
        if self._first_widget is None:
            self._first_widget = widget

    def _add_buttons(self, submit_text="Зберегти"):
        buttons = ttk.Frame(self, padding=(12, 6, 12, 12))
        buttons.grid(row=1, column=0, sticky="e")

        ttk.Button(buttons, text=submit_text, command=self._submit).grid(
            row=0, column=0, padx=(0, 6)
        )
        ttk.Button(buttons, text="Скасувати", command=self.destroy).grid(
            row=0, column=1
        )

        self.bind("<Return>", self._submit)
        self.bind("<Escape>", lambda event: self.destroy())

    def _collect(self):
        raise NotImplementedError

    def _submit(self, event=None):
        if self._on_submit(self._collect()):
            self.destroy()

    def show(self):

        self.update_idletasks()
        self._center_over_parent()
        self.wait_visibility()
        self.grab_set()

        if self._first_widget is not None:
            self._first_widget.focus_set()

        self.wait_window(self)

    def _center_over_parent(self):
        parent = self._parent
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_reqwidth()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_reqheight()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")


class ProjectDialog(BaseDialog):


    def __init__(self, parent, on_submit, initial=None):
        initial = initial or {}
        super().__init__(
            parent,
            "Редагування проєкту" if initial else "Новий проєкт",
            on_submit
        )

        self._add_entry("name", "Назва:", initial.get("name", ""))
        self._add_entry("start", "Початок (YYYY-MM-DD):", initial.get("start", ""))
        self._add_entry("end", "Завершення (YYYY-MM-DD):", initial.get("end", ""))
        self._add_buttons()

    def _collect(self):
        return {key: self._vars[key].get() for key in ("name", "start", "end")}


class MemberDialog(BaseDialog):


    def __init__(self, parent, on_submit, initial=None):
        initial = initial or {}
        super().__init__(
            parent,
            "Редагування учасника" if initial else "Новий учасник",
            on_submit
        )

        self._add_entry("name", "Ім'я:", initial.get("name", ""))
        self._add_entry("role", "Роль:", initial.get("role", ""))
        self._add_buttons()

    def _collect(self):
        return {key: self._vars[key].get() for key in ("name", "role")}


class ItemDialog(BaseDialog):


    def __init__(self, parent, on_submit, members, initial=None):
        editing = bool(initial)
        initial = initial or {}
        super().__init__(
            parent,
            "Редагування завдання" if editing else "Нове завдання",
            on_submit
        )

        self._assignees = {member_label(row): row["id"] for row in members}
        selected_assignee = next(
            (label for label, member_id in self._assignees.items()
             if member_id == initial.get("assignee_id")),
            ""
        )

        hours = initial.get("estimate_hours")

        self._add_entry("title", "Назва:", initial.get("title", ""))
        self._add_combobox(
            "type", "Тип:", TYPE_LABELS.values(),
            label_of(TYPE_LABELS, initial.get("type", "Task")),
            state="disabled" if editing else "readonly"
        )
        self._add_combobox(
            "assignee", "Виконавець:", self._assignees, selected_assignee
        )
        self._add_combobox(
            "priority", "Пріоритет:", PRIORITY_LABELS.values(),
            label_of(PRIORITY_LABELS, initial.get("priority", "medium"))
        )
        self._add_combobox(
            "status", "Статус:", STATUS_LABELS.values(),
            label_of(STATUS_LABELS, initial.get("status", "todo"))
        )
        self._add_entry(
            "deadline", "Дедлайн (YYYY-MM-DD):", initial.get("deadline", "")
        )
        self._add_entry(
            "estimate_hours", "Оцінка, год:",
            "" if hours is None else format_number(hours)
        )
        self._add_buttons()

    def _collect(self):
        get = lambda key: self._vars[key].get()

        return {
            "title": get("title"),
            "item_type": key_of(TYPE_LABELS, get("type")),
            "assignee_id": self._assignees.get(get("assignee")),
            "priority": key_of(PRIORITY_LABELS, get("priority")),
            "status": key_of(STATUS_LABELS, get("status")),
            "deadline": get("deadline"),
            "estimate_hours": get("estimate_hours")
        }


class TableDialog(tk.Toplevel):

    def __init__(self, parent, title, columns, rows):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.geometry("720x380")

        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        keys = [column[0] for column in columns]
        tree = ttk.Treeview(frame, columns=keys, show="headings")

        for key, heading, width, anchor in columns:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor=anchor)

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        for row in rows:
            tree.insert("", "end", values=[
                format_number(row[key]) if isinstance(row[key], float)
                else row[key]
                for key in keys
            ])

        ttk.Button(frame, text="Закрити", command=self.destroy).grid(
            row=1, column=0, columnspan=2, sticky="e", pady=(8, 0)
        )
        self.bind("<Escape>", lambda event: self.destroy())