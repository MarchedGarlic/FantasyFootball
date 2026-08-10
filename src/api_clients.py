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

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_TIMEOUT = 15  # seconds
DEFAULT_MAX_WORKERS = 8


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

    def get_league_matchups_bulk(self, league_id, weeks, max_workers=DEFAULT_MAX_WORKERS):
        """Fetch matchups for multiple weeks concurrently. Returns {week: matchups}, omitting
        weeks with no data, in the same shape the old sequential loop produced."""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_week = {
                executor.submit(self.get_league_matchups, league_id, week): week
                for week in weeks
            }
            for future in as_completed(future_to_week):
                week = future_to_week[future]
                matchups = future.result()
                if matchups:
                    results[week] = matchups
        return results

    def get_league_transactions_bulk(self, league_id, weeks, max_workers=DEFAULT_MAX_WORKERS):
        """Fetch transactions for multiple weeks concurrently. Returns {week: transactions},
        omitting weeks with no data."""
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_week = {
                executor.submit(self.get_league_transactions, league_id, week): week
                for week in weeks
            }
            for future in as_completed(future_to_week):
                week = future_to_week[future]
                transactions = future.result()
                if transactions:
                    results[week] = transactions
        return results
