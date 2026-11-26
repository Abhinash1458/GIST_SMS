
# app/config.py

import os
from pathlib import Path
from dotenv import load_dotenv

# Find the project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env
load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self):
        self.APP_NAME = os.getenv(
            "APP_NAME", "GIST SMS"
        )

        self.DATABASE_URL = os.getenv(
            "DATABASE_URL", "sqlite:///./sms.db"
        )

        self.SECRET_KEY = os.getenv("SECRET_KEY", "")

        self.ACCESS_TOKEN_MINUTES = int(
            os.getenv("ACCESS_TOKEN_MINUTES", "30")
        )

        self.ADMISSION_YEAR = int(
            os.getenv("ADMISSION_YEAR", "2026")
        )

        # Validate SECRET_KEY
        if len(self.SECRET_KEY) < 32:
            raise ValueError(
                "CONFIGURATION ERROR: SECRET_KEY must contain "
                "at least 32 characters. Please update your .env file."
            )

        if self.ACCESS_TOKEN_MINUTES <= 0:
            raise ValueError(
                "CONFIGURATION ERROR: ACCESS_TOKEN_MINUTES must be positive."
            )

        if self.ADMISSION_YEAR < 2000:
            raise ValueError(
                "CONFIGURATION ERROR: ADMISSION_YEAR is invalid."
            )


# Application settings object
settings = Settings()
