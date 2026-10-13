from .state import ApplicationState
from .logger import logger


class LifecycleManager:
    def __init__(self):
        self.state = ApplicationState.STOPPED

    def start(self):
        self.state = ApplicationState.STARTING
        logger.info(f"STATE: {self.state.value}")

    def running(self):
        self.state = ApplicationState.RUNNING
        logger.info(f"STATE: {self.state.value}")

    def stop(self):
        self.state = ApplicationState.STOPPING
        logger.info(f"STATE: {self.state.value}")

        self.state = ApplicationState.STOPPED
        logger.info(f"STATE: {self.state.value}")