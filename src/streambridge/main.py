from core.lifecycle import LifecycleManager


def main():
    lifecycle = LifecycleManager()

    print("==============================")
    print("STREAMBRIDGE STARTING")
    print("==============================")

    lifecycle.start()

    print("Application initialized")

    lifecycle.running()

    print("StreamBridge is running")

    lifecycle.stop()


if __name__ == "__main__":
    main()