import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _need(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing setting {name}. Add it to your .env file (see .env.example).")
    return value


@dataclass(frozen=True)
class Config:
    name: str
    tz: ZoneInfo
    latitude: float
    longitude: float
    ics_url: str
    work_ics_url: str = ""
    work_name: str = "Work"
    work_domain: str = ""

    @classmethod
    def load(cls) -> "Config":
        return cls(
            name=os.getenv("JARVIS_NAME", "Kyran"),
            tz=ZoneInfo(os.getenv("TIMEZONE", "America/New_York")),
            latitude=float(os.getenv("LATITUDE", "35.9132")),
            longitude=float(os.getenv("LONGITUDE", "-79.0558")),
            ics_url=os.getenv("OUTLOOK_ICS_URL", "").strip(),
            work_ics_url=os.getenv("WORK_ICS_URL", "").strip(),
            work_name=os.getenv("WORK_NAME", "").strip() or "Work",
            work_domain=os.getenv("WORK_EMAIL_DOMAIN", "").strip().lower().lstrip("@"),
        )
