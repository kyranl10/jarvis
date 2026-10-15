"""Overnight emails, Facebook comments and Instagram messages, read from a "Jarvis" label in Gmail.

Meta doesn't let outside apps read personal DMs or group posts, but it does email you about them.
Uses Gmail IMAP with an app password (free): GMAIL_ADDRESS and GMAIL_APP_PASSWORD.
A Gmail filter skips the inbox and files those emails under the "Jarvis" label, which is what this reads.
"""
import email
import html
import imaplib
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from zoneinfo import ZoneInfo

GMAIL_LABEL = "Jarvis"
NIGHT_STARTS = time(22, 30)  # "overnight" means since 10:30 PM the night before


@dataclass
class Overnight:
    comments: list[tuple[str, str, str]] = field(default_factory=list)  # (who, where, what they said)
    dms: list[str] = field(default_factory=list)  # Instagram senders, one per message email
    dm_unknown: int = 0  # "you have unread messages" reminders that don't say who
    emails: list[tuple[str, str, str]] = field(default_factory=list)  # (from, subject, first sentence) forwarded from Outlook

    def __bool__(self) -> bool:
        return bool(self.comments or self.dms or self.dm_unknown or self.emails)


def since(now: datetime) -> datetime:
    start = datetime.combine(now.date(), NIGHT_STARTS, tzinfo=now.tzinfo)
    return start if now >= start else start - timedelta(days=1)


def _header(msg, name: str) -> str:
    return str(make_header(decode_header(msg.get(name, "")))).strip()


def _text(msg) -> str:
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True) or b""
            return payload.decode(part.get_content_charset() or "utf-8", "replace")
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_content_type() == "text/html":
            page = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
            page = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", page)
            page = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", page)  # keep line breaks for snippet()
            return html.unescape(re.sub(r"<[^>]+>", " ", page))
    return ""


_COMMENT = re.compile(r"^(?P<who>.+?) (?:commented|replied) (?:on|to) .*?(?:in|on) (?P<where>[^.]+?)\.?$", re.I)
_QUOTE = re.compile(r"[\"“](.+?)[\"”]", re.S)
_DM = re.compile(r"^(?P<who>@?[\w.]+) (?:sent you a message|sent you \d+ messages|messaged you)", re.I)


_REPLY_PREFIX = re.compile(r"^\s*(?:(?:re|fw|fwd|aw|wg|sv)\s*(?:\[\d+\])?\s*:\s*)+", re.I)
_QUOTED_HEADER = re.compile(r"^(?:-{2,}\s*(?:original message|forwarded message)\s*-{2,}|_{8,}|(?:from|发件人|de|von)\s*:\s)", re.I)
_SIGN_OFF = re.compile(r"^(?:--\s*$|sent from my |get outlook for |sent from outlook|sent from mail for )", re.I)
_BANNER = re.compile(r"^\[?(?:you don't often get email from|external email|\[?external\]?\s*[:\-]|caution\s*:|warning\s*:"
                     r"|this (?:email|message) (?:originated|came) from outside|some people who received this message)", re.I)
_SALUTATION = re.compile(r"^(?:hi|hello|hey|dear|good (?:morning|afternoon|evening)|greetings)\b[^.!?]{0,40}[,!]?$|^.{1,40},$", re.I)
_URL = re.compile(r"<?(?:https?://|mailto:|www\.)[^\s>]*>?", re.I)
_SENTENCE = re.compile(r"^(.+?[.!?]+)(?=[\"”')\]]*(?:\s+[A-Z0-9\"“'(]|\s*$))", re.S)


def clean_subject(subject: str) -> str:
    """'RE: FW: Project kickoff' -> 'Project kickoff'."""
    return _REPLY_PREFIX.sub("", subject).strip()


def person(name: str) -> str:
    """'Nie, Jingping' -> 'Jingping Nie'; 'avi.thaker' -> 'Avi Thaker'."""
    name = name.strip().strip("'\"").strip()
    if re.fullmatch(r"[^,\s]+,\s*[^,]+", name):
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}"
    if " " not in name and re.search(r"[a-z][._][a-z]", name, re.I):
        name = " ".join(w[:1].upper() + w[1:] for w in re.split(r"[._]+", name) if w)
    return name


def snippet(body: str, limit: int = 160) -> str:
    """The first real sentence of an email, without quoted replies, signatures, banners or links."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept, skipping = [], False
    for i, raw in enumerate(lines):
        line = raw.strip()
        if skipping:  # the From/Sent/To/Subject block of a forward with nothing written above it
            skipping = bool(line)
            continue
        if _SIGN_OFF.match(line):
            break
        after = lines[i + 1].strip() if i + 1 < len(lines) else ""
        reply = re.match(r"^On\b", line) and ("wrote:" in line or after.endswith("wrote:"))
        if reply or _QUOTED_HEADER.match(line):
            if any(kept):  # everything from here down is the conversation being replied to
                break
            skipping = not reply and not line.startswith("_")
            continue
        if line.startswith(">") or _BANNER.match(line):
            continue
        if not any(kept) and _SALUTATION.match(line):
            continue
        kept.append(_URL.sub("", line))
    text = re.sub(r"\s+", " ", " ".join(kept)).strip(" -–—:;,")
    if not re.search(r"[^\W\d_]", text):
        return ""
    m = _SENTENCE.match(text)
    first = (m.group(1) if m else text).strip()
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


_TEAMS_SENDER = re.compile(r"\s+in\s+(?:Microsoft\s+)?Teams$", re.I)
_TEAMS_SUBJECT = re.compile(r"^.+ (?:sent (?:you )?(?:a )?(?:new )?messages?|mentioned you|replied(?: to .*)?)$", re.I)


def classify(sender: str, subject: str, body: str, work: str = "") -> tuple[str, tuple] | None:
    """work: the employer's name when the email was sent to the work address, else ""."""
    name, address = parseaddr(sender)
    if _TEAMS_SENDER.search(name):  # 'LevinW in Teams' / 'LevinW sent a message' -> the message itself
        who = _TEAMS_SENDER.sub("", name).strip()
        team = f"{work} Teams" if work else "Teams"
        return "email", (f"{who} on {team}", "(no subject)" if _TEAMS_SUBJECT.match(subject) else clean_subject(subject),
                         snippet(body))
    sender = sender.lower()
    if "facebookmail.com" in sender:
        m = _COMMENT.match(subject)
        if not m:
            return None
        quote = _QUOTE.search(body)
        said = re.sub(r"\s+", " ", quote.group(1)).strip() if quote else ""
        return "comment", (m.group("who").strip(), m.group("where").strip(), said[:200])
    if "instagram.com" in sender:
        m = _DM.match(subject)
        if m:
            return "dm", (m.group("who").lstrip("@"),)
        if "message" in subject.lower():
            return "dm_unknown", ()
        return None
    # Anything else in the label was forwarded from Outlook
    who = person(name or address.split("@")[0]) or "Unknown"
    return "email", (f"{who} at {work}" if work else who, clean_subject(subject) or "(no subject)", snippet(body))


_BULK_SENDER = re.compile(r"^(?:no[-_.]?reply|do[-_.]?not[-_.]?reply|massmail|mailer-daemon|postmaster)\b|@massmail\.", re.I)
_NOISE_SUBJECT = re.compile(r"^(?:test\d*|testing|diagnostics? report|confirm email: canvas\b.*|security alert: new email address added|undeliverable\b.*|delivery status notification\b.*)$", re.I)


def is_noise(sender: str, subject: str, headers: dict | None = None, owner: str = "") -> bool:
    """Mass mail, mailing lists, bounces, test emails and things you sent yourself.
    owner: your first name, so your own forwards from other addresses are skipped too."""
    name, address = parseaddr(sender)
    headers = {k.lower(): (v or "").lower() for k, v in (headers or {}).items()}
    if _BULK_SENDER.search(address):
        return True
    # Canvas course mail is sent like a mailing list but is real coursework, so only its headers are ignored
    canvas = address.lower().endswith("@instructure.com")
    if not canvas and (headers.get("list-unsubscribe") or headers.get("list-id")
                       or headers.get("precedence") in ("bulk", "list", "junk")):
        return True
    if _NOISE_SUBJECT.match(clean_subject(subject)):
        return True
    who = person(name or address.split("@")[0]).split()
    return bool(owner and who and who[0].lower() == owner.lower())


def collect(messages, start: datetime) -> Overnight:
    """messages: (sender, subject, received datetime, body) tuples, plus the employer's name
    as a fifth item when the email was sent to the work address."""
    found = Overnight()
    for sender, subject, received, body, *work in messages:
        if received < start:
            continue
        kind = classify(sender, subject, body, work[0] if work else "")
        if not kind:
            continue
        if kind[0] == "comment":
            found.comments.append(kind[1])
        elif kind[0] == "dm":
            found.dms.append(kind[1][0])
        elif kind[0] == "email":
            # The same subject twice (a resend, a reply) shows once, as the newest
            found.emails = [e for e in found.emails if e[1].lower() != kind[1][1].lower()] + [kind[1]]
        else:
            found.dm_unknown += 1
    return found


def overnight(address: str, app_password: str, now: datetime, work_domain: str = "", work_name: str = "",
              owner: str = "", start: datetime | None = None) -> Overnight:
    """Everything new since `start` (default: 10:30 last night)."""
    start = start or since(now)
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        imap.login(address, app_password)
        imap.select(GMAIL_LABEL, readonly=True)  # never marks anything as read
        day = (start.date() - timedelta(days=1)).strftime("%d-%b-%Y")
        messages = []
        _, data = imap.search(None, f'(SINCE "{day}")')
        for num in data[0].split()[-100:]:
            _, parts = imap.fetch(num, "(BODY.PEEK[])")
            msg = email.message_from_bytes(parts[0][1])
            received = parsedate_to_datetime(msg.get("Date")).astimezone(now.tzinfo)
            if address.lower() in _header(msg, "From").lower():
                continue  # your own sent mail that a filter also labelled
            if is_noise(_header(msg, "From"), _header(msg, "Subject"),
                        {h: msg.get(h, "") for h in ("List-Unsubscribe", "List-Id", "Precedence")}, owner):
                continue
            to = " ".join(_header(msg, h) for h in ("To", "Cc", "Delivered-To", "X-Forwarded-For")).lower()
            work = work_name if work_domain and "@" + work_domain in to else ""
            messages.append((_header(msg, "From"), _header(msg, "Subject"), received, _text(msg), work))
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return collect(sorted(messages, key=lambda m: m[2]), start)
