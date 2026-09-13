from pathlib import Path
import os

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_db_config() -> dict[str, str | int]:
    required = {
        "host": os.getenv("POSTGRES_HOST"),
        "port": os.getenv("POSTGRES_PORT"),
        "dbname": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }

    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing required database settings: " + ", ".join(missing)
        )

    return {
        "host": required["host"],
        "port": int(required["port"]),
        "dbname": required["dbname"],
        "user": required["user"],
        "password": required["password"],
    }