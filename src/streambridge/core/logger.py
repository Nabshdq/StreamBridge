import logging
import os


def setup_logger():
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("streambridge")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        "logs/streambridge.log",
        encoding="utf-8"
    )

    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger


logger = setup_logger()


def log_exception(message):
    logger.exception(message)