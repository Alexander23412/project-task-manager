# ШІ: Claude sonnet 5.5 – Перевірка коду
import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from models.enums import Priority, Status


ITEM_TYPES = ["Task", "Bug", "Milestone"]
ITEM_WEIGHTS = [60, 25, 15]

STATUS_WEIGHTS = {
    Status.TODO: 40,
    Status.IN_PROGRESS: 25,
    Status.DONE: 35
}

FIRST_NAMES = [
    "Олена", "Іван", "Марія", "Андрій", "Наталія", "Петро", "Софія",
    "Максим", "Ірина", "Богдан", "Тетяна", "Дмитро"
]
LAST_NAMES = [
    "Коваленко", "Шевченко", "Бондаренко", "Мельник", "Ткаченко",
    "Кравчук", "Олійник", "Лисенко", "Мороз", "Савченко"
]
ROLES = ["Developer", "Tester", "Designer", "Manager", "Analyst"]

PROJECT_WORDS = [
    "Альфа", "Бета", "Гамма", "Орбіта", "Маяк", "Течія", "Вершина", "Міст"
]

TITLE_PARTS = {
    "Task": (
        ["Підготувати", "Налаштувати", "Описати", "Оновити", "Розробити"],
        ["модуль", "звіт", "інтерфейс", "документацію", "сервіс"]
    ),
    "Bug": (
        ["Виправити", "Усунути", "Перевірити", "Локалізувати"],
        ["збій", "помилку", "витік пам'яті", "некоректний підрахунок"]
    ),
    "Milestone": (
        ["Завершити", "Здати", "Погодити", "Випустити"],
        ["етап", "реліз", "прототип", "версію"]
    )
}


def generate(projects=100, items_per_project=100, members=20, seed=42):

    if min(projects, items_per_project, members) < 1:
        raise ValueError("Кількість проєктів, задач і учасників має бути ≥ 1.")

    rng = random.Random(seed)
    statuses = list(STATUS_WEIGHTS)
    status_weights = list(STATUS_WEIGHTS.values())
    priorities = list(Priority)

    member_list = [
        {
            "id": member_id,
            "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
            "role": rng.choice(ROLES)
        }
        for member_id in range(1, members + 1)
    ]

    project_list = []
    next_item_id = 1  

    for project_id in range(1, projects + 1):
        start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 180))
        end = start + timedelta(days=rng.randint(540, 900))
        span_days = (end - start).days

        items = []

        for number in range(1, items_per_project + 1):
            item_type = rng.choices(ITEM_TYPES, ITEM_WEIGHTS)[0]
            verbs, nouns = TITLE_PARTS[item_type]

            items.append({
                "id": next_item_id,

                "title": f"{rng.choice(verbs)} {rng.choice(nouns)} №{number}",
                "type": item_type,
                "assignee_id": rng.randint(1, members),
                "priority": rng.choice(priorities).value,
                "status": rng.choices(statuses, status_weights)[0].value,
                "deadline": (
                    start + timedelta(days=rng.randint(0, span_days))
                ).isoformat(),
                "estimate_hours": rng.randint(1, 40)
            })
            next_item_id += 1

        project_list.append({
            "id": project_id,
            "name": f"Проєкт {project_id:03d} «{rng.choice(PROJECT_WORDS)}»",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "items": items
        })

    return {"members": member_list, "projects": project_list}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Генератор тестових JSON-файлів у форматі projects.json."
    )
    parser.add_argument("--projects", type=int, default=100)
    parser.add_argument("--items", type=int, default=100,
                        help="завдань на кожен проєкт")
    parser.add_argument("--members", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="data/projects_large.json")
    args = parser.parse_args(argv)

    try:
        data = generate(args.projects, args.items, args.members, args.seed)
    except ValueError as error:
        parser.error(str(error))

    write_json(args.output, data)
    total = args.projects * args.items
    print(
        f"Записано {args.output}: {args.members} учасників, "
        f"{args.projects} проєктів, {total} завдань (seed={args.seed})."
    )

if __name__ == "__main__":
    main()