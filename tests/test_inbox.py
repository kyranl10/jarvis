from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from jarvis import inbox, style
from jarvis.inbox import Overnight, clean_subject, collect, person, since, snippet

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 15, 8, 0, tzinfo=TZ)


def at(h, m=0, d=15):
    return datetime(2026, 10, d, h, m, tzinfo=TZ)


MESSAGES = [
    ("Facebook <notification@facebookmail.com>", "Sam Lee commented on your post in Drum Group.", at(21, 0, d=14),
     'Sam Lee commented on your post in Drum Group: "great hands but rushing in bar 3"'),
    ("Facebook <notification@facebookmail.com>", "Ava Cho commented on your post in Drum Group.", at(23, 15, d=14),
     'Ava Cho commented on your post in Drum Group: "Watch the accents in bar 12, otherwise clean"'),
    ("Facebook <notification@facebookmail.com>", "Ava Cho and 3 others reacted to your post", at(23, 20, d=14), ""),
    ("Instagram <no-reply@mail.instagram.com>", "jordan.k sent you a message", at(1, 5), ""),
    ("Instagram <no-reply@mail.instagram.com>", "You have unread messages", at(6, 30), ""),
]


def test_overnight_starts_at_1030_the_night_before():
    assert since(NOW) == at(22, 30, d=14)
    assert since(at(23, 0)) == at(22, 30)


def test_collects_only_overnight_comments_and_dms():
    night = collect(MESSAGES, since(NOW))
    assert night.comments == [("Ava Cho", "Drum Group", "Watch the accents in bar 12, otherwise clean")]
    assert night.dms == ["jordan.k"] and night.dm_unknown == 1


def test_overnight_in_briefing():
    night = collect(MESSAGES, since(NOW))
    _, body = style.notification(NOW.date(), NOW, None, [], [], [], "sir", night)
    assert body.splitlines()[-3:] == [
        "▸ OVERNIGHT",
        "  Ava Cho on Drum Group: “Watch the accents in bar 12, otherwise clean”",
        "  2 Instagram messages · jordan.k",
    ]
    said = style.spoken(NOW.date(), None, [], [], [], "sir", night)
    assert ("Overnight, 1 new comment in Drum Group. Ava Cho says: Watch the accents in bar 12, otherwise clean, "
            "and 2 Instagram messages from jordan.k.") in said
    assert not Overnight()


def test_forwarded_outlook_emails():
    msgs = MESSAGES + [
        ("Prof. Rivera <trivera@example.edu>", "HIST 210 office hours moved", at(0, 40), ""),
        ("noreply@example.edu", "Fall Break reminder", at(5, 0), ""),
    ]
    night = collect(msgs, since(NOW))
    assert night.emails == [("Prof. Rivera", "HIST 210 office hours moved", ""), ("noreply", "Fall Break reminder", "")]
    _, body = style.notification(NOW.date(), NOW, None, [], [], [], "sir", night)
    assert body.splitlines()[-2:] == ["  ✉ Prof. Rivera — HIST 210 office hours moved", "  ✉ noreply — Fall Break reminder"]
    said = style.spoken(NOW.date(), None, [], [], [], "sir", night)
    assert ("and 2 Instagram messages from jordan.k. noreply wrote about Fall Break reminder. "
            "Prof. Rivera wrote about HIST 210 office hours moved.") in said
    assert style.hud(NOW.date(), NOW, None, [], [], [], "sir", "", night)["overnight"]["emails"][0]["from"] == "Prof. Rivera"


AVI = ("Great chatting with you all today!\r\n\r\n"
       "On Tue, Oct 13, 2026 at 12:45 PM Nie, Jingping <jingping@unc.edu<mailto:jingping@unc.edu>> wrote:\r\n"
       "Hi Avi and all,\r\n\r\nAs such, let's just keep the meeting later today.\r\n\r\nBest,\r\nJingping\r\n\r\n"
       "Get Outlook for Mac<https://aka.ms/GetOutlookForMac>\r\n\r\nFrom: Avi Thaker <avi.thaker@gmail.com>\r\n")


def test_snippet_drops_quoted_replies():
    assert snippet(AVI) == "Great chatting with you all today!"
    assert snippet("Sounds good, see you then.\n\n> On Monday you wrote:\n> can we meet?") == "Sounds good, see you then."
    assert snippet("Approved. Thanks\n\n-----Original Message-----\nFrom: Me\nSubject: Leave\n\nCan I take Friday off?") == "Approved."
    assert snippet("Yes.\n________________________________\nFrom: Dean\nSent: Monday") == "Yes."
    # A forward with nothing written above it reads the forwarded message instead
    assert snippet("From: Dean <d@unc.edu>\nSent: Monday\nSubject: Parking\n\nLot F closes on Friday. Plan ahead.") == \
        "Lot F closes on Friday."


def test_snippet_drops_signatures_banners_and_links():
    banner = "[You don't often get email from klakhia@icloud.com. Learn why this is important at https://aka.ms/x ]\r\n\r\n"
    assert snippet(banner + "test\r\n") == "test"
    assert snippet("CAUTION: This email originated from outside UNC.\n\nHi Kyran,\n\nThe slides are at https://x.co/a now. "
                   "Thanks!\n\n-- \nDr. Smith") == "The slides are at now."
    assert snippet("Running late, start without me\n\nSent from my iPhone") == "Running late, start without me"
    assert snippet("Hi Kyran,\n\nSent from my iPhone") == ""
    assert snippet("https://example.com/only-a-link") == ""
    long = snippet("word " * 60)
    assert len(long) <= 161 and long.endswith("…")


def test_subjects_and_senders_are_tidied():
    assert clean_subject("RE: FW: Fwd: re: Project kickoff") == "Project kickoff"
    assert clean_subject("Re[2]: Budget") == "Budget"
    assert clean_subject("Reminder: lab") == "Reminder: lab"
    assert person('"Avi.thaker"') == "Avi Thaker" and person("Nie, Jingping") == "Jingping Nie"
    msgs = [('"Avi.thaker" <Avi.thaker@gmail.com>', "Re: DATA 495 — Tauroi Client Meeting", at(1, 55), AVI)]
    assert collect(msgs, since(NOW)).emails == [("Avi Thaker", "DATA 495 — Tauroi Client Meeting",
                                                  "Great chatting with you all today!")]


def test_emails_are_read_aloud():
    assert style.spoken_email("Avi Thaker", "Project kickoff", "Great chatting with you all today.") == \
        "Avi Thaker wrote about Project kickoff: Great chatting with you all today."
    # Said once when the subject and the first sentence say the same thing
    assert style.spoken_email("Kyran Lakhia", "test", "test") == "Kyran Lakhia wrote about test."
    assert style.spoken_email("Dean", "Parking", "Parking in lot F closes Friday") == "Dean wrote: Parking in lot F closes Friday."
    assert style.spoken_email("Dean", "(no subject)", "") == "Dean sent an email."
    night = Overnight(emails=[(f"P{i}", f"S{i}", f"Note {i}.") for i in range(5)])
    said = style.spoken(NOW.date(), None, [], [], [], "sir", night)
    assert ("Overnight, P4 wrote about S4: Note 4. P3 wrote about S3: Note 3. P2 wrote about S2: Note 2. "
            "And 2 more emails.") in said
    _, body = style.notification(NOW.date(), NOW, None, [], [], [], "sir", night)
    assert body.splitlines()[-2:] == ["  ✉ P4 — S4", "     Note 4."]
    assert style.hud(NOW.date(), NOW, None, [], [], [], "sir", "", night)["overnight"]["emails"][-1]["snippet"] == "Note 4."


def test_work_emails_and_teams_messages_are_labelled():
    msgs = [
        ("LevinW in Teams <noreply@email.teams.microsoft.com>", "LevinW sent a message", at(1, 0),
         "Hello data team, I have uploaded a new version of the master sheet. Please review it.", "VenueHorn"),
        ("Hafed G <HafedG@venuehorn.com>", "RE: Master sheet", at(2, 0), "All data from the master sheet is cleaned.", "VenueHorn"),
        ("Prof. Rivera <trivera@example.edu>", "Office hours moved", at(3, 0), ""),
    ]
    night = collect(msgs, since(NOW))
    assert night.emails == [
        ("LevinW on VenueHorn Teams", "(no subject)", "Hello data team, I have uploaded a new version of the master sheet."),
        ("Hafed G at VenueHorn", "Master sheet", "All data from the master sheet is cleaned."),
        ("Prof. Rivera", "Office hours moved", ""),
    ]
    said = style.spoken(NOW.date(), None, [], [], [], "sir", night)
    assert "LevinW on VenueHorn Teams wrote: Hello data team, I have uploaded a new version of the master sheet." in said


def test_overnight_skips_mass_mail_tests_and_your_own_forwards():
    assert inbox.is_noise("No Reply <no_reply@massmail.unc.edu>", "[FORMAL NOTICE] Changes")
    assert inbox.is_noise("Dean <dean@unc.edu>", "Newsletter", {"List-Unsubscribe": "<mailto:x@y>"})
    assert inbox.is_noise("Someone <a@b.com>", "Diagnostics report")
    assert inbox.is_noise("Someone <a@b.com>", "test")
    assert inbox.is_noise("Kyran Sanjiv Lakhia <me@school.edu>", "FW: Research", owner="Kyran")
    assert not inbox.is_noise("Avi Thaker <avi@x.com>", "DATA 495 – Client Meeting", owner="Kyran")
    assert not inbox.is_noise("GDIT Workday <GDIT@myworkday.com>", "Thank you for your submission", owner="Kyran")


def test_repeated_subjects_show_once():
    start = datetime(2026, 10, 13, 22, 30, tzinfo=TZ)
    at = start + timedelta(hours=1)
    found = inbox.collect([("A <a@x.com>", "Thanks", at, "First."), ("B <b@x.com>", "Other", at, "Hi there."),
                           ("A <a@x.com>", "RE: Thanks", at, "Second.")], start)
    assert [e[1] for e in found.emails] == ["Other", "Thanks"]
    assert found.emails[-1][2] == "Second."


def test_canvas_announcements_are_not_noise_but_its_confirmation_email_is():
    bulk = {"List-Unsubscribe": "<mailto:x>", "Precedence": "bulk"}
    assert not inbox.is_noise("PLAN372.001.FA26 <notifications@instructure.com>", "News article on dam safety", bulk)
    assert inbox.is_noise("Canvas <notifications@instructure.com>", "Confirm Email: Canvas - kyranlakhia@gmail.com", bulk)
    assert inbox.is_noise("Canvas <notifications@instructure.com>", "Security alert: new email address added", bulk)
    assert inbox.is_noise("Shop <deals@shop.com>", "Sale", bulk)


def test_recent_emails_link_to_gmail():
    msgs = [("Prof. Rivera <trivera@example.edu>", "HIST 210 office hours moved", at(7, 0), "", "", "1879082042730626238")]
    night = collect(msgs, since(NOW))
    hud = style.hud(NOW.date(), NOW, None, [], [], [], "sir", "", night)
    assert hud["overnight"]["emails"][0]["url"] == "https://mail.google.com/mail/#all/thread-f:1879082042730626238"
