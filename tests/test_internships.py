import json

from jarvis import internships as ix

NOW = 1792022400000  # Oct 15, 2026 noon UTC
DAY = 86400000


def listing(**kw):
    x = {"id": "s1", "company_name": "Acme", "title": "Data Analyst Intern", "url": "https://a", "active": True,
         "is_visible": True, "terms": ["Summer 2027"], "locations": ["Raleigh, NC"], "date_posted": NOW // 1000 - 3600,
         "degrees": ["Bachelor's"]}
    return {**x, **kw}


def test_simplify_filters():
    found = ix.from_simplify([listing(), listing(id="s2", locations=["London, UK"]), listing(id="s3", degrees=["PhD"]),
                              listing(id="s4", title="Mechanical Intern"), listing(id="s5", terms=["Summer 2026"]),
                              listing(id="s6", active=False)])
    assert [j["id"] for j in found] == ["s1"]
    assert found[0]["score"] == 5 + 2 + 2 and found[0]["source"] == "Simplify"


def test_candidates_dedupes_and_applies_one_week_rule():
    known = [{"id": "s1", "company": "Acme", "title": "Data Analyst Intern"}]
    found = [{"id": "s1", "company": "Acme", "title": "x", "score": 5},
             {"id": "u1", "company": "ACME", "title": "data analyst intern", "score": 5},
             {"id": "old", "company": "B", "title": "Data", "score": 5, "posted": NOW - 8 * DAY},
             {"id": "neg", "company": "C", "title": "Data Engineer", "score": -1},
             {"id": "ok", "company": "D", "title": "Data", "score": 2, "posted": NOW - DAY},
             {"id": "ok2", "company": "D", "title": "Data", "score": 2}]
    assert [j["id"] for j in ix.candidates(found, known, NOW)] == ["ok"]
    assert [j["id"] for j in ix.candidates(found, known, NOW, min_score=None)] == ["ok", "neg"]


def test_stale_keeps_anything_acted_on():
    jobs = [{"id": "a", "status": "new", "posted": NOW - 8 * DAY}, {"id": "b", "status": "denied", "added": NOW - 9 * DAY},
            {"id": "c", "status": "applied", "posted": NOW - 30 * DAY}, {"id": "d", "status": "new", "posted": NOW - DAY},
            {"id": "e", "status": "new"}]
    assert ix.stale(jobs, NOW) == ["a", "b"]


def test_hud_files_leak_no_application_details():
    jobs = [{"id": "n", "company": "Open Co", "title": "Data Intern", "status": "new", "posted": NOW, "fit": {"score": 7}},
            {"id": "a", "company": "Applied Co", "title": "Analyst", "status": "interview", "posted": NOW,
             "news": {"at": NOW - DAY, "text": "Applied Co wants to talk"}}]
    intern, listing = ix.hud_files(jobs, 10, NOW)
    text = json.dumps([intern, listing])
    assert "Applied Co" not in text and "status" not in json.dumps(listing["jobs"])
    assert intern["counts"]["interview"] == 1 and intern["news"] == [{"status": "interview", "at": NOW - DAY}]
    assert [j["id"] for j in listing["jobs"]] == ["n"] and intern["fresh"][0]["company"] == "Open Co"


def test_load_jobs_reads_artifact_data_files(tmp_path):
    (tmp_path / "x1.json").write_text(json.dumps({"data": {"company": "A", "status": "new"}}))
    (tmp_path / "x2.json").write_text(json.dumps({"company": "B"}))
    assert [(j["id"], j["company"]) for j in ix.load_jobs(tmp_path)] == [("x1", "A"), ("x2", "B")]
