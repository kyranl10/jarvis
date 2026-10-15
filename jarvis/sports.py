"""Scores and upcoming games for your teams, from ESPN's public site API (free, no key).

ESPN's scoreboards hold records and broadcasts, but each one covers a single league on a single day,
and date ranges don't work. So each team's schedule in every competition it plays (league, cups,
playoffs) says which days to read, and only those scoreboards are fetched. NBA and MLB schedules are
huge while their daily scoreboards are small, so those leagues are read day by day instead.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

API = "https://site.api.espn.com/apis/site/v2/sports"
ESPN_DAY = ZoneInfo("America/New_York")  # scoreboards are filed under the US Eastern date


@dataclass(frozen=True)
class Team:
    name: str  # how Jarvis says it
    sport: str
    id: str
    leagues: tuple[str, ...]
    short: str = ""  # shorter spoken name, if any


TEAMS = [
    Team("Charlotte FC", "soccer", "21300", ("usa.1", "usa.open", "concacaf.champions")),
    Team("Dortmund", "soccer", "124", ("ger.1", "ger.dfb_pokal", "uefa.champions")),
    Team("Boca Juniors", "soccer", "5", ("arg.1", "arg.copa", "conmebol.libertadores", "conmebol.sudamericana"), "Boca"),
    Team("UNC", "basketball", "153", ("mens-college-basketball",)),
    Team("UNC", "football", "153", ("college-football",)),
    Team("the Hornets", "basketball", "30", ("nba",)),
    Team("the Reds", "baseball", "17", ("mlb",)),
]

COMPETITIONS = {
    "usa.1": "MLS", "usa.open": "US Open Cup", "concacaf.champions": "CONCACAF Champions Cup",
    "ger.1": "Bundesliga", "ger.dfb_pokal": "DFB-Pokal", "uefa.champions": "Champions League",
    "arg.1": "Liga Profesional", "arg.copa": "Copa Argentina",
    "conmebol.libertadores": "Copa Libertadores", "conmebol.sudamericana": "Copa Sudamericana",
    "mens-college-basketball": "college basketball", "college-football": "college football",
    "nba": "NBA", "mlb": "MLB",
}
DAILY = {"nba", "mlb"}
NICKNAMED = {"nba", "mlb"}  # ESPN's short names there are nicknames: "the Celtics"
# Without these, college scoreboards only list featured games
SCOREBOARD_PARAMS = {"college-football": {"groups": "80"}, "mens-college-basketball": {"groups": "50", "limit": "500"}}


@dataclass
class Game:
    at: datetime
    competition: str
    us: str
    them: str
    home: bool | None  # None at a neutral ground
    final: bool
    us_score: int | None = None
    them_score: int | None = None
    result: str = ""  # W, L or D once final
    us_record: str = ""  # W-D-L for soccer, W-L otherwise
    them_record: str = ""
    broadcast: str = ""
    us_said: str = ""  # short names for the spoken briefing
    them_said: str = ""


def _get(path: str, params: dict) -> dict:
    resp = requests.get(f"{API}/{path}", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _score(c: dict) -> int | None:
    s = c.get("score")
    s = s.get("value") if isinstance(s, dict) else s
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _record(c: dict) -> str:
    records = c.get("records") or c.get("record") or []
    total = next((r for r in records if r.get("type") == "total"), records[0] if records else {})
    return total.get("summary") or total.get("displayValue") or ""


def _broadcast(comp: dict) -> str:
    names = []
    for b in comp.get("broadcasts") or []:
        names += b.get("names") or [(b.get("media") or {}).get("shortName", "")]
    return ", ".join(list(dict.fromkeys(n for n in names if n))[:2])


def _competition(league: str, event: dict) -> str:
    name = COMPETITIONS.get(league, league)
    stage = ((event.get("seasonType") or {}).get("name") or (event.get("season") or {}).get("slug") or "").lower()
    if "preseason" in stage:
        return f"{name} preseason"
    if "playoff" in stage or "post" in stage:
        return f"{name} playoffs" if league in ("usa.1", "nba", "mlb") else f"{name} postseason"
    return name


def parse_game(event: dict, league: str, team: Team, tz: ZoneInfo) -> Game | None:
    """One ESPN event (from a scoreboard or a schedule) as a Game, or None if it isn't finished or upcoming."""
    comp = event["competitions"][0]
    side = {c.get("id") or c["team"]["id"]: c for c in comp["competitors"]}
    us = side.pop(team.id, None)
    if us is None or len(side) != 1:
        return None
    them = next(iter(side.values()))
    status = (comp.get("status") or event.get("status") or {}).get("type", {})
    at = datetime.fromisoformat(event["date"].replace("Z", "+00:00")).astimezone(tz)
    game = Game(at, _competition(league, event), team.name, them["team"]["displayName"],
                None if comp.get("neutralSite") else us.get("homeAway") == "home", bool(status.get("completed")))
    short = (them["team"].get("shortDisplayName") or "").strip() or game.them
    game.us_said = team.short or team.name
    game.them_said = f"the {short}" if league in NICKNAMED and short != game.them else short
    if game.final:
        game.us_score, game.them_score = _score(us), _score(them)
        if game.us_score is None or game.them_score is None:
            return None
        if us.get("winner") or them.get("winner"):  # also settles penalty shootouts
            game.result = "W" if us.get("winner") else "L"
        else:
            game.result = "W" if game.us_score > game.them_score else "L" if game.us_score < game.them_score else "D"
    elif status.get("state", "pre") == "pre" and "POSTPONED" not in status.get("name", "") and "CANCEL" not in status.get("name", ""):
        game.us_record, game.them_record = _record(us), _record(them)
        game.broadcast = _broadcast(comp)
    else:
        return None  # in progress, postponed or cancelled
    return game


def _days(start: datetime, end: datetime) -> list[str]:
    first, last = start.astimezone(ESPN_DAY).date(), end.astimezone(ESPN_DAY).date()
    return [(first + timedelta(days=i)).strftime("%Y%m%d") for i in range((last - first).days + 1)]


def _safely(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # one competition being down shouldn't cost the rest
        print(f"Sports unavailable: {exc.__class__.__name__}")
        return None


def fetch(now: datetime, hours: int = 72, teams=TEAMS) -> tuple[list[Game], list[Game]]:
    """(scores, upcoming): finished games from the last `hours`, newest first, and games in the next `hours`, soonest first."""
    tz = now.tzinfo
    start, end = now - timedelta(hours=hours), now + timedelta(hours=hours)
    days = _days(start, end)
    pairs = [(t, lg) for t in teams for lg in t.leagues]

    def schedule(team, league, params):
        return team, league, _get(f"{team.sport}/{league}/teams/{team.id}/schedule", params).get("events", [])

    def scoreboard(sport, league, day):
        return league, _get(f"{sport}/{league}/scoreboard", {"dates": day, **SCOREBOARD_PARAMS.get(league, {})}).get("events", [])

    with ThreadPoolExecutor(8) as pool:
        # Soccer schedules list results unless asked for fixtures; US ones need the season type (2 regular, 3 post)
        jobs = [(t, lg, p) for t, lg in pairs if lg not in DAILY for p in
                (({}, {"fixture": "true"}) if t.sport == "soccer" else ({"seasontype": "2"}, {"seasontype": "3"}))]
        found = {}  # (league, event id) -> (team, event), from schedules until a scoreboard has a fuller copy
        boards = {(t.sport, lg, d) for t, lg in pairs if lg in DAILY for d in days}
        answered = 0  # if ESPN answers nothing at all, say so, so the HUD's health strip shows it
        for res in pool.map(lambda j: _safely(schedule, *j), jobs):
            if not res:
                continue
            answered += 1
            team, league, events = res
            for ev in events:
                at = datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
                if start <= at <= end:
                    found[(league, ev["id"])] = (team, ev)
                    boards.add((team.sport, league, at.astimezone(ESPN_DAY).strftime("%Y%m%d")))
        for res in pool.map(lambda b: _safely(scoreboard, *b), sorted(boards)):
            if not res:
                continue
            answered += 1
            league, events = res
            for ev in events:
                for team in (t for t, lg in pairs if lg == league):
                    if any((c.get("id") or c["team"]["id"]) == team.id for c in ev["competitions"][0]["competitors"]):
                        found[(league, ev["id"])] = (team, ev)

    if not answered and (jobs or boards):
        raise ConnectionError("ESPN didn't answer")
    games = [_safely(parse_game, ev, key[0], team, tz) for key, (team, ev) in found.items()]
    games = [g for g in games if g and start <= g.at <= end]
    scores = sorted((g for g in games if g.final and g.at <= now), key=lambda g: g.at, reverse=True)
    upcoming = sorted((g for g in games if not g.final and g.at >= now), key=lambda g: g.at)
    return scores, upcoming


def within(scores: list[Game], upcoming: list[Game], now: datetime, hours: int) -> tuple[list[Game], list[Game]]:
    """Only the games from the last and next `hours`."""
    edge = timedelta(hours=hours)
    return [g for g in scores if g.at >= now - edge], [g for g in upcoming if g.at <= now + edge]
