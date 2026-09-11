#!/usr/bin/env python3
"""
API Clients Module
Handles external API connections for ESPN and Sleeper data.

Every request carries a timeout and automatic retry/backoff on transient failures (connection
errors and 429/500/502/503/504), so a single flaky response degrades to a clear exception instead
of hanging forever or silently returning empty data that looks like "nothing happened this week".
Bulk fetch helpers (weekly matchups/transactions, ESPN athlete details) use a thread pool since a
full-season analysis previously made these calls one at a time, sequentially.
"""

import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 15  # seconds
DEFAULT_MAX_WORKERS = 8

# The only confirmed disagreement between ESPN's and Sleeper's team abbreviations (checked
# against a real week's scoreboard vs. the full Sleeper player pool) - Washington. Every other
# team's code matches. Keyed by ESPN's abbreviation, valued as Sleeper's.
ESPN_TO_SLEEPER_TEAM = {'WSH': 'WAS'}


def _build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(['GET']),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


class ESPNAPI:
    """ESPN Core API wrapper used for season stat leaders (player value ranking source)."""

    def __init__(self):
        self.session = _build_session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def get(self, url, params=None):
        """Shared GET with the module's timeout - used directly by roster_grading's
        athlete/position/team $ref lookups so they get the same timeout/retry behavior."""
        return self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)

    def get_nfl_leaders(self, season, storage=None, cache_max_age=86400):
        """Get NFL statistical leaders for a season using the Core API.

        Cached on disk for cache_max_age seconds (default 24h) via `storage` if provided,
        since this payload only changes as games are played, not on every analysis run.
        """
        cache_key = f"espn_rankings_{season}"
        if storage is not None:
            cached = storage.cache_get(cache_key, cache_max_age)
            if cached is not None:
                return cached

        url = f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/{season}/types/2/leaders"
        response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
        data = response.json() if response.status_code == 200 else None

        if data is not None and storage is not None:
            storage.cache_set(cache_key, data)

        return data

    def get_preseason_draft_ranks(self, season, storage=None, cache_max_age=604800):
        """Every player's ESPN preseason expert-consensus draft rank for a season (both
        STANDARD and PPR rank types), used as the 'where the market expected this player to go'
        baseline for the Biggest Steals / Draft Rating sections.

        This is ESPN's own preseason ranking, not crowd-sourced ADP - ESPN's
        `ownership.averageDraftPosition` field was checked and confirmed broken (returns a flat
        170.0 placeholder for every player, elite or not, as of 2026-09), so `draftRanksByRankType`
        is used instead; it was verified to return correctly-ordered, season-accurate ranks.
        Cached for 7 days by default (longer than other ESPN data) since a season's preseason
        ranks don't change once the season is under way.
        """
        cache_key = f"espn_draft_ranks_{season}"
        if storage is not None:
            cached = storage.cache_get(cache_key, cache_max_age)
            if cached is not None:
                return cached

        url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}/segments/0/leaguedefaults/3"
        headers = {
            'X-Fantasy-Filter': json.dumps({
                'players': {
                    'limit': 3000,
                    'sortDraftRanks': {'sortPriority': 100, 'sortAsc': True, 'value': 'STANDARD'},
                    'filterRanksForRankTypes': {'value': ['STANDARD', 'PPR']},
                }
            }),
            'X-Fantasy-Source-Type': '1',
        }
        response = self.session.get(url, params={'view': 'kona_player_info'}, headers=headers, timeout=DEFAULT_TIMEOUT)
        raw = response.json() if response.status_code == 200 else None

        ranks = None
        if raw and isinstance(raw, dict) and raw.get('players'):
            ranks = {}
            for entry in raw['players']:
                player = entry.get('player') or {}
                name = player.get('fullName')
                rank_types = player.get('draftRanksByRankType') or {}
                if not name or not rank_types:
                    continue
                ranks[name.lower()] = {
                    'standard_rank': (rank_types.get('STANDARD') or {}).get('rank'),
                    'ppr_rank': (rank_types.get('PPR') or {}).get('rank'),
                }

        if ranks is not None and storage is not None:
            storage.cache_set(cache_key, ranks)

        return ranks or {}

    def get_weekly_schedule(self, week, season, storage=None, cache_max_age=21600):
        """Which NFL team played which that week, as {team_abbr: opponent_abbr} (both
        directions included) - the input to src/start_sit.py's defense-vs-position calculation
        and to knowing each rostered player's upcoming opponent. A completed week's schedule
        never changes, but this is cached at a shorter 6h TTL than the season-long caches above
        since it's also used for the *upcoming* week, whose game (bye weeks, flex scheduling)
        can still move before kickoff.

        Sleeper and ESPN don't always agree on team abbreviations (confirmed empirically:
        ESPN's Washington is 'WSH', Sleeper's is 'WAS') - normalized here so every other module
        can key off Sleeper's abbreviations (what `all_players[pid]['team']` uses) without
        worrying about the mismatch.
        """
        cache_key = f"espn_schedule_{season}_wk{week}"
        if storage is not None:
            cached = storage.cache_get(cache_key, cache_max_age)
            if cached is not None:
                return cached

        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        params = {'week': week, 'seasontype': 2, 'year': season}
        response = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        data = response.json() if response.status_code == 200 else None

        schedule = {}
        if data and isinstance(data, dict):
            for event in data.get('events', []):
                competitors = (event.get('competitions') or [{}])[0].get('competitors', [])
                if len(competitors) != 2:
                    continue
                abbrevs = [ESPN_TO_SLEEPER_TEAM.get(
                    c.get('team', {}).get('abbreviation'), c.get('team', {}).get('abbreviation')
                ) for c in competitors]
                if all(abbrevs):
                    schedule[abbrevs[0]] = abbrevs[1]
                    schedule[abbrevs[1]] = abbrevs[0]

        if schedule and storage is not None:
            storage.cache_set(cache_key, schedule)

        return schedule

    def get_weekly_schedule_bulk(self, weeks, season, storage=None, max_workers=DEFAULT_MAX_WORKERS):
        """get_weekly_schedule() for multiple weeks concurrently - same bulk-fetch pattern as
        SleeperAPI's matchup/transaction fetchers. Returns {week: {team: opponent}}, omitting
        weeks with no schedule data (bye week is a "no game" gap and stays absent naturally)."""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_week = {
                executor.submit(self.get_weekly_schedule, week, season, storage): week
                for week in weeks
            }
            for future in as_completed(future_to_week):
                week = future_to_week[future]
                schedule = future.result()
                if schedule:
                    results[week] = schedule
        return results


class SleeperAPI:
    """Sleeper API wrapper for fantasy football league/roster/transaction data."""

    def __init__(self):
        self.session = _build_session()
        self.base_url = "https://api.sleeper.app/v1"

    def _get(self, path, default=None):
        url = f"{self.base_url}{path}"
        response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
        return response.json() if response.status_code == 200 else default

    def get_user_by_username(self, username):
        """Get user by username"""
        return self._get(f"/user/{username}", default=None)

    def get_user_leagues(self, user_id, season, sport="nfl"):
        """Get leagues for a user in a given season"""
        return self._get(f"/user/{user_id}/leagues/{sport}/{season}", default=[])

    def get_league_info(self, league_id):
        """Get detailed league information, including settings (waiver_type, waiver_budget,
        playoff_week_start, playoff_teams, etc)."""
        return self._get(f"/league/{league_id}", default=None)

    def get_league_rosters(self, league_id):
        """Get all rosters for a league"""
        return self._get(f"/league/{league_id}/rosters", default=[])

    def get_league_users(self, league_id):
        """Get all users in a league"""
        return self._get(f"/league/{league_id}/users", default=[])

    def get_league_matchups(self, league_id, week):
        """Get matchups for a specific week"""
        return self._get(f"/league/{league_id}/matchups/{week}", default=[])

    def get_league_transactions(self, league_id, week):
        """Get transactions for a specific week"""
        return self._get(f"/league/{league_id}/transactions/{week}", default=[])

    def get_traded_picks(self, league_id):
        """Get all traded draft picks in a league"""
        return self._get(f"/league/{league_id}/traded_picks", default=[])

    def get_league_drafts(self, league_id):
        """Get every draft associated with a league (a normal redraft league has exactly one)."""
        return self._get(f"/league/{league_id}/drafts", default=[])

    def get_draft_picks(self, draft_id):
        """Get every pick made in a draft: round, overall pick number, player, and the roster
        that made the pick."""
        return self._get(f"/draft/{draft_id}/picks", default=[])

    def get_nfl_state(self):
        """Get current NFL week/season state - used to default the season picker to the
        current season instead of a hardcoded year."""
        return self._get("/state/nfl", default=None)

    def get_all_players(self, sport="nfl", storage=None, cache_max_age=86400):
        """Get all players (~5MB). Sleeper's own docs say to fetch this at most once a day;
        cached on disk via `storage` if provided instead of re-fetching on every run."""
        cache_key = f"players_{sport}"
        if storage is not None:
            cached = storage.cache_get(cache_key, cache_max_age)
            if cached is not None:
                return cached

        data = self._get(f"/players/{sport}", default={})

        if data and storage is not None:
            storage.cache_set(cache_key, data)

        return data

    def _fetch_weeks_bulk(self, fetch_one_week, weeks, max_workers):
        """Fetch per-week data concurrently via fetch_one_week(week). Returns {week: data},
        omitting weeks with no data. A week whose request still fails after the Retry
        adapter's retries are exhausted is logged and skipped rather than aborting every other
        week's already-successful result."""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_week = {
                executor.submit(fetch_one_week, week): week
                for week in weeks
            }
            for future in as_completed(future_to_week):
                week = future_to_week[future]
                try:
                    data = future.result()
                except Exception as e:
                    print(f"   [WARNING] Failed to fetch week {week}: {e}")
                    continue
                if data:
                    results[week] = data
        return results

    def get_league_matchups_bulk(self, league_id, weeks, max_workers=DEFAULT_MAX_WORKERS):
        """Fetch matchups for multiple weeks concurrently. Returns {week: matchups}, omitting
        weeks with no data, in the same shape the old sequential loop produced."""
        return self._fetch_weeks_bulk(
            lambda week: self.get_league_matchups(league_id, week), weeks, max_workers
        )

    def get_league_transactions_bulk(self, league_id, weeks, max_workers=DEFAULT_MAX_WORKERS):
        """Fetch transactions for multiple weeks concurrently. Returns {week: transactions},
        omitting weeks with no data."""
        return self._fetch_weeks_bulk(
            lambda week: self.get_league_transactions(league_id, week), weeks, max_workers
        )
