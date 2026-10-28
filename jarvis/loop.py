"""Keeps the HUD fresh: python -m jarvis.loop [--hours 5.6]

GitHub runs scheduled workflows hours late, so one job stays up and refreshes every 15 minutes,
and at once whenever the HUD's Sync button posts to the "-sync" side topic. The workflow then
starts the next job before this one hits GitHub's 6-hour limit. It also refreshes as soon as a new
commit lands (the mail triage pushing data/mail.enc), so nothing waits for a fresh runner.
GitHub drops most of the UNC board job's own schedule too (runs came ~6 hours apart, not 2), so the
loop starts that job itself every couple of hours.
"""
import argparse
import os
import subprocess
import sys
import time

import requests

EVERY = 15 * 60  # seconds between routine refreshes
POLL = 20        # seconds between checks for a Sync tap
UNC_EVERY = 2 * 3600  # seconds between UNC board runs


def sync_requested(topic: str, since: int) -> bool:
    """True if the HUD posted to the sync topic after `since` (unix seconds)."""
    try:
        resp = requests.get(f"https://ntfy.sh/{topic}-sync/json", params={"poll": 1, "since": since}, timeout=15)
        return any('"event":"message"' in line.replace(" ", "") for line in resp.text.splitlines())
    except requests.RequestException:
        return False


def remote_head() -> str:
    """The latest commit on the remote branch, or "" if git can't reach it."""
    result = subprocess.run(["git", "ls-remote", "origin", "HEAD"], capture_output=True, text=True)
    return result.stdout.split()[0] if result.returncode == 0 and result.stdout.strip() else ""


def start_unc_board() -> bool:
    """Start the UNC board workflow (it commits data/unc.json, which this loop then picks up)."""
    result = subprocess.run(["gh", "workflow", "run", "unc.yml", "--ref", "master"], capture_output=True, text=True)
    print(time.strftime("%H:%M:%S"), "UNC board", "started" if result.returncode == 0 else "couldn't start", flush=True)
    return result.returncode == 0


def refresh() -> None:
    # Pick up commits made while this job runs (the mail triage updates data/mail.enc)
    subprocess.run(["git", "pull", "-q", "--ff-only"], capture_output=True)
    result = subprocess.run([sys.executable, "-m", "jarvis.briefing", "--quiet"], capture_output=True, text=True)
    # Only the status lines; the briefing text itself stays out of the public run log
    for line in (result.stdout + result.stderr).splitlines():
        if "unavailable" in line or "snapshot" in line or "refreshed" in line or "Traceback" in line:
            print(line)
    print(time.strftime("%H:%M:%S"), "refresh", "ok" if result.returncode == 0 else f"failed ({result.returncode})", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh the HUD every 15 minutes and on demand.")
    parser.add_argument("--hours", type=float, default=5.6, help="how long to keep running")
    args = parser.parse_args()
    topic = os.environ["NTFY_TOPIC"]
    stop = time.time() + args.hours * 3600
    unc_at = 0.0
    while time.time() < stop:
        started = int(time.time())
        if started - unc_at >= UNC_EVERY and start_unc_board():
            unc_at = started
        seen = remote_head()
        refresh()
        while time.time() < min(started + EVERY, stop):
            time.sleep(POLL)
            if sync_requested(topic, started):
                print(time.strftime("%H:%M:%S"), "sync requested from the HUD", flush=True)
                break
            now = remote_head()
            if seen and now and now != seen:
                print(time.strftime("%H:%M:%S"), "new commit, refreshing", flush=True)
                break


if __name__ == "__main__":
    main()
