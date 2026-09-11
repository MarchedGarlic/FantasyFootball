#!/usr/bin/env python3
"""Small helpers shared by multiple analysis modules."""


def get_manager_name(user_lookup, manager_id, prefix="Manager"):
    """Display name for a manager_id, falling back to '{prefix} {manager_id}' instead of
    raising when the manager is missing from user_lookup (e.g. a departed/unlinked manager)."""
    return (user_lookup or {}).get(manager_id, {}).get('display_name', f'{prefix} {manager_id}')


def week_has_been_played(matchups):
    """True if at least one team in this week's matchup list has a nonzero score.

    `all_weekly_matchups` is fetched for the whole season's week range up front (so features
    like "matchups to watch" can see next week's real pairings before it's played), but Sleeper
    pre-populates every future/unplayed week's `points`/`players_points` with 0.0 for every
    rostered player rather than omitting them (confirmed against live data mid-season). Any
    per-week loop that scores or aggregates results - not just pairing lookups - must skip a
    week where literally everyone is 0.0, or it silently treats "hasn't happened yet" as a real
    result: a wave of fake ties/median-wins/zero-point games stretching to the end of the
    season. A week where only some games have kicked off (a real Thursday-night score already
    in, Sunday's not yet) still counts as played - that is genuine partial data, not a
    placeholder, and should not be skipped.
    """
    return any((m.get('points') or 0) > 0 for m in (matchups or []))
