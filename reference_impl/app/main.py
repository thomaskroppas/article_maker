"""
Точка входа приложения SEO Pipeline.
Инициализирует БД, логгер, запускает GUI.
"""
import sys
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.config.settings import LOGS_DIR
from app.storage.db_manager import init_db, close_all


def setup_logging():
    log_file = LOGS_DIR / "app.log"
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ],
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("=== SEO Pipeline запускается ===")

    # Инициализация PostgreSQL пула
    init_db()
    logger.info("PostgreSQL инициализирован")

    # GUI
    app = QApplication(sys.argv)
    app.setApplicationName("SEO Pipeline")
    app.setOrganizationName("SEO Tools")

    from app.ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    logger.info("GUI запущен")
    exit_code = app.exec()

    # Закрываем пул соединений при выходе
    close_all()
    logger.info("PostgreSQL пул закрыт")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
