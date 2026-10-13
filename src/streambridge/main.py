import asyncio

from core.runner import ApplicationRunner


async def main():
    runner = ApplicationRunner()

    await runner.start()


if __name__ == "__main__":
    asyncio.run(main())