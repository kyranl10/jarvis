from datetime import date

import pytest

from jarvis import unc_board

HEADER = ('"BOARD Link to Job Posting","Position Title & Link to Posting","Company/Organization","Role Type","Location",'
          '"Date Added to this Document","Date Posted by Company","Application Deadline","International Students",'
          '"Applicable Program","Notes/Comments"')
TODAY = date(2026, 10, 15)


def sheet(*rows):
    return "\n".join([HEADER, *rows])


def test_keeps_recent_undergrad_data_internships():
    out = unc_board.parse(sheet(
        '"https://x.co/1","Data Analyst Intern, Summer 2027","Acme","Internship","Raleigh, NC","10/14/2026","10/12","12/2","Yes","",""',
        '"https://x.co/2","Data Scientist, Research Intern, PhD, Summer 2027","Google","Internship","Mountain View, CA","10/14/2026","","","","",""',
        '"https://x.co/3","Software Engineer Intern","Acme","Internship","Austin, TX","10/14/2026","","","","",""',
        '"https://x.co/4","Data Engineer","Acme","Full-Time","Austin, TX","10/14/2026","","","","",""',
        '"https://x.co/5","Analytics Intern","Acme","Internship","London, UK","10/14/2026","","","","",""',
        '"https://x.co/6","ML Intern, BS/MS","Beta","Internship","Remote","10/13/2026","","","","",""',
    ), TODAY)
    assert [r["title"] for r in out["rows"]] == ["ML Intern, BS/MS", "Data Analyst Intern, Summer 2027"]
    acme = out["rows"][1]
    assert acme == {"id": unc_board.job_id("Acme", "Data Analyst Intern, Summer 2027"), "company": "Acme",
                    "title": "Data Analyst Intern, Summer 2027", "url": "https://x.co/1", "locations": ["Raleigh, NC"],
                    "posted": 1791806400000, "sheetAdded": "Oct 14", "deadline": "Dec 2", "source": "UNC board"}
    assert out["newest_added"] == "Oct 14"
    assert out["skipped"] == ["Oct 14 Google | Data Scientist, Research Intern, PhD, Summer 2027: grad students only",
                              "Oct 14 Acme | Software Engineer Intern: not a data role",
                              "Oct 14 Acme | Data Engineer: role type 'Full-Time'",
                              "Oct 14 Acme | Analytics Intern: location 'London, UK'"]


def test_one_week_rule_and_old_rows():
    out = unc_board.parse(sheet(
        '"","Data Intern","Old Post","Internship","Remote","10/14/2026","9/24","","","",""',
        '"","Data Intern","Old Add","Internship","Remote","10/1/2026","","","","",""',
    ), TODAY)
    assert out["rows"] == [] and out["newest_added"] == "Oct 14"


def test_year_less_dates_roll_back():
    assert unc_board._full_date("12/30", date(2027, 1, 2)) == date(2026, 12, 30)
    assert unc_board._full_date("1/2", date(2027, 1, 2)) == date(2027, 1, 2)
    assert unc_board._full_date("soon", TODAY) is None


def test_id_matches_the_scan_tasks_formula():
    import hashlib
    assert unc_board.job_id("Acme", "Data Intern") == "unc-" + hashlib.sha1(b"acme|data intern").hexdigest()[:10]


def test_changed_columns_fail_loudly():
    with pytest.raises(ValueError):
        unc_board.parse('"Title","Company"\n"a","b"', TODAY)


def test_engineering_roles_with_data_in_the_name_are_skipped():
    assert not unc_board.is_data_role("Software Engineer Intern (Data Foundation)")
    assert unc_board.is_data_role("Machine Learning Engineer Intern (Ads)")
    assert unc_board.is_data_role("Data Analyst Intern")


def test_duplicate_rows_and_header_below_a_title_row():
    out = unc_board.parse("\n".join(['"2026-27 BOARD"', HEADER,
        '"","Data Intern","Acme","Internship","Remote","10/14/2026","","","","",""',
        '"","Data Intern","Acme","Internship","Remote","10/14/2026","","","","",""']), TODAY)
    assert len(out["rows"]) == 1


def test_xlsx_links(tmp_path):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["Link", "Position Title & Link to Posting", "Company/Organization", "Role Type", "Location", "Date Added to this Document"])
    ws.append([None, "Data Intern", "Acme", "Internship", "Remote", date(2026, 10, 14)])
    ws["B2"].hyperlink = "https://acme.example/jobs/1"
    path = tmp_path / "b.xlsx"
    wb.save(path)
    out = unc_board.parse_table(*unc_board.read_xlsx(path.read_bytes()), TODAY)
    assert out["rows"][0]["url"] == "https://acme.example/jobs/1"
    assert out["rows"][0]["sheetAdded"] == "Oct 14"


def test_graduate_only_postings():
    assert unc_board.grad_only("AI & Machine Learning, Innovation Graduate Internship")
    assert not unc_board.grad_only("Data, & Machine Learning Engineering Undergraduate Internship")
    assert not unc_board.grad_only("ML Intern, BS/MS")
