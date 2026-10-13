import asyncio

from .core.runner import ApplicationRunner


async def main():
    runner = ApplicationRunner()

    await runner.start()


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()