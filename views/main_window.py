# ШІ: Claude sonnet 5.5 – чернетка MainWindow (головне вікно Tkinter для MainPresenter).
# Змінено:  PROJECT_COLUMNS, ITEM_COLUMNS змінені назви 
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from views.dialogs import ItemDialog, MemberDialog, ProjectDialog, TableDialog
from views.labels import (
    PRIORITY_LABELS, STATUS_LABELS, TYPE_LABELS,
    format_number, key_of, label_of, member_label
)


POLL_MS = 100            
FILTER_DELAY_MS = 250   
ALL = "Усі"
ASCENDING = " ▲"
DESCENDING = " ▼"

JSON_TYPES = [("JSON", "*.json"), ("Усі файли", "*.*")]
XML_TYPES = [("XML", "*.xml"), ("Усі файли", "*.*")]

PROJECT_COLUMNS = [
    ("name", "Назва", 140, "w"),
    ("period", "Період", 150, "w"),
    ("items", "Завд.", 45, "e"),
    ("progress", "Готовність", 75, "e")
]

MEMBER_COLUMNS = [
    ("name", "Ім'я", 150, "w"),
    ("role", "Роль", 120, "w")
]

ITEM_COLUMNS = [
    ("title", "Назва", 250, "w", "title"),
    ("type", "Тип", 90, "w", None),
    ("assignee", "Виконавець", 150, "w", None),
    ("priority", "Пріоритет", 100, "w", "priority"),
    ("status", "Статус", 110, "w", "status"),
    ("deadline", "Дедлайн", 100, "center", "deadline"),
    ("estimate_hours", "Години", 70, "e", None)
]


class MainWindow(tk.Tk):


    def __init__(self):
        super().__init__()
        self.title("Менеджер проєктів")
        self.geometry("1150x680")
        self.minsize(900, 520)

        self._presenter = None
        self._busy = False
        self._indeterminate = False
        self._filter_job = None
        self._summary = ""

        self._projects = {}
        self._members = {}
        self._items = {}
        self._selected_project_id = None

        self._assignee_ids = {}        
        self._sort_field = "deadline"
        self._sort_desc = False

        self._locked_buttons = []
        self._locked_menu_entries = []

        self._build_menu()
        self._build_body()
        self._build_status_bar()
        self._update_headings()

    def attach(self, presenter):

        self._presenter = presenter
        self.protocol("WM_DELETE_WINDOW", presenter.on_close)
        self.after(POLL_MS, self._poll)

    def _poll(self):

        try:
            if self._presenter is not None:
                self._presenter.process_messages()
        finally:
            self.after(POLL_MS, self._poll)

    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Файл", menu=file_menu)
        self._add_menu_command(file_menu, "Імпорт JSON…", self._import)
        self._add_menu_command(file_menu, "Експорт JSON…", self._export_json)
        self._add_menu_command(
            file_menu, "XML-звіт про прострочені…", self._export_xml
        )
        file_menu.add_separator()
        file_menu.add_command(label="Вихід", command=self._exit)

        operations_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Операції", menu=operations_menu)
        self._add_menu_command(
            operations_menu, "Навантаження учасників", self._workload
        )
        self._add_menu_command(
            operations_menu, "Прострочені завдання", self._overdue
        )

        self.config(menu=menubar)

    def _add_menu_command(self, menu, label, command):
        menu.add_command(label=label, command=command)
        self._locked_menu_entries.append((menu, menu.index("end")))

    def _build_body(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        self._build_left_panel(left)
        self._build_right_panel(right)

    def _build_left_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=2)

        projects_box = ttk.LabelFrame(parent, text="Проєкти", padding=6)
        projects_box.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        self._projects_tree = self._build_table(
            projects_box, PROJECT_COLUMNS, selectmode="browse"
        )
        self._build_buttons(projects_box, [
            ("Додати", self._add_project),
            ("Змінити", self._edit_project),
            ("Видалити", self._delete_project)
        ])
        self._projects_tree.bind("<<TreeviewSelect>>", self._on_project_selected)
        self._projects_tree.bind(
            "<Double-1>", lambda e: self._on_double_click(
                e, self._projects_tree, self._edit_project)
        )

        members_box = ttk.LabelFrame(parent, text="Учасники", padding=6)
        members_box.grid(row=1, column=0, sticky="nsew")
        self._members_tree = self._build_table(
            members_box, MEMBER_COLUMNS, selectmode="browse"
        )
        self._build_buttons(members_box, [
            ("Додати", self._add_member),
            ("Змінити", self._edit_member),
            ("Видалити", self._delete_member)
        ])
        self._members_tree.bind(
            "<Double-1>", lambda e: self._on_double_click(
                e, self._members_tree, self._edit_member)
        )

    def _build_right_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        self._build_filter_bar(parent).grid(row=0, column=0, sticky="ew")

        items_box = ttk.LabelFrame(parent, text="Завдання", padding=6)
        items_box.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        columns = [(key, heading, width, anchor)
                   for key, heading, width, anchor, _field in ITEM_COLUMNS]
        self._items_tree = self._build_table(
            items_box, columns, selectmode="browse"
        )
        self._items_tree.tag_configure("overdue", foreground="#b00020")

        for key, _heading, _width, _anchor, field in ITEM_COLUMNS:
            if field is not None:
                self._items_tree.heading(
                    key, command=lambda f=field: self._on_sort(f)
                )

        self._build_buttons(items_box, [
            ("Додати", self._add_item),
            ("Змінити", self._edit_item),
            ("Видалити", self._delete_item)
        ])
        self._items_tree.bind(
            "<Double-1>", lambda e: self._on_double_click(
                e, self._items_tree, self._edit_item)
        )
        self._items_tree.bind("<Delete>", self._on_delete_key)

    def _build_filter_bar(self, parent):
        bar = ttk.LabelFrame(parent, text="Пошук і фільтри", padding=6)

        self._search_var = tk.StringVar(master=self)
        self._status_var_filter = tk.StringVar(master=self, value=ALL)
        self._priority_var_filter = tk.StringVar(master=self, value=ALL)
        self._assignee_var = tk.StringVar(master=self, value=ALL)

        ttk.Label(bar, text="Назва:").grid(row=0, column=0, padx=(0, 4))
        search = ttk.Entry(bar, textvariable=self._search_var, width=22)
        search.grid(row=0, column=1, padx=(0, 10))
        search.bind("<KeyRelease>", self._schedule_filters)

        ttk.Label(bar, text="Статус:").grid(row=0, column=2, padx=(0, 4))
        self._add_filter_box(
            bar, 3, self._status_var_filter, [ALL, *STATUS_LABELS.values()], 14
        )

        ttk.Label(bar, text="Пріоритет:").grid(row=0, column=4, padx=(0, 4))
        self._add_filter_box(
            bar, 5, self._priority_var_filter,
            [ALL, *PRIORITY_LABELS.values()], 12
        )

        ttk.Label(bar, text="Виконавець:").grid(row=0, column=6, padx=(0, 4))
        self._assignee_box = self._add_filter_box(
            bar, 7, self._assignee_var, [ALL], 22
        )

        ttk.Button(bar, text="Скинути", command=self._reset_filters).grid(
            row=0, column=8
        )
        return bar

    def _add_filter_box(self, parent, column, variable, values, width):
        box = ttk.Combobox(
            parent, textvariable=variable, values=values,
            state="readonly", width=width
        )
        box.grid(row=0, column=column, padx=(0, 10))
        box.bind("<<ComboboxSelected>>", self._apply_filters)
        return box

    def _build_status_bar(self):
        bar = ttk.Frame(self, padding=(6, 0, 6, 6))
        bar.pack(fill="x", side="bottom")
        bar.columnconfigure(0, weight=1)

        self._status_text = tk.StringVar(master=self, value="")
        ttk.Label(bar, textvariable=self._status_text).grid(
            row=0, column=0, sticky="w"
        )
        self._progress = ttk.Progressbar(
            bar, orient="horizontal", length=240, mode="determinate"
        )
        self._progress.grid(row=0, column=1, sticky="e")

    def _build_table(self, parent, columns, selectmode):

        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            parent, columns=[column[0] for column in columns],
            show="headings", selectmode=selectmode, height=6
        )

        for key, heading, width, anchor, *_ in columns:
            tree.heading(key, text=heading)
            tree.column(key, width=width, anchor=anchor, stretch=True)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return tree

    def _build_buttons(self, parent, specs):
        row = ttk.Frame(parent)
        row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

        for column, (text, command) in enumerate(specs):
            button = ttk.Button(row, text=text, command=command)
            button.grid(row=0, column=column, padx=(0, 6))
            self._locked_buttons.append(button)

    def show_projects(self, rows, selected_id):
        self._projects = {row["id"]: row for row in rows}
        self._selected_project_id = selected_id

        tree = self._projects_tree
        tree.delete(*tree.get_children())

        for row in rows:
            tree.insert("", "end", iid=str(row["id"]), values=(
                row["name"],
                f"{row['start']} — {row['end']}",
                row["items"],
                f"{row['progress'] * 100:.0f}%"
            ))

        if selected_id is not None and tree.exists(str(selected_id)):
            tree.selection_set(str(selected_id))
            tree.see(str(selected_id))

    def show_members(self, rows):
        self._members = {row["id"]: row for row in rows}

        self._refill(
            self._members_tree, rows,
            lambda row: (row["name"], row["role"])
        )


        previous_id = self._assignee_ids.get(self._assignee_var.get())
        self._assignee_ids = {member_label(row): row["id"] for row in rows}
        self._assignee_box.configure(values=[ALL, *self._assignee_ids])

        self._assignee_var.set(next(
            (label for label, member_id in self._assignee_ids.items()
             if member_id == previous_id),
            ALL
        ))

    def show_items(self, rows):
        self._items = {row["id"]: row for row in rows}

        tree = self._items_tree
        top = tree.yview()[0]

        def values(row):
            return (
                row["title"],
                label_of(TYPE_LABELS, row["type"]),
                row["assignee"],
                label_of(PRIORITY_LABELS, row["priority"]),
                label_of(STATUS_LABELS, row["status"]),
                row["deadline"],
                format_number(row["estimate_hours"])
            )

        self._refill(
            tree, rows, values,
            tags=lambda row: ("overdue",) if row["overdue"] else ()
        )
        tree.yview_moveto(top)

        self._summary = f"Показано завдань: {len(rows)}"
        if not self._busy:
            self._status_text.set(self._summary)

    def show_error(self, message):
        messagebox.showerror("Помилка", message, parent=self._dialog_parent())

    def show_info(self, message):
        messagebox.showinfo("Повідомлення", message, parent=self._dialog_parent())

    def confirm(self, message):
        return messagebox.askyesno(
            "Підтвердження", message,
            icon="warning", parent=self._dialog_parent()
        )

    def set_busy(self, is_busy):
      
        self._busy = bool(is_busy)

        for button in self._locked_buttons:
            button.state(["disabled"] if self._busy else ["!disabled"])

        for menu, index in self._locked_menu_entries:
            menu.entryconfigure(
                index, state="disabled" if self._busy else "normal"
            )

    def show_progress(self, done, total):
        if total is None:
            self._status_text.set("Виконується операція…")

            if not self._indeterminate:
                self._progress.configure(mode="indeterminate")
                self._progress.start(20)
                self._indeterminate = True
            return

        if self._indeterminate:
            self._progress.stop()
            self._indeterminate = False

        self._progress.configure(
            mode="determinate", maximum=max(total, 1), value=done
        )
        self._status_text.set(f"Оброблено частин: {done} з {total}")

    def stop_progress(self):
        self._progress.stop()
        self._indeterminate = False
        self._progress.configure(mode="determinate", value=0)
        self._status_text.set(self._summary)

    def show_workload(self, rows):
        if not rows:
            self.show_info("Невиконаних завдань немає.")
            return

        TableDialog(
            self, "Навантаження учасників",
            [
                ("name", "Учасник", 360, "w"),
                ("hours", "Годин у невиконаних завданнях", 220, "e")
            ],
            rows
        )

    def show_overdue(self, rows):
        if not rows:
            self.show_info("Прострочених завдань немає.")
            return

        TableDialog(
            self, "Прострочені завдання",
            [
                ("project", "Проєкт", 140, "w"),
                ("title", "Завдання", 220, "w"),
                ("assignee", "Виконавець", 130, "w"),
                ("deadline", "Дедлайн", 90, "center"),
                ("days_overdue", "Днів", 60, "e")
            ],
            rows
        )

    def close(self):
        self.destroy()

    def _dialog_parent(self):

        return self.grab_current() or self

    @staticmethod
    def _refill(tree, rows, values, tags=None):
   
        selected = set(tree.selection())
        tree.delete(*tree.get_children())

        for row in rows:
            tree.insert(
                "", "end", iid=str(row["id"]), values=values(row),
                tags=tags(row) if tags else ()
            )

        keep = [iid for iid in selected if tree.exists(iid)]
        if keep:
            tree.selection_set(keep)

    @staticmethod
    def _selected_id(tree):
        selection = tree.selection()
        return int(selection[0]) if selection else None

    def _selected_row(self, tree, rows, what):
  
        row = rows.get(self._selected_id(tree))

        if row is None:
            self.show_error(f"Спочатку виберіть {what} у таблиці.")

        return row

    def _on_double_click(self, event, tree, action):
        if self._busy:
            return

        if tree.identify_region(event.x, event.y) in ("cell", "tree"):
            action()

    def _on_delete_key(self, event=None):
        if not self._busy:
            self._delete_item()

    def _on_project_selected(self, event=None):
        if self._presenter is None:
            return

        new_id = self._selected_id(self._projects_tree)

        if new_id == self._selected_project_id:
            return

        if not self._presenter.select_project(new_id):
            self.show_projects(list(self._projects.values()),
                               self._selected_project_id)

    def _add_project(self):
        ProjectDialog(
            self,
            lambda v: self._presenter.add_project(
                v["name"], v["start"], v["end"]
            )
        ).show()

    def _edit_project(self):
        row = self._selected_row(self._projects_tree, self._projects, "проєкт")

        if row is None:
            return

        ProjectDialog(
            self,
            lambda v: self._presenter.update_project(
                row["id"], v["name"], v["start"], v["end"]
            ),
            initial=row
        ).show()

    def _delete_project(self):
        row = self._selected_row(self._projects_tree, self._projects, "проєкт")

        if row is not None:
            self._presenter.delete_project(row["id"])


    def _add_member(self):
        MemberDialog(
            self,
            lambda v: self._presenter.add_member(v["name"], v["role"])
        ).show()

    def _edit_member(self):
        row = self._selected_row(self._members_tree, self._members, "учасника")

        if row is None:
            return

        MemberDialog(
            self,
            lambda v: self._presenter.update_member(
                row["id"], v["name"], v["role"]
            ),
            initial=row
        ).show()

    def _delete_member(self):
        row = self._selected_row(self._members_tree, self._members, "учасника")

        if row is not None:
            self._presenter.delete_member(row["id"])

    def _add_item(self):
        if self._selected_project_id is None:
            self.show_error("Спочатку виберіть проєкт.")
            return

        ItemDialog(
            self,
            lambda v: self._presenter.add_item(**v),
            list(self._members.values())
        ).show()

    def _edit_item(self):
        row = self._selected_row(self._items_tree, self._items, "завдання")

        if row is None:
            return

        def submit(v):

            return self._presenter.update_item(
                row["id"], v["title"], v["assignee_id"], v["priority"],
                v["status"], v["deadline"], v["estimate_hours"]
            )

        ItemDialog(
            self, submit, list(self._members.values()), initial=row
        ).show()

    def _delete_item(self):
        row = self._selected_row(self._items_tree, self._items, "завдання")

        if row is not None:
            self._presenter.delete_item(row["id"])

    def _schedule_filters(self, event=None):

        if self._filter_job is not None:
            self.after_cancel(self._filter_job)

        self._filter_job = self.after(FILTER_DELAY_MS, self._apply_filters)

    def _apply_filters(self, event=None):
        if self._filter_job is not None:
            self.after_cancel(self._filter_job)
            self._filter_job = None

        if self._presenter is None:
            return

        self._presenter.set_filters(
            text=self._search_var.get(),
            status=key_of(STATUS_LABELS, self._status_var_filter.get()),
            priority=key_of(PRIORITY_LABELS, self._priority_var_filter.get()),
            assignee_id=self._assignee_ids.get(self._assignee_var.get())
        )

    def _reset_filters(self):
        self._search_var.set("")
        self._status_var_filter.set(ALL)
        self._priority_var_filter.set(ALL)
        self._assignee_var.set(ALL)
        self._apply_filters()

    def _on_sort(self, field):

        descending = (not self._sort_desc) if field == self._sort_field else False

        if self._presenter.set_sort(field, descending):
            self._sort_field = field
            self._sort_desc = descending
            self._update_headings()

    def _update_headings(self):
        for key, heading, _width, _anchor, field in ITEM_COLUMNS:
            arrow = ""

            if field is not None and field == self._sort_field:
                arrow = DESCENDING if self._sort_desc else ASCENDING

            self._items_tree.heading(key, text=heading + arrow)


    def _import(self):
        path = filedialog.askopenfilename(
            parent=self, title="Імпорт даних", filetypes=JSON_TYPES
        )

        if path:
            self._presenter.import_file(path)

    def _export_json(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Експорт даних", filetypes=JSON_TYPES,
            defaultextension=".json"
        )

        if path:
            self._presenter.export_json(path)

    def _export_xml(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="XML-звіт про прострочені завдання",
            filetypes=XML_TYPES, defaultextension=".xml"
        )

        if path:
            self._presenter.export_xml_report(path)

    def _workload(self):
        self._presenter.calculate_workload()

    def _overdue(self):
        self._presenter.find_overdue()

    def _exit(self):
        self._presenter.on_close()