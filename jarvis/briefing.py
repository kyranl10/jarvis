"""Morning briefing: python -m jarvis.briefing [--dry-run] [--quiet]"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta

from . import band, calendar_mail, flagged, instagram, mailstore, sports, style
from .calendar_source import coming_up, fetch_ics, label, parse_events
from .canvas import due_soon
from .config import Config
from .inbox import clean_subject, overnight, since
from .pma import announced, fetch_posts
from .notify import publish_quietly, push
from .weather import forecast


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Send Jarvis's morning briefing.")
    parser.add_argument("--dry-run", action="store_true", help="print the briefing instead of sending it")
    parser.add_argument("--quiet", action="store_true", help="refresh the HUD and spoken briefing without a notification")
    args = parser.parse_args()

    cfg = Config.load()
    now = datetime.now(cfg.tz)
    today = now.date()
    address = os.getenv("JARVIS_ADDRESS", "sir")

    ok = {}  # source -> whether it answered this run, for the HUD's health strip
    try:
        weather = forecast(cfg.latitude, cfg.longitude, str(cfg.tz))
        ok["weather"] = True
    except Exception as exc:  # weather is nice to have, not essential
        print(f"Weather unavailable: {exc.__class__.__name__}")
        weather = None
        ok["weather"] = False

    feeds = []  # (calendar name, ICS text) for the chat page's calendar snapshot
    events, coming = [], []
    if cfg.ics_url:
        try:
            ics = fetch_ics(cfg.ics_url)
            events = parse_events(ics, today, cfg.tz)
            coming = coming_up(ics, today, cfg.tz)
            feeds.append(("UNC", ics))
            ok["calendar"] = True
        except Exception as exc:  # the rest of the refresh still goes out without it
            print(f"Calendar unavailable: {exc.__class__.__name__}")
            ok["calendar"] = False
    else:
        print("No OUTLOOK_ICS_URL set, so the briefing has no calendar yet.")
    if cfg.work_ics_url:  # the work calendar, each event labelled with the employer's name
        try:
            ics = fetch_ics(cfg.work_ics_url)
            feeds.append((cfg.work_name, ics))
            events = sorted(events + [label(e, cfg.work_name) for e in parse_events(ics, today, cfg.tz)],
                            key=lambda e: (not e.all_day, e.start))
            coming = sorted(coming + [(d, label(e, cfg.work_name)) for d, e in coming_up(ics, today, cfg.tz)],
                            key=lambda p: (p[0], not p[1].all_day, p[1].start))
            ok["work"] = True
        except Exception as exc:  # the briefing still goes out without it
            print(f"Work calendar unavailable: {exc.__class__.__name__}")
            ok["work"] = False

    groupspot = os.getenv("GROUPSPOT_ICAL_URL", "").strip()
    if groupspot:  # Marching Tar Heels rehearsals and games, unless already on the calendar
        seen = {(e.title.lower(), e.start) for e in events + [e for _, e in coming]}
        try:
            band_events = band.build(groupspot, today, cfg.tz, strict=True)
            ok["band"] = True
        except Exception:  # band.build already logged it
            band_events = []
            ok["band"] = False
        for e in band_events:
            if (e.title.lower(), e.start) in seen:
                continue
            if e.start.date() == today:
                events.append(e)
            else:
                coming.append((e.start.date(), e))
        events.sort(key=lambda e: (not e.all_day, e.start))
        coming.sort(key=lambda p: (p[0], not p[1].all_day, p[1].start))

    gmail, gmail_pw = os.getenv("GMAIL_ADDRESS", "").strip(), os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if gmail and gmail_pw and feeds:  # the next 45 days, filed privately in Gmail for the Jarvis chat page
        try:
            sources = [(name, calendar_mail.window(text, today, cfg.tz)) for name, text in feeds]
            if groupspot:
                sources.append(("Marching Tar Heels", band.build(groupspot, today, cfg.tz, days=calendar_mail.DAYS)))
            filed = calendar_mail.deliver(gmail, gmail_pw, calendar_mail.snapshot(sources, now))
            print("Calendar snapshot " + ("updated" if filed else "unchanged"))
        except Exception as exc:  # never print the exception text: it can contain a feed URL
            print(f"Calendar snapshot unavailable: {exc.__class__.__name__}")

    canvas_url = os.getenv("CANVAS_ICS_URL", "").strip()
    due = []
    if canvas_url:
        try:
            due = due_soon(canvas_url, today, cfg.tz)
            ok["canvas"] = True
        except Exception as exc:  # the briefing still goes out without it
            print(f"Canvas unavailable: {exc.__class__.__name__}")
            ok["canvas"] = False

    night = recent = None  # since last night for the spoken briefing; the last 24 hours for the HUD
    if gmail and gmail_pw:
        try:
            known = {i["subject"].lower() for i in (flagged.load(now) or {}).get("flagged", [])} | flagged.dismissed(now)
            night = overnight(gmail, gmail_pw, now, cfg.work_domain, cfg.work_name, owner=cfg.name)
            recent = overnight(gmail, gmail_pw, now, cfg.work_domain, cfg.work_name, owner=cfg.name,
                               start=now - timedelta(hours=24))
            for found in (night, recent):  # emails already under the HUD's "Needs you" aren't repeated
                found.emails = [e for e in found.emails if clean_subject(e[1]).lower() not in known]
            ok["gmail"] = True
        except Exception as exc:  # the briefing still goes out without it
            print(f"Gmail unavailable: {exc.__class__.__name__}")
            ok["gmail"] = False

    posts = []
    bot = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    for channel in filter(None, os.getenv("DISCORD_CHANNEL_ID", "").replace(" ", "").split(",")):
        try:
            posts += fetch_posts(bot, channel, cfg.tz) if bot else []
            ok.setdefault("discord", bool(bot))
        except Exception as exc:  # the briefing still goes out without it
            print(f"Discord unavailable: {exc.__class__.__name__}")
            ok["discord"] = False
    posts.sort(key=lambda p: p.at, reverse=True)
    # Events announced in PMA's Discord that aren't on the calendar yet
    extra = announced(posts, events + [e for _, e in coming], today, today + timedelta(days=3))
    events = sorted(events + [e for e in extra if e.start.date() == today], key=lambda e: (not e.all_day, e.start))
    coming = sorted(coming + [(e.start.date(), e) for e in extra if e.start.date() > today],
                    key=lambda p: (p[0], not p[1].all_day, p[1].start))
    pma = [p for p in posts if p.at >= now - timedelta(days=3)][:3]
    pma_news = [p for p in pma if p.at >= since(now)]

    insta_expired = False
    insta = None  # None hides the HUD's Instagram panel until a token is set
    ig_user, ig_token = os.getenv("INSTAGRAM_USER_ID", "").strip(), os.getenv("INSTAGRAM_TOKEN", "").strip()
    for who in filter(None, os.getenv("INSTAGRAM_WATCH", "").replace(" ", "").replace("@", "").split(",")):
        try:
            if ig_user and ig_token:
                insta = (insta or []) + instagram.fetch_posts(ig_user, ig_token, who, cfg.tz)
                ok.setdefault("instagram", True)
        except instagram.TokenExpired:
            insta_expired = True
            ok["instagram"] = False
            print("Instagram token expired.")
        except Exception as exc:  # the briefing still goes out without it
            print(f"Instagram unavailable for {who}: {exc.__class__.__name__}")
            ok["instagram"] = False
    if insta is not None:
        insta = sorted((p for p in insta if p.at >= now - timedelta(hours=24)), key=lambda p: p.at, reverse=True)
    insta_12h = [p for p in insta or [] if p.at >= now - timedelta(hours=12)]  # the briefing; the HUD shows a full day

    try:
        games = sports.fetch(now, hours=72)
        ok["sports"] = True
    except Exception as exc:  # the briefing still goes out without it
        print(f"Sports unavailable: {exc.__class__.__name__}")
        games = ([], [])
        ok["sports"] = False
    day_of_games = sports.within(*games, now, hours=24)

    title, body = style.notification(today, now, weather, events, coming, due, address, night, pma, day_of_games,
                                     insta_12h, insta_expired)
    voice = style.spoken(today, weather, events, coming, due, address, night, pma_news, day_of_games, insta_12h,
                         insta_expired)
    hud = style.hud(today, now, weather, events, coming, due, address, voice, recent, pma, since(now), games, insta)
    inbox = flagged.load(now)  # emails Jarvis flagged, for the HUD's Inbox panel
    if mailstore.SEALED.exists() or mailstore.PLAIN.exists():
        ok["mail"] = inbox is not None
        if inbox is None:
            print("Mail triage data unavailable (missing or wrong MAIL_KEY?)")
    # The HUD keeps a day of these, so it can show when each source last answered and flag stale ones
    hud["ok"] = sorted(k for k, v in ok.items() if v)
    hud["down"] = sorted(k for k, v in ok.items() if not v)
    if args.dry_run:  # only here: the Actions log of this public repo is public too
        print(title, body, "", "Spoken:", voice, sep="\n")
        return

    publish_quietly(voice, "-voice")  # read aloud by the iPhone Shortcut
    payload = json.dumps(hud, ensure_ascii=False)
    while len(payload.encode("utf-8")) > 3900 and len(hud["pma"]) > 1:
        hud["pma"].pop()
        payload = json.dumps(hud, ensure_ascii=False)
    while len(payload.encode("utf-8")) > 3900 and len(hud["insta"] or []) > 1:
        hud["insta"].pop()  # the oldest post goes first
        payload = json.dumps(hud, ensure_ascii=False)
    games = hud["sports"]
    while len(payload.encode("utf-8")) > 3900 and (games["scores"] or games["upcoming"]):
        # The oldest result or the furthest game goes first
        max((games["scores"], games["upcoming"]), key=len).pop()
        payload = json.dumps(hud, ensure_ascii=False)
    mail = hud["overnight"]["emails"] if hud["overnight"] else []
    while len(payload.encode("utf-8")) > 3900 and any(m["snippet"] for m in mail):
        next(m for m in mail if m["snippet"])["snippet"] = ""  # the oldest email's first sentence goes first
        payload = json.dumps(hud, ensure_ascii=False)
    while len(payload.encode("utf-8")) > 3900 and hud["overnight"] and hud["overnight"]["comments"]:
        hud["overnight"]["comments"].pop()
        payload = json.dumps(hud, ensure_ascii=False)
    while len(payload.encode("utf-8")) > 3900 and mail:
        mail.pop(0)
        hud["overnight"]["more_emails"] += 1
        payload = json.dumps(hud, ensure_ascii=False)
    while len(payload.encode("utf-8")) > 3900 and (hud["ahead"] or hud["due"]):
        # ntfy turns messages over 4 KB into file attachments, which the HUD can't read
        (hud["ahead"] or hud["due"]).pop()
        payload = json.dumps(hud, ensure_ascii=False)
    publish_quietly(payload, "-hud")  # shown by the HUD page
    if inbox is not None:
        publish_quietly(json.dumps(inbox, ensure_ascii=False), "-mail")
    if args.quiet:
        print("HUD and spoken briefing refreshed.")
        return
    push(title, body, tags="large_blue_circle")
    print("Sent to your phone.")


if __name__ == "__main__":
    main()
