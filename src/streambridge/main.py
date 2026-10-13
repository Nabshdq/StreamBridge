import asyncio

from core.lifecycle import LifecycleManager
from core.shutdown import ShutdownHandler
from core.logger import logger


async def main():
    lifecycle = LifecycleManager()
    shutdown = ShutdownHandler()

    logger.info("==============================")
    logger.info("STREAMBRIDGE STARTING")
    logger.info("==============================")

    shutdown.setup()

    lifecycle.start()
    lifecycle.running()

    logger.info("StreamBridge is running")

    try:
        await shutdown.wait()

    finally:
        logger.info("Shutdown signal received")

        lifecycle.stop()

        logger.info("StreamBridge stopped cleanly")


if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("CTRL+C received")