import logging
import os

from logging.handlers import RotatingFileHandler

from .config import Config


def setup_logger():
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("streambridge")

    log_level = getattr(
        logging,
        Config.LOG_LEVEL.upper(),
        logging.INFO
    )

    logger.setLevel(log_level)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(
        "logs/streambridge.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )

    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()

    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()


def log_exception(message):
    logger.exception(message)