# ШІ: Claude sonnet 5.5 – Перевірка коду
import argparse
import os
import platform
import statistics
import time
from pathlib import Path

from services.project_service import ProjectService


def measure(path, repeats, warmup):

    times = []

    for attempt in range(warmup + repeats):
        service = ProjectService()
        started = time.perf_counter()
        service.load_file(path)
        elapsed = time.perf_counter() - started

        if attempt >= warmup:
            times.append(elapsed)

    return len(service.projects), len(service.snapshot_items()), times


def format_report(results, repeats, warmup):
    baseline = results[0]["median"]

    lines = [
        f"Python: {platform.python_version()} ({platform.python_implementation()})",
        f"Платформа: {platform.platform()}",
        f"Логічних ядер: {os.cpu_count()}",
        f"Повторів: {repeats} (+{warmup} прогрівальних), показано медіану",
        "",
        "| Файл | Проєктів | Завдань | Медіана, с | Мінімум, с "
        "| мс на завдання | Відносно першого |",
        "|---|---|---|---|---|---|---|"
    ]

    for row in results:
        per_item = row["median"] / row["items"] * 1000
        lines.append(
            f"| {row['name']} | {row['projects']} | {row['items']} "
            f"| {row['median']:.3f} | {row['minimum']:.3f} "
            f"| {per_item:.3f} | ×{row['median'] / baseline:.2f} |"
        )

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Порівняння часу завантаження JSON-файлів."
    )
    parser.add_argument("--files", type=Path, nargs="+", required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--output", type=Path,
                        help="додатково записати звіт у файл")
    args = parser.parse_args(argv)

    if args.repeats < 1 or args.warmup < 0:
        parser.error("--repeats має бути ≥ 1, --warmup ≥ 0.")

    results = []

    for path in args.files:
        print(f"Вимірюю {path} ...", flush=True)
        projects, items, times = measure(path, args.repeats, args.warmup)
        results.append({
            "name": path.name, "projects": projects, "items": items,
            "median": statistics.median(times), "minimum": min(times)
        })

    report = format_report(results, args.repeats, args.warmup)
    print()
    print(report)

    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()