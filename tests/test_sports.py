import copy
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from jarvis import sports, style
from jarvis.sports import Team, parse_game

TZ = ZoneInfo("America/New_York")
ESPN = json.loads((Path(__file__).parent / "fixtures" / "espn.json").read_text(encoding="utf-8"))
CLT = Team("Charlotte FC", "soccer", "21300", ("usa.1",))
BOCA = Team("Boca Juniors", "soccer", "5", ("conmebol.sudamericana",), "Boca")
BVB = Team("Dortmund", "soccer", "124", ("ger.1",))


def test_finished_game():
    g = parse_game(ESPN["sudamericana_20261013"][0], "conmebol.sudamericana", BOCA, TZ)
    assert (g.at, g.us, g.them, g.home) == (datetime(2026, 10, 13, 20, 30, tzinfo=TZ), "Boca Juniors", "Vasco da Gama", True)
    assert (g.final, g.us_score, g.them_score, g.result, g.competition) == (True, 0, 1, "L", "Copa Sudamericana")
    assert style.spoken_sports([g], [], date(2026, 10, 14)) == \
        "In sports, Boca lost 1 to 0 to Vasco da Gama."


def test_upcoming_game_with_records():
    g = parse_game(ESPN["mls_20261014"][0], "usa.1", CLT, TZ)
    assert (g.at, g.them, g.home, g.final) == (datetime(2026, 10, 14, 19, 30, tzinfo=TZ), "Columbus Crew", False, False)
    assert (g.us_record, g.them_record, g.broadcast, g.competition) == ("13-7-8", "8-5-15", "Apple TV", "MLS")
    today = date(2026, 10, 14)
    assert style.spoken_sports([], [g], today) == \
        "In sports, tonight, Charlotte FC play Columbus Crew at 7:30."
    _, body = style.notification(today, datetime(2026, 10, 14, 7, tzinfo=TZ), None, [], [], [], "sir", sports=([], [g]))
    assert body.splitlines()[-2:] == ["▸ SPORTS",
                                      "  Today 7:30 PM — Charlotte FC (13-7-8) at Columbus Crew (8-5-15) · MLS · Apple TV"]


def test_soccer_draw():
    g = parse_game(ESPN["bundesliga_20261009"][0], "ger.1", BVB, TZ)
    assert (g.us_score, g.them_score, g.result, g.competition) == (2, 2, "D", "Bundesliga")
    assert style.spoken_sports([g], [], date(2026, 10, 10)) == \
        "In sports, Dortmund drew 2 all with Werder Bremen."


def _game(us, them, at, **kw):
    return sports.Game(at, "", us, them, None, False, us_said=us, them_said=them, **kw)


def test_one_sentence_for_results_and_one_for_whats_ahead():
    today = date(2026, 10, 14)
    boca = sports.Game(datetime(2026, 10, 13, 20, 30, tzinfo=TZ), "", "Boca Juniors", "Vasco da Gama", True, True,
                       0, 1, "L", us_said="Boca", them_said="Vasco da Gama")
    upcoming = [_game("Dortmund", "Bodo/Glimt", datetime(2026, 10, 14, 15, tzinfo=TZ)),
                _game("Charlotte FC", "Columbus", datetime(2026, 10, 14, 19, 30, tzinfo=TZ)),
                _game("the Hornets", "the Celtics", datetime(2026, 10, 14, 19, 30, tzinfo=TZ)),
                _game("the Reds", "the Cubs", datetime(2026, 10, 15, 11, 5, tzinfo=TZ))]
    assert style.spoken_sports([boca], upcoming[:3], today) == (
        "In sports, Boca lost 1 to 0 to Vasco da Gama. Today, Dortmund play Bodo/Glimt at 3, and tonight "
        "Charlotte FC play Columbus and the Hornets play the Celtics, both at 7:30.")
    assert style.spoken_sports([], upcoming[3:], today) == "In sports, tomorrow, the Reds play the Cubs at 11:05 AM."


def test_short_names_from_espn():
    event = copy.deepcopy(ESPN["mls_20261014"][0])
    for c in event["competitions"][0]["competitors"]:
        c["team"]["shortDisplayName"] = c["team"]["displayName"].split()[0] + " "
    g = parse_game(event, "usa.1", CLT, TZ)
    assert (g.us_said, g.them_said, g.them) == ("Charlotte FC", "Columbus", "Columbus Crew")
    g = parse_game(event, "nba", Team("the Hornets", "basketball", "21300", ("nba",)), TZ)
    assert g.them_said == "the Columbus"


def _at(event, when: datetime):
    event = copy.deepcopy(event)
    event["id"] += when.strftime("%d%H")
    event["date"] = event["competitions"][0]["date"] = when.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%MZ")
    return event


def test_last_and_next_24_and_72_hours(monkeypatch):
    now = datetime(2026, 10, 14, 7, tzinfo=TZ)
    final, fixture = ESPN["sudamericana_20261013"][0], ESPN["mls_20261014"][0]
    events = {"conmebol.sudamericana": [_at(final, now - timedelta(hours=h)) for h in (10, 50, 80)],
              "usa.1": [_at(fixture, now + timedelta(hours=h)) for h in (12, 60, 90)]}
    monkeypatch.setattr(sports, "_get", lambda path, params: {"events": events[path.split("/")[1]]})

    scores, upcoming = sports.fetch(now, hours=72, teams=[CLT, BOCA])
    assert [g.at for g in scores] == [now - timedelta(hours=10), now - timedelta(hours=50)]
    assert [g.at for g in upcoming] == [now + timedelta(hours=12), now + timedelta(hours=60)]

    day = sports.within(scores, upcoming, now, hours=24)
    assert ([g.at for g in day[0]], [g.at for g in day[1]]) == ([now - timedelta(hours=10)], [now + timedelta(hours=12)])
    voice = style.spoken(now.date(), None, [], [], [], "sir", sports=day)
    assert voice.endswith("In sports, Boca lost 1 to 0 to Vasco da Gama. Tonight, Charlotte FC play Columbus Crew at 7. "
                          "Enjoy the day, sir.")

    hud = style.hud(now.date(), now, None, [], [], [], "sir", voice, sports=(scores, upcoming))
    assert [g["at"] for g in hud["sports"]["scores"]] == ["2026-10-13T21:00-04:00", "2026-10-12T05:00-04:00"]
    assert hud["sports"]["upcoming"][0] == {"at": "2026-10-14T19:00-04:00", "comp": "MLS", "us": "Charlotte FC",
                                            "them": "Columbus Crew", "home": False, "rec": ["13-7-8", "8-5-15"],
                                            "tv": "Apple TV", "say": ["Charlotte FC", "Columbus Crew"]}


def test_espn_answering_nothing_raises_for_the_health_strip(monkeypatch, capsys):
    def get(path, params):
        raise ConnectionError("down")
    monkeypatch.setattr(sports, "_get", get)
    with pytest.raises(ConnectionError):
        sports.fetch(datetime(2026, 10, 14, 7, tzinfo=TZ), teams=[CLT])
    assert set(capsys.readouterr().out.splitlines()) == {"Sports unavailable: ConnectionError"}


def test_a_failing_competition_is_skipped(monkeypatch, capsys):
    def get(path, params):
        if params.get("fixture"):
            raise ConnectionError("down")
        return {"events": []}
    monkeypatch.setattr(sports, "_get", get)
    assert sports.fetch(datetime(2026, 10, 14, 7, tzinfo=TZ), teams=[CLT]) == ([], [])
    assert set(capsys.readouterr().out.splitlines()) == {"Sports unavailable: ConnectionError"}
