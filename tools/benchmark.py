# ШІ: Claude sonnet 5.5 – Перевірка коду 
import argparse
import os
import platform
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from services.background_tasks import DONE, ERROR, BackgroundTasks
from services.project_service import ProjectService


OPERATIONS = [
    ("Навантаження учасників", lambda tasks, today: tasks.start_workload()),
    ("Пошук прострочень", lambda tasks, today: tasks.start_overdue(today))
]

def run_once(tasks, start, today, timeout=120.0):

    started = time.perf_counter()
    operation_id = start(tasks, today)

    while True:
        message = tasks.get_message(timeout=timeout)

        if message is None:
            raise RuntimeError(f"Операція не завершилась за {timeout} с.")

        if message.operation_id != operation_id:
            continue

        if message.kind == ERROR:
            raise RuntimeError(f"Помилка під час замірів: {message.data}")

        if message.kind == DONE:
            return time.perf_counter() - started


def measure(service, start, workers, repeats, chunk_size, today):
    tasks = BackgroundTasks(
        service, max_workers=workers, chunk_size=chunk_size
    )

    try:
        run_once(tasks, start, today) 
        return [
            run_once(tasks, start, today) for _ in range(repeats)
        ]
    finally:
        tasks.shutdown()


def benchmark(service, worker_counts, repeats, chunk_size, today):

    rows = []

    for name, start in OPERATIONS:
        medians = {}

        for workers in worker_counts:
            times = measure(
                service, start, workers, repeats, chunk_size, today
            )
            medians[workers] = (statistics.median(times), min(times))

        baseline = medians[1][0]

        for workers in worker_counts:
            median, minimum = medians[workers]
            speedup = baseline / median
            rows.append(
                (name, workers, median, minimum, speedup, speedup / workers)
            )

    return rows


def gil_status():
    check = getattr(sys, "_is_gil_enabled", None)

    if check is None:
        return "увімкнено (Python < 3.13, sys._is_gil_enabled недоступна)"

    return "увімкнено" if check() else "вимкнено (free-threaded збірка)"


def format_report(rows, item_count, chunk_size, repeats, load_seconds):
    chunks = -(-item_count // chunk_size)

    lines = [
        f"Python: {platform.python_version()} ({platform.python_implementation()})",
        f"GIL: {gil_status()}",
        f"Платформа: {platform.platform()}",
        f"Логічних ядер: {os.cpu_count()}",
        f"Завдань: {item_count}, розмір частини: {chunk_size}, "
        f"частин: {chunks}",
        f"Повторів: {repeats} (+1 прогрівальний), показано медіану",
        f"Завантаження файлу: {load_seconds:.3f} с",
        "",
        "| Операція | Потоків n | Медіана T, с | Мінімум, с | S = T1/Tn | E = S/n |",
        "|---|---|---|---|---|---|"
    ]

    for name, workers, median, minimum, speedup, efficiency in rows:
        lines.append(
            f"| {name} | {workers} | {median:.4f} | {minimum:.4f} "
            f"| {speedup:.2f} | {efficiency:.2f} |"
        )

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Порівняння 1, 2, 4, 8 потоків на великому файлі."
    )
    parser.add_argument("--file", default="data/projects_large.json")
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today(),
                        help="дата для пошуку прострочень, YYYY-MM-DD")
    parser.add_argument("--output", help="додатково записати звіт у файл")
    args = parser.parse_args(argv)

    if 1 not in args.workers:
        parser.error("У --workers має бути 1: це база для S = T1/Tn.")

    if args.repeats < 1 or args.chunk_size < 1 or min(args.workers) < 1:
        parser.error("--repeats, --chunk-size та --workers мають бути ≥ 1.")

    service = ProjectService()

    started = time.perf_counter()
    service.load_file(args.file)
    load_seconds = time.perf_counter() - started

    item_count = len(service.snapshot_items())
    print(f"Завантажено {item_count} завдань, вимірюю...", flush=True)

    rows = benchmark(
        service, sorted(set(args.workers)), args.repeats,
        args.chunk_size, args.today
    )
    report = format_report(
        rows, item_count, args.chunk_size, args.repeats, load_seconds
    )

    print()
    print(report)

    if args.output:
        Path(args.output).write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()