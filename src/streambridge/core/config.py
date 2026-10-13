import os

from dotenv import load_dotenv


load_dotenv()


class Config:
    APP_NAME = os.getenv("APP_NAME", "StreamBridge")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    TIKTOK_USERNAME = os.getenv("TIKTOK_USERNAME")

    TWITCH_TOKEN = os.getenv("TWITCH_TOKEN")
    TWITCH_CHANNEL = os.getenv("TWITCH_CHANNEL")