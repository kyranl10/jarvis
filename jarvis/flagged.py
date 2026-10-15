"""Emails Jarvis flagged as worth Kyran's attention, shown in the HUD's Inbox panel.

A scheduled Claude task reads new mail under the Gmail "Jarvis" label every couple of hours, decides
what matters, and commits the result encrypted to data/mail.enc (see mailstore). This module trims that
data and the briefing run publishes it to the ntfy "-mail" side topic, which the HUD reads.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

from . import mailstore

LIMIT = 3900  # ntfy turns bigger messages into attachments the HUD can't read
CLOSED = ("denied", "done")  # statuses mirrored from Jarvis Mail that take an item off the HUD


def load(now: datetime, path: Path | None = None, keep_hours: int = 72) -> dict | None:
    """The flagged emails from the last `keep_hours`, most important then newest first, sized for ntfy."""
    data = mailstore.read(path)
    if data is None:
        return None
    cutoff = now - timedelta(hours=keep_hours)
    items, gone = [], []
    for item in data.get("flagged", []):
        try:
            at = datetime.fromisoformat(item["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if at.tzinfo is None or at < cutoff:
            continue
        if item.get("status") == "denied":  # listed under the Mail page's Dismissed tab, restorable on the Claude page
            gone.append({k: item.get(k, "") for k in ("id", "at", "from", "subject", "level")})
        if item.get("status") in CLOSED:
            continue  # dismissed or finished in Jarvis Mail
        items.append({k: item.get(k, "") for k in ("id", "at", "from", "subject", "gist", "why", "level", "url")})  # id: the item in Jarvis Mail
        if isinstance(item.get("plan"), dict):  # the recommended plan, kept free of names and addresses
            items[-1]["plan"] = item["plan"]
    items.sort(key=lambda i: i["at"], reverse=True)
    items.sort(key=lambda i: i["level"] != "act")  # stable: action items first, each group newest first
    gone += [{"subject": d["subject"], "at": d["at"]} for d in _dismissed(data, now)]
    gone.sort(key=lambda i: i["at"], reverse=True)
    out = {"updated": data.get("updated", ""), "flagged": items, "dismissed": gone}
    while len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > LIMIT and out["dismissed"]:
        out["dismissed"].pop()  # the dismissed list goes first
    while len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > LIMIT and any("plan" in i for i in items):
        next(i for i in reversed(items) if "plan" in i).pop("plan")  # plans go before items; the HUD links to them
    while len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > LIMIT and any(i.get("gist") for i in items):
        next(i for i in reversed(items) if i.get("gist"))["gist"] = ""  # then the oldest gists; "why" still says enough
    while len(json.dumps(out, ensure_ascii=False).encode("utf-8")) > LIMIT and out["flagged"]:
        out["flagged"].pop()  # the least important, oldest item goes first
    return out



def _dismissed(data: dict, now: datetime) -> list[dict]:
    """Emails dismissed in Jarvis Mail that were never flagged: {"subject", "at" (when dismissed)}, kept 3 days."""
    out = []
    for d in data.get("dismissed", []):
        try:
            if now - datetime.fromisoformat(d["at"]) <= timedelta(days=3):
                out.append(d)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def dismissed(now: datetime, path: Path | None = None) -> set[str]:
    """Subjects (lowercase) dismissed in Jarvis Mail, so the HUD's recent list skips them too."""
    data = mailstore.read(path)
    if data is None:
        return set()
    return {str(d["subject"]).strip().lower() for d in _dismissed(data, now)}
