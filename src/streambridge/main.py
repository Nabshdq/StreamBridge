from core.lifecycle import LifecycleManager
from core.logger import logger


def main():
    lifecycle = LifecycleManager()

    logger.info("==============================")
    logger.info("STREAMBRIDGE STARTING")
    logger.info("==============================")

    lifecycle.start()

    logger.info("Application initialized")

    lifecycle.running()

    logger.info("StreamBridge is running")

    lifecycle.stop()

    logger.info("StreamBridge stopped")


if __name__ == "__main__":
    main()