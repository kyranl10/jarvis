"""Free push notifications to your phone via ntfy (https://ntfy.sh)."""
import requests

from .config import _need


def push(title: str, body: str, topic_suffix: str = "", tags: str = "") -> None:
    topic = _need("NTFY_TOPIC") + topic_suffix
    headers = {"Title": title.encode("utf-8")}
    if tags:
        headers["Tags"] = tags
    resp = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()


def publish_quietly(body: str, topic_suffix: str) -> None:
    """Stores a message on a side topic without notifying anyone (the iPhone Shortcut reads it)."""
    topic = _need("NTFY_TOPIC") + topic_suffix
    resp = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"), timeout=30)
    resp.raise_for_status()
