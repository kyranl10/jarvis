"""Captions of recent posts from Instagram accounts you follow, via Meta's official Business Discovery API.

Instagram blocks outside apps from reading profiles, and it doesn't email you when someone posts.
Business Discovery is Meta's sanctioned way to read another account's public posts. It's free but needs
your own Instagram to be a professional (creator) account linked to a Facebook Page, plus a token from a
Meta developer app: INSTAGRAM_USER_ID and INSTAGRAM_TOKEN. It can only read business and creator accounts.
INSTAGRAM_WATCH lists the usernames to follow, comma separated.
"""
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

API = "https://graph.facebook.com/v23.0"


class TokenExpired(Exception):
    """Meta tokens can expire; the briefing says so instead of going quiet."""


@dataclass
class Post:
    at: datetime
    who: str
    text: str
    url: str = ""


def clean(caption: str) -> str:
    text = re.sub(r"(?:\s*#\w+)+\s*$", "", caption or "")  # the block of hashtags at the end
    return re.sub(r"\s+", " ", text).strip()


def parse(data: dict, who: str, tz: ZoneInfo) -> list[Post]:
    media = data.get("business_discovery", {}).get("media", {}).get("data", [])
    posts = []
    for m in media:
        if not m.get("timestamp"):
            continue
        at = datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(tz)
        posts.append(Post(at, who, clean(m.get("caption", "")), m.get("permalink", "")))
    return sorted(posts, key=lambda p: p.at, reverse=True)  # newest first


def fetch_posts(user_id: str, token: str, username: str, tz: ZoneInfo, limit: int = 10) -> list[Post]:
    fields = f"business_discovery.username({username}){{media.limit({limit}){{caption,timestamp,permalink}}}}"
    resp = requests.get(f"{API}/{user_id}", params={"fields": fields, "access_token": token}, timeout=30)
    if resp.status_code in (400, 401) and resp.json().get("error", {}).get("code") == 190:
        raise TokenExpired()
    resp.raise_for_status()
    return parse(resp.json(), username, tz)
