"""PMA announcements, read from your own private Discord server.

A bot can only read servers it has been added to, so PMA posts are forwarded (or followed) into a
private server where Jarvis's bot lives: DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID (that server's channel).
Announcements that name a time ("Chapter tonight at 9:00 in Hill Hall") become calendar events.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests

from .calendar_source import Event

API = "https://discord.com/api/v10"


@dataclass
class Post:
    at: datetime
    text: str


def clean(text: str) -> str:
    text = re.sub(r"<a?:\w+:\d+>", "", text)  # custom emoji
    text = re.sub(r"<[@#][!&]?\d+>", "", text)  # user, role and channel mentions
    text = re.sub(r"(^|\s)@(everyone|here|\w+)\b", r"\1", text) if text.lstrip().startswith("@") else text
    text = re.sub(r"[*_~`|>]{1,3}", "", text)  # markdown
    return re.sub(r"\s+", " ", text).strip(" ,")


def fetch_posts(token: str, channel_id: str, tz: ZoneInfo, limit: int = 30) -> list[Post]:
    resp = requests.get(f"{API}/channels/{channel_id}/messages", params={"limit": limit},
                        headers={"Authorization": f"Bot {token}"}, timeout=30)
    resp.raise_for_status()
    posts = []
    for m in resp.json():
        if m.get("type", 0) not in (0, 19):
            continue  # system messages, like "added #announcements to this channel"
        # A forwarded message keeps the original in a snapshot, with the time it was first posted
        m = (m.get("message_snapshots") or [{}])[0].get("message") or m
        text = clean(m.get("content") or "")
        if text and m.get("timestamp"):
            posts.append(Post(datetime.fromisoformat(m["timestamp"]).astimezone(tz), text))
    return sorted(posts, key=lambda p: p.at, reverse=True)  # newest first


WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

_TIME = re.compile(r"\b(?:(noon|midnight)|(\d{1,2}):(\d{2})\s*([ap]\.?m\b\.?)?|(\d{1,2})\s*([ap]\.?m\b\.?)|at\s+(\d{1,2})\b(?=[^/:]|$))",
                   re.I)
_DAY = re.compile(r"\b(?:(tonight|today|this (?:morning|afternoon|evening))|(tomorrow|tmrw?)"
                  r"|(?:this |next )?(mon|tue|wed|thu|fri|sat|sun)[a-z]*day"
                  r"|(\d{1,2})/(\d{1,2})"
                  r"|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?)\b", re.I)
_PLACE = re.compile(r"\b(?:in|at|to)\s+((?:the\s+)?[A-Z][\w']*(?:\s+(?:[A-Z][\w']*|\d+))*)")
_LEAD = re.compile(r"^(?:(?:a |friendly |quick )?reminder(?: that)?[:,!-]?\s*|(?:hey |yo )?(?:everyone|guys|brothers|all)[,!:]\s*"
                   r"|(?:we will have|we'll have|we have|we're having|there will be|there is|don't forget(?: about)?|please (?:come|show up) (?:to|for))\s+)",
                   re.I)
_CUT = re.compile(r"\s+(?:is|are|will|starts?|begins?|at|in|on|tonight|today|tomorrow|this|next|from)\b|[,.!:;(]", re.I)
_SKIP = {"the", "a", "an", "and", "of", "for", "pma", "meeting", "at", "in"}


def _clock(m, context: str) -> time | None:
    word, h1, m1, ap1, h2, ap2, h3 = m.groups()
    if word:
        return time(12) if word.lower() == "noon" else time(0)
    hour, minute, ap = (int(h1), int(m1), ap1) if h1 else (int(h2), 0, ap2) if h2 else (int(h3), 0, None)
    if hour > 23 or minute > 59:
        return None
    if ap:
        hour = hour % 12 + (12 if ap.lower().startswith("p") else 0)
    elif hour < 12:
        # Chapter events are afternoons and evenings unless the post says morning
        morning = re.search(r"\bmorning\b", context, re.I) and hour >= 6
        hour = hour if morning else hour + 12
    return time(hour, minute)


def _day(m, posted: date) -> date | None:
    tonight, tomorrow, weekday, mo, dy, month, mday = m.groups()
    if tonight:
        return posted
    if tomorrow:
        return posted + timedelta(days=1)
    if weekday:
        return posted + timedelta(days=(WEEKDAYS.index(weekday[:3].lower()) - posted.weekday()) % 7)
    try:
        if mo:
            d = date(posted.year, int(mo), int(dy))
        else:
            d = date(posted.year, MONTHS.index(month[:3].lower()) + 1, int(mday))
    except ValueError:
        return None
    return d if d >= posted - timedelta(days=30) else d.replace(year=d.year + 1)


def _title(sentence: str, start: int) -> str:
    head = sentence[:start]
    while True:
        stripped = _LEAD.sub("", head, count=1).strip()
        if stripped == head:
            break
        head = stripped
    head = _CUT.split(head, maxsplit=1)[0].strip()
    head = re.sub(r"^(?:the|our)\s+", "", head, flags=re.I)
    words = head.split()
    if not words or len(words) > 5:
        return "PMA event"
    name = " ".join(words)
    return name[0].upper() + name[1:] if name.lower().startswith("pma") else f"PMA {name}"


def find_event(post: Post) -> Event | None:
    """The first time a post mentions, as an event, or None."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n", post.text):
        t = _TIME.search(sentence)
        if not t:
            continue
        when = _clock(t, sentence)
        if when is None:
            continue
        d = _DAY.search(sentence)
        day = _day(d, post.at.date()) if d else post.at.date()
        if day is None:
            continue
        start = datetime.combine(day, when, tzinfo=post.at.tzinfo)
        if start < post.at - timedelta(hours=1):
            continue  # a time with no day that has already passed isn't an upcoming event
        first = min(t.start(), d.start()) if d else t.start()
        place = _PLACE.search(sentence, t.end()) or _PLACE.search(sentence)
        where = re.sub(r"^the\s+", "", place.group(1)) if place else ""
        return Event(_title(sentence, first), start, start + timedelta(hours=1), False, where)
    return None


def _words(title: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 2 and w not in _SKIP}


def announced(posts: list[Post], known: list[Event], first_day: date, last_day: date) -> list[Event]:
    """Events from announcements between first_day and last_day that the calendar doesn't already have."""
    found: list[Event] = []
    for post in sorted(posts, key=lambda p: p.at):
        ev = find_event(post)
        if not ev or not first_day <= ev.start.date() <= last_day:
            continue
        same = lambda e: abs(e.start - ev.start) <= timedelta(hours=1) and (
            _words(e.title) & _words(ev.title) or e in found)
        if any(same(e) for e in known + found):
            continue  # already on the calendar, or a repeat reminder
        found.append(ev)
    return sorted(found, key=lambda e: e.start)
