# ШІ: Claude sonnet 5.5 – чернетка BackgroundTasks (фоновий імпорт, навантаження, прострочення).
# Змінено: try: job(operation_id, *args)
import logging
import queue
import threading
import time
from collections import namedtuple
from concurrent.futures import (
    FIRST_COMPLETED, CancelledError, ThreadPoolExecutor, wait
)

from models.enums import Status


logger = logging.getLogger(__name__)


_POLL_SECONDS = 0.1


PROGRESS = "progress"
RESULT = "result"
ERROR = "error"
DONE = "done"


Message = namedtuple("Message", ["kind", "operation_id", "data"])


def _workload_chunk(chunk):

    totals = {}

    for _project, item in chunk:
        if item.status == Status.DONE:
            continue

        member_id = item.assignee.id
        totals[member_id] = totals.get(member_id, 0) + item.estimate_hours

    return totals


def _overdue_chunk(chunk, today):

    return [
        {
            "project_id": project.id,
            "item_id": item.id,
            "days_overdue": (today - item.deadline).days
        }
        for project, item in chunk
        if item.is_overdue(today)
    ]


class BackgroundTasks:


    def __init__(self, service, max_workers=4, chunk_size=500):
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("Кількість потоків має бути цілим числом ≥ 1.")

        if not isinstance(chunk_size, int) or chunk_size < 1:
            raise ValueError("Розмір частини має бути цілим числом ≥ 1.")

        self._service = service
        self._chunk_size = chunk_size
        self._max_workers = max_workers
        self._queue = queue.Queue()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="worker"
        )

        self._state_lock = threading.Lock()
        self._last_operation_id = 0
        self._active_operations = 0

    @property
    def max_workers(self):
        return self._max_workers

    @property
    def is_busy(self):

        with self._state_lock:
            return self._active_operations > 0

    def poll(self):

        messages = []

        while True:
            try:
                messages.append(self._queue.get_nowait())
            except queue.Empty:
                return messages

    def get_message(self, timeout=None):

        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def shutdown(self):

        logger.info("Пул фонових потоків зупиняється")
        self._executor.shutdown(wait=False, cancel_futures=True)

    def start_import(self, path):
        return self._launch("імпорт", self._import_job, path)

    def start_workload(self):
        return self._launch("навантаження учасників", self._workload_job)

    def start_overdue(self, today):
        return self._launch("прострочені завдання", self._overdue_job, today)


    def _put(self, kind, operation_id, data=None):
        self._queue.put(Message(kind, operation_id, data))

    def _launch(self, name, job, *args):
        with self._state_lock:
            self._last_operation_id += 1
            operation_id = self._last_operation_id
            self._active_operations += 1

        thread = threading.Thread(
            target=self._run,
            args=(operation_id, name, job, args),
            name=f"coordinator-{operation_id}",
            daemon=True
        )
        thread.start()
        return operation_id

    def _run(self, operation_id, name, job, args):
        started = time.perf_counter()
        outcome = "успішно"
        logger.info("Операцію №%s (%s) запущено", operation_id, name)

        try:
            job(operation_id, *args)

        except (Exception, CancelledError) as error:
            outcome = "з помилкою"
            logger.exception(
                "Помилка фонової операції №%s (%s)", operation_id, name
            )
            self._put(ERROR, operation_id, str(error) or type(error).__name__)

        finally:

            logger.info(
                "Операцію №%s (%s) завершено %s за %.3f с",
                operation_id, name, outcome, time.perf_counter() - started
            )

            with self._state_lock:
                self._active_operations -= 1

            self._put(DONE, operation_id)

    def _run_chunked(self, operation_id, pairs, function, *extra):

        size = self._chunk_size
        chunks = [pairs[start:start + size] for start in range(0, len(pairs), size)]
        total = len(chunks)

        logger.info(
            "Операція №%s: завдань %s, частин %s (по %s), потоків %s",
            operation_id, len(pairs), total, size, self._max_workers
        )
        self._put(PROGRESS, operation_id, {"done": 0, "total": total})

        futures = {
            self._executor.submit(function, chunk, *extra): index
            for index, chunk in enumerate(chunks)
        }
        results = [None] * total
        pending = set(futures)
        finished = 0

        try:
            while pending:

                done, pending = wait(
                    pending, timeout=_POLL_SECONDS, return_when=FIRST_COMPLETED
                )

                for future in done:
                    results[futures[future]] = future.result()
                    finished += 1
                    self._put(
                        PROGRESS, operation_id,
                        {"done": finished, "total": total}
                    )

                if any(future.cancelled() for future in pending):
                    raise CancelledError(
                        "Операцію скасовано: застосунок закривається."
                    )
        except BaseException:
            for future in futures:
                future.cancel()
            raise

        return results

    def _import_job(self, operation_id, path):

        self._put(PROGRESS, operation_id, {"done": 0, "total": None})

        self._service.load_file(path)

        self._put(RESULT, operation_id, {
            "members": len(self._service.members),
            "projects": len(self._service.projects)
        })

    def _workload_job(self, operation_id):
        pairs = self._service.snapshot_items()
        results = self._run_chunked(operation_id, pairs, _workload_chunk)

        merged = {}

        for partial in results:
            for member_id, hours in partial.items():
                merged[member_id] = merged.get(member_id, 0) + hours

        self._put(RESULT, operation_id, {"workload": merged})

    def _overdue_job(self, operation_id, today):
        pairs = self._service.snapshot_items()
        results = self._run_chunked(
            operation_id, pairs, _overdue_chunk, today
        )

        overdue = [entry for partial in results for entry in partial]
        overdue.sort(key=lambda entry: (entry["project_id"], entry["item_id"]))

        self._put(RESULT, operation_id, {"overdue": overdue})