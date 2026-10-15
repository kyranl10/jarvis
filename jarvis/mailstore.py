"""The mail triage's data file, kept encrypted because this repo is public.

The scheduled mail triage writes what it flagged to data/mail.enc, sealed with a key that lives only in
the GitHub secret MAIL_KEY (for the refresh) and in the project's private files (for the triage task).
The refresh decrypts it and publishes the result to the private ntfy "-mail" topic the HUD reads.

  python -m jarvis.mailstore keygen          print a new key
  python -m jarvis.mailstore show            print the decrypted data
  python -m jarvis.mailstore seal FILE       encrypt a JSON file into data/mail.enc
  python -m jarvis.mailstore merge FILE      add a triage run's results: {"seen": [thread ids], "flagged": [items]}
  python -m jarvis.mailstore sync FILE       mirror Jarvis Mail decisions: [{"id", "status", "subject"?, "at"?}]

merge and sync also drop what's past its time (seen ids and flagged items after 4 days, dismissals after 3),
set "updated", and print whether anything changed, so the tasks know whether to commit.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent.parent / "data"
SEALED = DATA / "mail.enc"
PLAIN = DATA / "mail.json"  # the old unencrypted file, read only if no sealed one exists
KEY_FILE = Path(os.getenv("MAIL_KEY_FILE", "/mnt/project-files/.secrets/jarvis-mail.key"))


def key() -> bytes | None:
    value = os.getenv("MAIL_KEY", "").strip()
    if not value and KEY_FILE.is_file():
        value = KEY_FILE.read_text(encoding="utf-8").strip()
    return value.encode() if value else None


def read(path: Path | None = None) -> dict | None:
    """The triage data, or None if it's missing, unreadable or the key is absent or wrong."""
    if path is None:  # the sealed file, or the old plain one while the switch-over is under way
        return read(SEALED) if SEALED.exists() and read(SEALED) is not None else read(PLAIN)
    try:
        raw = path.read_bytes()
        if path.suffix == ".enc":
            k = key()
            if not k:
                return None
            from cryptography.fernet import Fernet  # imported here so a run without it still reads mail.json
            raw = Fernet(k).decrypt(raw)
        data = json.loads(raw.decode("utf-8"))
    except Exception:  # missing file, bad JSON, wrong key (InvalidToken), or cryptography not installed
        return None
    return data if isinstance(data, dict) else None


def seal(data: dict, path: Path | None = None) -> None:
    from cryptography.fernet import Fernet
    path = path or SEALED
    k = key()
    if not k:
        raise SystemExit("No MAIL_KEY set and no key file found.")
    path.write_bytes(Fernet(k).encrypt(json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")) + b"\n")


TZ = ZoneInfo("America/New_York")
KEEP_DAYS = 4       # seen ids and flagged items
DISMISSED_DAYS = 3  # emails dismissed in Jarvis Mail stay restorable, and listed on the HUD, this long


def thread_time(thread_id: str) -> datetime | None:
    """When a Gmail thread started: its hex id is a millisecond timestamp shifted left 20 bits."""
    try:
        return datetime.fromtimestamp((int(thread_id.split("-")[0], 16) >> 20) / 1000, timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def _at(item: dict) -> datetime | None:
    try:
        at = datetime.fromisoformat(item["at"])
        return at if at.tzinfo else None
    except (KeyError, TypeError, ValueError):
        return None


def tidy(data: dict, now: datetime) -> dict:
    keep, gone = now - timedelta(days=KEEP_DAYS), now - timedelta(days=DISMISSED_DAYS)
    data["seen"] = [i for i in dict.fromkeys(data.get("seen", [])) if (thread_time(i) or now) >= keep]
    data["flagged"] = [i for i in data.get("flagged", []) if (_at(i) or now) >= keep]
    data["dismissed"] = [d for d in data.get("dismissed", []) if (_at(d) or now) >= gone]
    return data


def merge(data: dict, run: dict, now: datetime) -> dict:
    """A triage run's new seen ids and flagged items (an item with an existing id replaces it, keeping its status)."""
    data = dict(data)
    data["seen"] = list(data.get("seen", [])) + [i for i in run.get("seen", []) if i not in data.get("seen", [])]
    old = {i.get("id"): i for i in data.get("flagged", [])}
    for item in run.get("flagged", []):
        if item.get("id") in old and "status" in old[item["id"]]:
            item = {**item, "status": old[item["id"]]["status"]}
        old[item.get("id")] = item
    data["flagged"] = list(old.values())
    return tidy(data, now)


def sync(data: dict, decisions: list[dict], now: datetime) -> dict:
    """Jarvis Mail's statuses: denied or done take a flagged item off the HUD; a denied email that was never flagged
    is listed under the HUD Mail page's Dismissed tab; anything else (open, working, restored) clears both."""
    data = dict(data)
    flagged = {i.get("id"): i for i in data.get("flagged", [])}
    dismissed = [d for d in data.get("dismissed", [])]
    for d in decisions:
        status, item = d.get("status"), flagged.get(d.get("id"))
        dismissed = [x for x in dismissed if x.get("id") != d.get("id")]
        if item is not None:
            if status in ("denied", "done"):
                item["status"] = status
            else:
                item.pop("status", None)
        elif status == "denied" and d.get("subject"):
            dismissed.append({"id": d["id"], "subject": d["subject"], "at": d.get("at") or now.isoformat(timespec="seconds")})
    data["dismissed"] = dismissed
    return tidy(data, now)


def _apply(change, arg: str) -> None:
    before = read(SEALED) or read(PLAIN) or {"seen": [], "flagged": [], "dismissed": []}
    now = datetime.now(TZ)
    after = change(json.loads(json.dumps(before)), json.loads(Path(arg).read_text(encoding="utf-8")), now)
    if {k: v for k, v in after.items() if k != "updated"} == {k: v for k, v in before.items() if k != "updated"}:
        print("unchanged")
        return
    after["updated"] = now.isoformat(timespec="seconds")
    seal(after)
    print(f"changed: {len(after['flagged'])} flagged, {len(after['dismissed'])} dismissed, {len(after['seen'])} seen")


def main(argv: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = argv[0] if argv else ""
    if cmd == "keygen":
        from cryptography.fernet import Fernet
        print(Fernet.generate_key().decode())
    elif cmd == "show":
        data = read(SEALED)
        if data is None:
            raise SystemExit("Couldn't read data/mail.enc (missing file, or no or wrong key).")
        print(json.dumps(data, ensure_ascii=False, indent=1))
    elif cmd == "merge" and len(argv) == 2:
        _apply(merge, argv[1])
    elif cmd == "sync" and len(argv) == 2:
        _apply(sync, argv[1])
    elif cmd == "seal" and len(argv) == 2:
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("flagged", []), list):
            raise SystemExit("Expected {updated, seen, flagged, dismissed}.")
        seal(data)
        print(f"Sealed {len(data.get('flagged', []))} flagged items into {SEALED.relative_to(DATA.parent)}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
