import asyncio

from .lifecycle import LifecycleManager
from .shutdown import ShutdownHandler
from .logger import logger


class ApplicationRunner:
    def __init__(self):
        self.lifecycle = LifecycleManager()
        self.shutdown = ShutdownHandler()

    async def start(self):
        logger.info("==============================")
        logger.info("STREAMBRIDGE STARTING")
        logger.info("==============================")

        self.shutdown.setup()

        self.lifecycle.start()
        self.lifecycle.running()

        logger.info("StreamBridge is running")

        try:
            await self.shutdown.wait()

        except asyncio.CancelledError:
            logger.info("Shutdown cancelled")

        finally:
            logger.info("Shutdown signal received")

            self.lifecycle.stop()

            logger.info("StreamBridge stopped cleanly")