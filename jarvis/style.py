"""Jarvis's voice: a clean notification layout and a spoken version for Siri."""
import re
from datetime import date, datetime

GREETING = {range(0, 12): "Good morning", range(12, 17): "Good afternoon", range(17, 24): "Good evening"}


def _greeting(hour: int) -> str:
    return next(text for hours, text in GREETING.items() if hour in hours)


def _clock(dt: datetime) -> str:
    text = dt.strftime("%I:%M %p").lstrip("0")
    return text.replace(":00", "")  # 4:00 PM -> 4 PM


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def clean_course(title: str) -> str:
    """'Homework 7 [HIST210.001.FA26]' -> 'Homework 7 · HIST 210'."""
    def short(m):
        code = re.match(r"([A-Z]+)\s*(\d+)", m.group(1))
        return f" · {code.group(1)} {code.group(2)}" if code else ""
    return re.sub(r"\s*\[([^\]]+)\]", short, title).strip()


def clean_title(title: str) -> str:
    return re.sub(r"^NO CLASS:\s*", "", title).strip()


def where(location: str) -> str:
    """A room name, 'online' for meeting links, or nothing."""
    loc = (location or "").strip()
    if not loc:
        return ""
    if "http" in loc.lower() or "zoom" in loc.lower() or "teams" in loc.lower():
        room = re.split(r"https?://|\n|;", loc)[0].strip(" ,;-")
        return room if room and "zoom" not in room.lower() else "online"
    return loc


def _event_line(ev) -> str:
    when = "All day" if ev.all_day else _clock(ev.start)
    place = where(ev.location)
    return f"{when} — {clean_title(ev.title)}" + (f" · {place}" if place else "")


def _short_day(d: date, today: date) -> str:
    return "Tomorrow" if (d - today).days == 1 else d.strftime("%a")


def notification(today: date, now: datetime, weather: dict | None, events, coming, due, address: str, night=None,
                 pma=None, sports=None, insta=None, insta_expired=False) -> tuple[str, str]:
    """Returns (title, body) for the push notification."""
    title = f"{_greeting(now.hour)}, {address}"
    lines = [f"{today:%A}, {today:%B} {_ordinal(today.day)}"]
    if weather:
        lines.append(f"{weather['temp']}° now · {weather['sky']} · H {weather['high']}° L {weather['low']}°"
                     + (f" · {weather['rain']}% rain" if weather["rain"] >= 30 else ""))

    lines += ["", "▸ TODAY"]
    lines += [f"  {_event_line(ev)}" for ev in events] or ["  Nothing scheduled"]

    if coming:
        lines += ["", "▸ AHEAD"]
        lines += [f"  {_short_day(d, today)}, {_event_line(ev)}" for d, ev in coming]

    if due:
        lines += ["", "▸ DUE"]
        for a in due:
            days = (a.due.date() - today).days
            day = "Today" if days == 0 else _short_day(a.due.date(), today)
            lines.append(f"  {day} — {clean_course(a.title)}")

    if night:
        lines += ["", "▸ OVERNIGHT"]
        for who, where, said in night.comments:
            lines.append(f"  {who} on {where}" + (f": “{said}”" if said else ""))
        dms = len(night.dms) + night.dm_unknown
        if dms:
            names = sorted(set(night.dms))
            lines.append(f"  {dms} Instagram message{'s' if dms != 1 else ''}" + (f" · {', '.join(names)}" if names else ""))
        for who, subject, said in night.emails[-8:]:
            lines.append(f"  ✉ {who} — {subject}")
            if said and not _within(said, subject):
                lines.append(f"     {_short(said, 100)}")
        if len(night.emails) > 8:
            lines.append(f"  + {len(night.emails) - 8} more emails")

    if pma:
        lines += ["", "▸ PMA"]
        lines += [f"  {_posted(p.at, today)} — {_short(p.text, 120)}" for p in pma]

    if insta or insta_expired:
        lines += ["", "▸ INSTAGRAM"]
        if insta_expired:
            lines.append("  Token expired. Ask Claude to renew it")
        lines += [f"  @{p.who} · {_posted(p.at, today)} — {_short(p.text, 160) or '(no caption)'}" for p in insta]

    scores, upcoming = sports or ([], [])
    if scores or upcoming:
        lines += ["", "▸ SPORTS"]
        lines += [f"  {g.result} · {g.us[0].upper() + g.us[1:]} {g.us_score}–{g.them_score} {g.them} · {g.competition}"
                  for g in scores]
        for g in upcoming:
            day = "Today" if g.at.date() == today else _short_day(g.at.date(), today)
            lines.append(f"  {day} {_clock(g.at)} — {_matchup(g)} · {g.competition}" + (f" · {g.broadcast}" if g.broadcast else ""))
    return title, "\n".join(lines)


def _matchup(g) -> str:
    us = g.us[0].upper() + g.us[1:] + (f" ({g.us_record})" if g.us_record else "")
    them = g.them + (f" ({g.them_record})" if g.them_record else "")
    return f"{us} {'at' if g.home is False else 'vs'} {them}"


def _say_clock(dt: datetime) -> str:
    """'7:30' in the afternoon and evening, '11 AM' in the morning."""
    return _clock(dt) if dt.hour < 12 else _clock(dt).removesuffix(" PM")


def _spoken_score(g) -> str:
    us, them = g.us_said or g.us, g.them_said or g.them
    high, low = max(g.us_score, g.them_score), min(g.us_score, g.them_score)
    if g.result == "D":
        return f"{us} drew {g.us_score or 'nil'} all with {them}"
    return f"{us} beat {them} {high} to {low}" if g.result == "W" else f"{us} lost {high} to {low} to {them}"


def _spoken_upcoming(upcoming, today: date) -> str:
    """'today, Dortmund play Bodo/Glimt at 3, and tonight A play B and C play D, both at 7:30'."""
    when = {}  # today / tonight / tomorrow -> time -> games
    for g in upcoming:
        days = (g.at.date() - today).days
        day = ("tonight" if g.at.hour >= 17 else "today") if days == 0 else "tomorrow" if days == 1 else f"on {g.at:%A}"
        when.setdefault(day, {}).setdefault(_say_clock(g.at), []).append(f"{g.us_said or g.us} play {g.them_said or g.them}")
    parts = []
    for day, times in when.items():
        said = [f"{games[0]} at {t}" if len(games) == 1 else f"{_join(games)}, {'both' if len(games) == 2 else 'all'} at {t}"
                for t, games in times.items()]
        parts.append(f"{day}{',' if not parts else ''} {_join(said)}")
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]


def spoken_sports(scores, upcoming, today: date) -> str:
    """'In sports, ...': one sentence for results, one for what's coming up."""
    results = _join([_spoken_score(g) for g in reversed(scores)])
    ahead = _spoken_upcoming(upcoming, today) if upcoming else ""
    if not results:
        return f"In sports, {ahead}." if ahead else ""
    return f"In sports, {results}." + (f" {ahead[0].upper() + ahead[1:]}." if ahead else "")


def _posted(at: datetime, today: date) -> str:
    days = (today - at.date()).days
    day = "Today" if days == 0 else "Yesterday" if days == 1 else f"{at:%a}"
    return f"{day} {_clock(at)}"


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _spoken_event(ev) -> str:
    name = clean_title(ev.title)
    return name if ev.all_day else f"{name} at {_clock(ev.start)}"


def spoken(today: date, weather: dict | None, events, coming, due, address: str, night=None, pma_news=None,
           sports=None, insta=None, insta_expired=False) -> str:
    """A single paragraph for Siri to read aloud, in the style of J.A.R.V.I.S."""
    # The greeting and the time are added by whoever speaks it (the alarm Shortcut or the HUD), since this text can be up to 15 minutes old by then
    parts = [f"Today is {today:%A} the {_ordinal(today.day)}."]
    if weather:
        w = f"It's currently {weather['temp']} degrees and {weather['sky']}, with a high of {weather['high']}."
        if weather["rain"] >= 50:
            w += " You may want an umbrella."
        parts.append(w)

    if not events:
        parts.append("Your schedule is clear today.")
    elif len(events) == 1:
        parts.append(f"You have one engagement today: {_spoken_event(events[0])}.")
    else:
        parts.append(f"You have {len(events)} engagements today: {_join([_spoken_event(e) for e in events])}.")

    if due:
        soonest = due[0]
        days = (soonest.due.date() - today).days
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"on {soonest.due:%A}"
        name = clean_course(soonest.title).replace(" · ", " for ")
        more = f", and {len(due) - 1} more this week" if len(due) > 1 else ""
        parts.append(f"{name} is due {when}{more}.")

    if night:
        parts.append(_spoken_night(night))

    if pma_news:  # announcements since 10:30 PM; the newest is read out
        text = _short(pma_news[0].text, 200).rstrip("…")
        parts.append(f"From PMA: {text}" + ("" if text[-1:] in ".!?" else "."))

    if insta_expired:
        parts.append("My Instagram access has expired, so I can't see new posts until it's renewed.")
    if insta:  # posts from the last 12 hours; the newest caption is read out
        p = insta[0]
        more = f", one of {len(insta)} new posts" if len(insta) > 1 else ""
        text = _short(p.text, 200).rstrip("…")
        said = f": {text}" + ("" if text[-1:] in ".!?" else ".") if text else "."
        parts.append(f"{p.who} posted on Instagram{more}{said}")

    if coming:
        d, ev = coming[0]
        when = "Tomorrow" if (d - today).days == 1 else f"On {d:%A}"
        parts.append(f"{when}, {_spoken_event(ev)}.")

    if sports and any(sports):
        parts.append(spoken_sports(*sports, today))

    parts.append("Shall I leave you to it?" if events or due else "Enjoy the day, " + address + ".")
    return " ".join(parts)


def _spoken_night(night) -> str:
    bits = []
    if night.comments:
        n = len(night.comments)
        where = night.comments[0][1]
        who, _, said = night.comments[0]
        first = f"{who} says: {said}" if said else f"the first from {who}"
        bits.append(f"{n} new comment{'s' if n != 1 else ''} in {where}. {first}")
    dms = len(night.dms) + night.dm_unknown
    if dms:
        names = sorted(set(night.dms))
        bits.append(f"{dms} Instagram message{'s' if dms != 1 else ''}" + (f" from {_join(names)}" if names else ""))
    said = [spoken_email(*e) for e in reversed(night.emails[-3:])]  # newest first
    more = len(night.emails) - len(said)
    if more:
        said.append(f"And {more} more email{'s' if more != 1 else ''}.")
    if not bits:
        return "Overnight, " + " ".join(said)
    return " ".join(["Overnight, " + ", and ".join(bits) + "."] + said)


def _within(part: str, whole: str) -> bool:
    words = lambda text: " " + " ".join(re.findall(r"\w+", text.lower())) + " "
    return words(part) in words(whole)


def spoken_email(who: str, subject: str, said: str) -> str:
    """'Avi Thaker wrote about Project kickoff: Great chatting with you all today.'"""
    topic = "" if subject == "(no subject)" else subject
    said = said.rstrip("…").strip()
    if said and said[-1] not in ".!?":
        said += "."
    if not said:
        return f"{who} wrote about {topic}." if topic else f"{who} sent an email."
    if topic and _within(said, topic):  # the sentence only repeats the subject
        return f"{who} wrote about {topic}."
    if not topic or _within(topic, said):  # the sentence already says what the subject does
        return f"{who} wrote: {said}"
    return f"{who} wrote about {topic}: {said}"


def hud(today: date, now: datetime, weather: dict | None, events, coming, due, address: str, voice: str, night=None,
        pma=None, pma_since=None, sports=None, insta=None) -> dict:
    """Everything the HUD page shows, as plain JSON-friendly data."""
    def ev(e):
        return {"time": "All day" if e.all_day else _clock(e.start),
                "end": "" if e.all_day else _clock(e.end),
                "title": clean_title(e.title), "place": where(e.location),
                "start_at": e.start.isoformat(timespec="minutes"), "all_day": e.all_day}

    scores, upcoming = sports or ([], [])

    def item(a):
        days = (a.due.date() - today).days
        title, _, course = clean_course(a.title).partition(" · ")
        return {"day": "Today" if days == 0 else _short_day(a.due.date(), today),
                "days": days, "title": title, "course": course,
                "time": "" if a.all_day else _clock(a.due)}

    return {
        "generated": now.isoformat(timespec="minutes"),
        "date": today.isoformat(),
        "address": address,
        "weather": weather,
        "today": [ev(e) for e in events],
        "ahead": [{"day": _short_day(d, today), **ev(e)} for d, e in coming],
        "due": [item(a) for a in due],
        "overnight": {
            "comments": [{"who": w, "where": p, "said": t} for w, p, t in night.comments],
            "dms": len(night.dms) + night.dm_unknown,
            "dm_from": sorted(set(night.dms)),
            "emails": [{"from": w, "subject": t, "snippet": _short(s, 90), "url": night.links.get(t.lower(), ""),
                        **({"at": night.times[t.lower()].isoformat(timespec="minutes")} if t.lower() in night.times else {})}
                       for w, t, s in night.emails[-4:]],
            "more_emails": max(0, len(night.emails) - 4),
        } if night else None,
        "pma": [{"when": _posted(p.at, today), "text": _short(p.text, 180),
                 "new": bool(pma_since and p.at >= pma_since)} for p in pma or []],
        "insta": [{"who": p.who, "when": _posted(p.at, today), "text": _short(p.text, 220), "url": p.url}
                  for p in insta] if insta is not None else None,
        "sports": {
            "scores": [{"at": g.at.isoformat(timespec="minutes"), "comp": g.competition, "us": g.us, "them": g.them,
                        "home": g.home, "score": [g.us_score, g.them_score], "res": g.result,
                        "say": [g.us_said or g.us, g.them_said or g.them]} for g in scores],
            "upcoming": [{"at": g.at.isoformat(timespec="minutes"), "comp": g.competition, "us": g.us, "them": g.them,
                          "home": g.home, "rec": [g.us_record, g.them_record], "tv": g.broadcast,
                          "say": [g.us_said or g.us, g.them_said or g.them]} for g in upcoming],
        },
        "voice": voice,
    }
