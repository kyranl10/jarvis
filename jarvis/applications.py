"""Kyran's application statuses for the HUD's internships page, kept off the public site.

The internship tasks commit them encrypted as jobs.enc in jarvis-hud (see internships.py). Each refresh
decrypts that file and publishes it to the private ntfy "-jobs" topic, which the internships page reads
when opened from the HUD link.
"""
import json

import requests

from . import mailstore

URL = "https://raw.githubusercontent.com/kyranl10/jarvis-hud/main/jobs.enc"
LIMIT = 3900  # ntfy turns bigger messages into attachments the page can't read


def fit(data: dict) -> str:
    """The payload as JSON, trimmed to fit one ntfy message: reply texts older than 3 days go first, then
    the cards of old acted-on jobs, then the remaining reply texts, oldest first. Statuses always stay."""
    out = json.loads(json.dumps(data))
    size = lambda: len(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    texts = sorted((s for s in out.get("status", {}).values() if "n" in s), key=lambda s: s.get("a", 0))
    recent = out.get("updated", 0) - 3 * 864e5
    for s in [s for s in texts if s.get("a", 0) < recent]:
        if size() <= LIMIT:
            break
        s.pop("n")
    while size() > LIMIT and out.get("cards"):
        out["cards"].pop()
    for s in texts:
        if size() <= LIMIT:
            break
        s.pop("n", None)
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def load() -> dict | None:
    resp = requests.get(URL, timeout=30)
    if resp.status_code == 404:
        return None  # not written yet
    resp.raise_for_status()
    data = mailstore.decrypt(resp.content)
    if data is None:
        raise ValueError("jobs.enc couldn't be decrypted")
    return data
