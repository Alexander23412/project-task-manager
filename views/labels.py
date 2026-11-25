# ШІ: Claude sonnet 5.5 – Перевірка коду
STATUS_LABELS = {
    "todo": "До виконання",
    "in_progress": "У роботі",
    "done": "Виконано"
}

PRIORITY_LABELS = {
    "low": "Низький",
    "medium": "Середній",
    "high": "Високий"
}

TYPE_LABELS = {
    "Task": "Задача",
    "Bug": "Помилка",
    "Milestone": "Віха"
}


def label_of(mapping, key):

    return mapping.get(key, str(key))


def key_of(mapping, label):

    for key, value in mapping.items():
        if value == label:
            return key

    return None


def member_label(row):

    return f"{row['name']} (№{row['id']})"


def format_number(value):

    if isinstance(value, float):
        return f"{value:g}"

    return str(value)