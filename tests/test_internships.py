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
    jobs.append({"id": "old", "company": "Old Co", "title": "Analyst", "status": "applied", "posted": NOW - 20 * DAY})
    intern, listing, private = ix.hud_files(jobs, 10, NOW)
    assert "Applied Co wants" not in json.dumps([intern, listing]) and "Old Co" not in json.dumps([intern, listing])
    assert "status" not in json.dumps(listing["jobs"])
    assert intern["counts"]["interview"] == 1 and intern["news"] == [{"status": "interview", "at": NOW - DAY}]
    assert [j["id"] for j in listing["jobs"]] == ["n", "a"] and intern["fresh"][0]["company"] == "Open Co"
    assert private["status"] == {"a": {"s": "interview", "n": "Applied Co wants to talk", "a": NOW - DAY}, "old": {"s": "applied"}}
    assert [c["id"] for c in private["cards"]] == ["old"]


def test_load_jobs_reads_artifact_data_files(tmp_path):
    (tmp_path / "x1.json").write_text(json.dumps({"data": {"company": "A", "status": "new"}}))
    (tmp_path / "x2.json").write_text(json.dumps({"company": "B"}))
    assert [(j["id"], j["company"]) for j in ix.load_jobs(tmp_path)] == [("x1", "A"), ("x2", "B")]


def test_private_payload_fits_ntfy():
    from jarvis import applications
    data = {"updated": NOW, "status": {f"j{i}": {"s": "applied", "n": "x" * 120, "a": NOW + i} for i in range(20)},
            "cards": [{"id": f"c{i}", "company": "C" * 30, "title": "T" * 60} for i in range(40)]}
    out = json.loads(applications.fit(data))
    assert len(applications.fit(data).encode()) <= applications.LIMIT
    assert len(out["status"]) == 20 and out["status"]["j19"].get("n")  # newest replies kept longest


def test_same_posting_under_different_spellings():
    pairs = [
        (("Federal Reserve Bank of Dallas", "2027 Intern - System IT (S&R and Statistics)"),
         ("Federal Reserve System", "2027 Intern - System IT (S&R and Statistics)")),
        (("Mastercard", "Data Engineering Intern, Summer 2027"),
         ("MasterCard", "Data Engineering Intern, Summer 2027 – San Franscisco, CA, US")),
        (("Stryker", "Customer One Intern (Data Analyst) - Cary, IL"),
         ("Stryker", "Summer 2027 Internship - Data Analytics - Customer One - Illinois")),
        (("Stryker", "Summer 2027 Internship - Statistical Programming"),
         ("Stryker", "Summer 2027 Internship - Statistical Programming - California")),
        (("Nike", "AI, Data & Machine Learning Engineering Undergraduate Internship"),
         ("Nike", "NIKE, Inc. Artificial Intelligence, Data, & Machine Learning Engineering Undergraduate Internship Position Type")),
        (("GE Vernova", "AI Evaluation & Benchmarking Intern"), ("GE Vernova", "AI Evaluation & Benchmarking Intern - AGI")),
    ]
    for (c1, t1), (c2, t2) in pairs:
        assert ix.same_job({"company": c1, "title": t1}, {"company": c2, "title": t2}), (t1, t2)


def test_different_postings_stay_apart():
    tiktok = "TikTok"
    assert not ix.same_job({"company": tiktok, "title": "Machine Learning Engineer Intern - E-Commerce Recommendation Video"},
                           {"company": tiktok, "title": "Machine Learning Engineer Intern - E-Commerce Knowledge Graph"})
    assert not ix.same_job({"company": "Stryker", "title": "Data Engineering - Indiana"},
                           {"company": "Stryker", "title": "Statistical Programming - California"})
    assert not ix.same_job({"company": "Acme", "title": "Data Analyst Intern"}, {"company": "Beta", "title": "Data Analyst Intern"})
