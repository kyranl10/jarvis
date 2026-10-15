"""The deterministic half of the internship scan, run by Kyran's scheduled Claude tasks.

The tasks keep the judgment calls (reading postings, rating hire odds, application replies); this does the rest.

  python -m jarvis.internships scan --jobs DIR [--since EPOCH_S] [--top N]
      New candidates from Simplify's Summer 2027 list and the UNC board (data/unc.json), as JSON,
      best first: not already in DIR, no same company-and-title duplicates, within the one-week rule.
  python -m jarvis.internships prune --jobs DIR
      Ids of stale jobs to delete: status new or denied, more than 7 days old by posting date (or added).
  python -m jarvis.internships hud --jobs DIR --matched N INTERN_JSON [JOBS_JSON]
      The public jarvis-hud files: counts and this week's postings, never statuses or replies. Next to
      JOBS_JSON it also writes jobs.enc: the statuses, replies and older acted-on jobs, encrypted with
      the mail key. The refresh decrypts it and sends it through the private ntfy "-jobs" topic, so the
      internships page shows everything only when opened from Kyran's HUD link.

DIR holds one JSON file per job (ArtifactData list with out_dir); a file is the job, or {"data": job}.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

SIMPLIFY = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json"
UNC = Path(__file__).resolve().parent.parent / "data" / "unc.json"
DAY_MS = 864e5
MAX_AGE_DAYS = 7  # Kyran's one-week rule (Oct 14)

# Filters (Kyran's answers, Oct 14): summer 2027 plus co-ops, all data roles, US plus remote, bachelor's-eligible
TERMS = {"Summer 2027", "Fall 2027", "Spring 2027", "Winter 2027", "Spring 2028"}
US = re.compile(r", (A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[ADLN]|K[SY]|LA|M[ADEINOST]|N[CDEHJMVY]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[AT]"
                r"|W[AIVY])\b|\bRemote\b|United States|\bUSA?\b", re.I)
DATA = re.compile(r"data|analyt|machine learning|\bML\b|\bAI\b|quant|statist|insight|business intel|decision science", re.I)
SCORES = [(r"data scien", 6), (r"sports", 5), (r"data analy", 5), (r"analytics", 4), (r"business intel|insight", 3),
          (r"statist", 3), (r"machine learning|\bML\b", 2), (r"\bAI\b", 1), (r"quant", 1),
          (r"research", -1), (r"engineer", -2), (r"hardware|firmware|embedded", -4)]

STATUS_GROUPS = {"new": ["new"], "progress": ["tailoring", "review", "ready"],
                 "applied": ["applied", "interview", "offer", "rejected"], "interview": ["interview", "offer"],
                 "denied": ["denied"]}
PUBLIC_FIELDS = ("id", "company", "title", "url", "posted", "source", "terms", "locations", "details", "fit", "added",
                 "sheetAdded")


def load_jobs(folder: Path) -> list[dict]:
    jobs = []
    for f in sorted(Path(folder).rglob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d = d.get("data", d)
        d["id"] = f.stem
        jobs.append(d)
    return jobs


def score(title: str, terms: list[str], locations: list[str]) -> int:
    s = sum(w for pat, w in SCORES if re.search(pat, title, re.I))
    if "Summer 2027" in terms:
        s += 2
    if any(re.search(r", NC\b", l) for l in locations):
        s += 2
    return s


def from_simplify(listings: list[dict], since_s: int = 0) -> list[dict]:
    out = []
    for x in listings:
        if not (x.get("active") and x.get("is_visible")) or x.get("date_posted", 0) < since_s:
            continue
        terms = [t for t in (x.get("terms") or []) if t in TERMS]
        if not terms or not any(US.search(l) for l in x.get("locations") or []):
            continue
        if not DATA.search(x["title"]) and x.get("category") != "Data Science, AI & Machine Learning":
            continue
        degrees = x.get("degrees") or []
        if degrees and "Bachelor's" not in degrees:
            continue
        locations = [l for l in x["locations"] if US.search(l)][:4]
        out.append({"id": x["id"], "company": x["company_name"], "title": x["title"], "url": x["url"],
                    "locations": locations, "terms": terms, "posted": x["date_posted"] * 1000,
                    "category": x.get("category", ""), "sponsorship": x.get("sponsorship", ""), "source": "Simplify",
                    "score": score(x["title"], terms, locations)})
    return out


def from_unc(board: dict) -> list[dict]:
    return [{**r, "terms": [t for t in TERMS if t.lower() in r["title"].lower()] or ["Summer 2027"],
             "score": score(r["title"], ["Summer 2027"], r.get("locations", []))} for r in board.get("rows", [])]


def candidates(found: list[dict], known: list[dict], now_ms: int, min_score: int | None = 1) -> list[dict]:
    """New, unduplicated candidates inside the one-week rule, best first; min_score None keeps any score."""
    ids = {j["id"] for j in known}
    pairs = {(j.get("company", "").lower(), j.get("title", "").lower()) for j in known}
    out = []
    for j in sorted(found, key=lambda j: (-j["score"], -j.get("posted", 0))):
        pair = (j["company"].lower(), j["title"].lower())
        if j["id"] in ids or pair in pairs or (min_score is not None and j["score"] < min_score):
            continue
        if j.get("posted") and now_ms - j["posted"] > MAX_AGE_DAYS * DAY_MS:
            continue
        ids.add(j["id"])
        pairs.add(pair)
        out.append(j)
    return out


def stale(jobs: list[dict], now_ms: int) -> list[str]:
    """Jobs never acted on (new) or turned down (denied) that are older than the one-week rule."""
    return [j["id"] for j in jobs if j.get("status", "new") in ("new", "denied")
            and (j.get("posted") or j.get("added") or now_ms) < now_ms - MAX_AGE_DAYS * DAY_MS]


def hud_files(jobs: list[dict], matched: int, now_ms: int) -> tuple[dict, dict, dict]:
    """(intern.json, jobs.json, private): the public HUD files say nothing about applications; private
    carries each acted-on job's status and reply, and the cards of acted-on jobs too old for the public list."""
    counts = {k: sum(j.get("status") in v for j in jobs) for k, v in STATUS_GROUPS.items()}
    fresh, seen = [], set()
    for j in sorted((j for j in jobs if j.get("status") == "new"), key=lambda j: -j.get("posted", 0)):
        if (j.get("fit") or {}).get("score", 0) >= 6 and j["company"] not in seen and len(fresh) < 3:
            seen.add(j["company"])
            fresh.append(j)
    # Replies from the last 3 days: only what kind of reply and when; the company stays on the private page
    news = sorted((j for j in jobs if (j.get("news") or {}).get("at", 0) > now_ms - 3 * DAY_MS),
                  key=lambda j: -j["news"]["at"])[:3]
    intern = {"updated": now_ms, "matched": matched, "counts": counts,
              "news": [{"status": j.get("status"), "at": j["news"]["at"]} for j in news],
              "fresh": [{"company": j["company"], "title": j["title"], "posted": j.get("posted")} for j in fresh]}
    # Public: every new job, plus acted-on ones from this week, all without status, so nothing tells them apart
    recent = lambda j: (j.get("posted") or j.get("added") or 0) >= now_ms - MAX_AGE_DAYS * DAY_MS
    shown = [j for j in jobs if j.get("status", "new") == "new" or recent(j)]
    listing = sorted(({k: j[k] for k in PUBLIC_FIELDS if k in j} for j in shown), key=lambda j: -j.get("posted", 0))
    acted = [j for j in jobs if j.get("status", "new") != "new"]
    private = {"updated": now_ms,
               "status": {j["id"]: {"s": j["status"], **({"n": j["news"]["text"], "a": j["news"]["at"]} if j.get("news") else {})}
                          for j in acted},
               "cards": [{k: j[k] for k in ("id", "company", "title", "url", "posted", "source") if k in j}
                         for j in acted if not recent(j)]}
    return intern, {"updated": now_ms, "matched": matched, "counts": counts, "jobs": listing}, private


def _fetch_json(url: str):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def main(argv: list[str]) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["scan", "prune", "hud"])
    ap.add_argument("--jobs", type=Path, required=True, help="folder of job JSON files")
    ap.add_argument("--since", type=int, default=0, help="scan: Simplify listings posted after this (unix seconds)")
    ap.add_argument("--top", type=int, default=0, help="scan: at most this many from Simplify")
    ap.add_argument("--matched", type=int, default=0, help="hud: the running match count")
    ap.add_argument("out", nargs="*", type=Path, help="hud: INTERN_JSON [JOBS_JSON]")
    a = ap.parse_args(argv)
    now = int(time.time() * 1000)
    jobs = load_jobs(a.jobs)
    if a.command == "scan":
        simplify = candidates(from_simplify(_fetch_json(SIMPLIFY), a.since), jobs, now)[: a.top or None]
        board = json.loads(UNC.read_text(encoding="utf-8")) if UNC.exists() else {}
        unc = candidates(from_unc(board), jobs + simplify, now, min_score=None)  # the board is already filtered
        json.dump({"unc_newest_added": board.get("newest_added"), "jobs": simplify + unc}, sys.stdout,
                  ensure_ascii=False, indent=1)
    elif a.command == "prune":
        json.dump(stale(jobs, now), sys.stdout)
    else:
        if not a.out:
            ap.error("hud needs INTERN_JSON [JOBS_JSON]")
        intern, listing, private = hud_files(jobs, a.matched, now)
        a.out[0].write_text(json.dumps(intern, indent=1) + "\n")
        if len(a.out) > 1:
            a.out[1].write_text(json.dumps(listing, separators=(",", ":")) + "\n")
            from . import mailstore
            if mailstore.key():
                mailstore.seal(private, a.out[1].with_name("jobs.enc"))
            else:
                print("No mail key found, so jobs.enc (statuses for the private view) wasn't written.", file=sys.stderr)
        print(json.dumps(intern))


if __name__ == "__main__":
    main(sys.argv[1:])
