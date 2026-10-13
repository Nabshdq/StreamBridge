import asyncio
import signal
import platform


class ShutdownHandler:
    def __init__(self):
        self.event = asyncio.Event()

    def setup(self):
        system = platform.system()

        if system != "Windows":
            loop = asyncio.get_running_loop()

            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(
                    sig,
                    self.request_shutdown
                )

    def request_shutdown(self):
        self.event.set()

    async def wait(self):
        await self.event.wait()