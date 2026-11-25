# ШІ: Claude sonnet 5.5 – Перевірка коду
import argparse
import logging
import sys
from pathlib import Path

from presenters.main_presenter import MainPresenter
from services.background_tasks import BackgroundTasks
from services.project_service import ProjectService
from views.main_window import MainWindow


BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / "tasks.log"
DEFAULT_DATA_PATH = BASE_DIR / "data" / "projects.json"

LOG_FORMAT = "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"

logger = logging.getLogger(__name__)


def setup_logging(path=LOG_PATH):

    logging.basicConfig(
        filename=path,
        encoding="utf-8",
        level=logging.INFO,
        format=LOG_FORMAT
    )


def create_app():

    service = ProjectService()
    tasks = BackgroundTasks(service)
    window = MainWindow()
    presenter = MainPresenter(service, tasks, window)
    window.attach(presenter)

    def report_callback_exception(exc_type, exc_value, exc_traceback):
        logger.error(
            "Необроблений виняток в обробнику інтерфейсу",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
        presenter.show_unexpected_error(exc_value)

    window.report_callback_exception = report_callback_exception

    return service, tasks, window, presenter


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Менеджер проєктів")
    parser.add_argument(
        "--file", type=Path, default=DEFAULT_DATA_PATH,
        help="JSON-файл, який завантажується під час запуску"
    )
    parser.add_argument(
        "--empty", action="store_true",
        help="не завантажувати файл, почати з порожніх даних"
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    setup_logging()
    logger.info("Запуск застосунку")

    _service, _tasks, window, presenter = create_app()
    presenter.start()

    if not args.empty and args.file.is_file():
        logger.info("Стартове завантаження: %s", args.file)
        presenter.import_file(args.file, announce=False)

    window.mainloop()
    logger.info("Застосунок закрито")


if __name__ == "__main__":
    sys.exit(main())