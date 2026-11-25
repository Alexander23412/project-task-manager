# ШІ: Claude sonnet 5.5 – Перевірка коду
import argparse
import copy
import json
from pathlib import Path

from tools.generate_data import generate


def _item(data, project=0, index=0):
    return data["projects"][project]["items"][index]


def _mutation(change):

    def build(base):
        data = copy.deepcopy(base)
        change(data)
        return data
    return build


def _set(getter, key, value):
    return _mutation(lambda data: getter(data).__setitem__(key, value))


def _delete(key):
    return _mutation(lambda data: data.pop(key))


def _same_project_id(data):
    data["projects"][1]["id"] = data["projects"][0]["id"]


def _same_member_id(data):
    data["members"][1]["id"] = data["members"][0]["id"]


def _same_item_id_in_other_project(data):
    _item(data, 1, 0)["id"] = _item(data, 0, 0)["id"]


def _same_project_name_other_case(data):
    data["projects"][1]["name"] = data["projects"][0]["name"].upper()


CASES = [
    ("01_truncated.json", "обрив файлу (немає закриваючих дужок)", "truncated"),
    ("02_empty.json", "порожній файл", ""),
    ("03_not_an_object.json", "корінь не об'єкт, а список", "[]"),
    ("04_no_members.json", "немає ключа members", _delete("members")),
    ("05_no_projects.json", "немає ключа projects", _delete("projects")),
    ("06_unknown_type.json", "невідомий тип завдання «Epic»",
     _set(_item, "type", "Epic")),
    ("07_unknown_status.json", "невідомий статус",
     _set(_item, "status", "nope")),
    ("08_unknown_priority.json", "невідомий пріоритет",
     _set(_item, "priority", "nope")),
    ("09_unknown_assignee.json", "виконавця з id 999 не існує",
     _set(_item, "assignee_id", 999)),
    ("10_duplicate_member_id.json", "повтор id учасника",
     _mutation(_same_member_id)),
    ("11_duplicate_project_id.json", "повтор id проєкту",
     _mutation(_same_project_id)),
    ("12_duplicate_item_id.json", "повтор id завдання між проєктами",
     _mutation(_same_item_id_in_other_project)),
    ("13_nonexistent_date.json", "дата 2026-13-45",
     _set(_item, "deadline", "2026-13-45")),
    ("14_wrong_date_format.json", "формат дати 01.02.2026",
     _set(_item, "deadline", "01.02.2026")),
    ("15_deadline_outside_project.json", "дедлайн поза межами проєкту",
     _set(_item, "deadline", "2099-01-01")),
    ("16_duplicate_project_name.json", "однакова назва проєктів (інший регістр)",
     _mutation(_same_project_name_other_case)),
    ("17_zero_hours.json", "оцінка часу 0",
     _set(_item, "estimate_hours", 0)),
    ("18_hours_as_string.json", "оцінка часу рядком «8»",
     _set(_item, "estimate_hours", "8")),
    ("19_empty_title.json", "порожня назва завдання",
     _set(_item, "title", "")),
]


def build_files():
    """Повертає {ім'я файлу: (опис, вміст)}. Вміст це готовий текст."""
    base = generate(projects=3, items_per_project=4, members=3, seed=1)
    text = json.dumps(base, ensure_ascii=False, indent=2)
    files = {}

    for name, description, how in CASES:
        if how == "truncated":
            content = text[: len(text) // 2]
        elif isinstance(how, str):
            content = how
        else:
            content = json.dumps(how(base), ensure_ascii=False, indent=2)

        files[name] = (description, content)

    return files


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Створює пошкоджені JSON-файли для ручної перевірки імпорту."
    )
    parser.add_argument("--output", type=Path, default=Path("data/broken"))
    args = parser.parse_args(argv)

    args.output.mkdir(parents=True, exist_ok=True)

    for name, (description, content) in build_files().items():
        (args.output / name).write_text(content, encoding="utf-8")
        print(f"{args.output / name}: {description}")

    print(f"\nСтворено файлів: {len(CASES)}.")


if __name__ == "__main__":
    main()