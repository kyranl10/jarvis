import json
from datetime import datetime
from zoneinfo import ZoneInfo

from jarvis import flagged

NOW = datetime(2026, 10, 14, 14, 0, tzinfo=ZoneInfo("America/New_York"))


def item(at, level="fyi", subject="Hi"):
    return {"at": at, "from": "Prof. Rivera", "subject": subject, "why": "Class news", "level": level, "url": ""}


def test_keeps_recent_and_orders_action_first(tmp_path):
    path = tmp_path / "mail.json"
    path.write_text(json.dumps({"updated": "2026-10-14T13:00:00-04:00", "flagged": [
        item("2026-10-14T09:00:00-04:00", "fyi", "Newest fyi"),
        item("2026-10-13T09:00:00-04:00", "act", "Older action"),
        item("2026-10-10T09:00:00-04:00", "act", "Too old"),
        {"subject": "no date"},
    ]}))
    out = flagged.load(NOW, path)
    assert [i["subject"] for i in out["flagged"]] == ["Older action", "Newest fyi"]


def test_trims_to_fit_ntfy(tmp_path):
    path = tmp_path / "mail.json"
    path.write_text(json.dumps({"flagged": [item("2026-10-14T09:00:00-04:00", subject="x" * 300) for _ in range(30)]}))
    out = flagged.load(NOW, path)
    assert 0 < len(out["flagged"]) < 30
    assert len(json.dumps(out).encode()) <= flagged.LIMIT


def test_missing_file(tmp_path):
    assert flagged.load(NOW, tmp_path / "nope.json") is None


def test_plans_pass_through_and_go_first_when_too_big(tmp_path):
    now = datetime(2026, 10, 14, 15, 0, tzinfo=ZoneInfo("America/New_York"))
    plan = {"summary": "x" * 900, "steps": [{"who": "you", "text": "Apply."}]}
    data = {"updated": now.isoformat(), "flagged": [
        {"id": f"t{n}", "at": now.isoformat(), "from": "Lab", "subject": f"Posting {n}", "why": "Fits",
         "level": "fyi", "url": "https://x", "plan": plan} for n in range(5)]}
    p = tmp_path / "mail.json"
    p.write_text(json.dumps(data))
    out = flagged.load(now, path=p)
    assert len(out["flagged"]) == 5
    assert "plan" in out["flagged"][0] and "plan" not in out["flagged"][-1]
    assert len(json.dumps(out, ensure_ascii=False).encode("utf-8")) <= flagged.LIMIT


def test_items_closed_in_jarvis_mail_leave_the_hud(tmp_path):
    now = datetime(2026, 10, 14, 22, 0, tzinfo=ZoneInfo("America/New_York"))
    path = tmp_path / "mail.json"
    item = {"at": "2026-10-14T17:40:00-04:00", "from": "x", "subject": "s", "why": "w", "level": "fyi", "url": "u"}
    path.write_text(json.dumps({"updated": "", "dismissed": [
        {"subject": "DATA 495 – Tauroi Client Meeting", "at": "2026-10-14T21:00:00-04:00"},
        {"subject": "Old one", "at": "2026-10-10T21:00:00-04:00"}], "flagged": [
        dict(item, id="a"), dict(item, id="b", status="denied"), dict(item, id="c", status="done")]}))
    out = flagged.load(now, path)
    assert [i["id"] for i in out["flagged"]] == ["a"]
    assert [d.get("id", d["subject"]) for d in out["dismissed"]] == ["DATA 495 – Tauroi Client Meeting", "b"]
    assert flagged.dismissed(now, path) == {"data 495 – tauroi client meeting"}
