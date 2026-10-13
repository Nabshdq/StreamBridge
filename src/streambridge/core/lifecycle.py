from .state import ApplicationState


class LifecycleManager:
    def __init__(self):
        self.state = ApplicationState.STOPPED

    def start(self):
        self.state = ApplicationState.STARTING
        print(f"STATE: {self.state.value}")

    def running(self):
        self.state = ApplicationState.RUNNING
        print(f"STATE: {self.state.value}")

    def stop(self):
        self.state = ApplicationState.STOPPING
        print(f"STATE: {self.state.value}")

        self.state = ApplicationState.STOPPED
        print(f"STATE: {self.state.value}")