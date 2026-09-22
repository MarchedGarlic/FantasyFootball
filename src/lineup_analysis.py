#!/usr/bin/env python3
"""
Lineup Efficiency ("Start/Sit Accuracy") Analysis

Compares each manager's actual starting lineup, week by week, against the best lineup they
could have started from their own full roster (starters + bench) that week. This is the real
signal the Manager Grades panel has always claimed to use ("start/sit accuracy - optimal lineup
decisions vs. actual ones") but never actually computed - see CLAUDE.md section 4.6.

The optimal lineup is a maximum-weight bipartite matching between starting slots (from the
league's own `roster_positions`, including FLEX-style slots) and rostered players eligible for
each slot, solved with scipy's Hungarian algorithm (`linear_sum_assignment`).
"""

import numpy as np
from scipy.optimize import linear_sum_assignment

# Slots that never hold an active player and so aren't part of the "should you have started
# someone else" question.
NON_STARTING_SLOTS = {'BN', 'IR', 'TAXI'}

# Sleeper's flex-style slot labels and which real positions can fill them. Any slot not listed
# here (QB, RB, WR, TE, K, DEF, ...) is eligible only for players whose own position matches the
# slot name exactly.
FLEX_ELIGIBILITY = {
    'FLEX': {'RB', 'WR', 'TE'},
    'WRRB_FLEX': {'RB', 'WR'},
    'REC_FLEX': {'WR', 'TE'},
    'WRTE_FLEX': {'WR', 'TE'},
    'SUPER_FLEX': {'QB', 'RB', 'WR', 'TE'},
    'IDP_FLEX': {'DL', 'LB', 'DB'},
}


def slot_eligible_positions(slot):
    """Real player positions allowed to fill a given roster slot."""
    return FLEX_ELIGIBILITY.get(slot, {slot})


def starting_slots_from_roster_positions(roster_positions):
    """The league's starting-lineup shape (one entry per slot to fill), in the order Sleeper
    lists them, with bench/IR/taxi slots dropped since they're never "started"."""
    return [slot for slot in (roster_positions or []) if slot not in NON_STARTING_SLOTS]


def compute_optimal_lineup_points(player_ids, players_points, player_positions, starting_slots):
    """Best total score this roster could have started this week, given the league's starting
    slots. Returns (optimal_points, {slot: player_id}) - the assignment is the actual optimal
    lineup, not just its point total, so callers can show "who should've started" if they want.

    Solved as a maximum-weight assignment (Hungarian algorithm via
    `scipy.optimize.linear_sum_assignment`, run on negated points so a min-cost solve maximizes
    points) rather than a greedy fill - a greedy "best player first" pass can lock in a player for
    an early flex-eligible slot and miss a better overall combination once later slots are
    considered, which a real assignment solve does not.
    """
    slots = list(starting_slots or [])
    players = [pid for pid in (player_ids or []) if pid]
    if not slots or not players:
        return 0.0, {}

    ineligible_cost = 1e6
    cost = np.full((len(slots), len(players)), ineligible_cost)
    for i, slot in enumerate(slots):
        eligible = slot_eligible_positions(slot)
        for j, pid in enumerate(players):
            if player_positions.get(pid) in eligible:
                cost[i, j] = -(players_points.get(pid) or 0.0)

    row_idx, col_idx = linear_sum_assignment(cost)

    optimal_points = 0.0
    assignment = {}
    for r, c in zip(row_idx, col_idx):
        if cost[r, c] >= ineligible_cost:
            continue  # no rostered player was eligible for this slot at all
        pid = players[c]
        optimal_points += players_points.get(pid) or 0.0
        assignment[slots[r]] = pid

    return optimal_points, assignment


def calculate_lineup_efficiency(all_weekly_matchups, roster_to_manager, all_players, roster_positions):
    """Per-manager, per-week actual-vs-optimal lineup comparison - the real start/sit accuracy
    data. Returns {manager_id: {week: {actual_points, optimal_points, points_left_on_bench,
    efficiency}}}, `efficiency` = actual_points / optimal_points (1.0 = started the best possible
    lineup that week).
    """
    starting_slots = starting_slots_from_roster_positions(roster_positions)
    player_positions = {
        pid: (info or {}).get('position')
        for pid, info in (all_players or {}).items()
    }

    efficiency_by_manager = {}
    for week, matchups in (all_weekly_matchups or {}).items():
        for team in matchups or []:
            roster_id = team.get('roster_id')
            manager_id = roster_to_manager.get(roster_id)
            if manager_id is None:
                continue

            players_points = team.get('players_points') or {}
            player_ids = team.get('players') or list(players_points.keys())
            starters = [pid for pid in (team.get('starters') or []) if pid and pid != '0']

            actual_points = sum((players_points.get(pid) or 0.0) for pid in starters)
            optimal_points, _ = compute_optimal_lineup_points(
                player_ids, players_points, player_positions, starting_slots
            )
            # The optimal solve is a ceiling on what the actual lineup could have scored, never a
            # floor - if missing/incomplete points data ever made it look lower than what was
            # actually started, don't let it produce an efficiency above 100%.
            optimal_points = max(optimal_points, actual_points)

            if optimal_points <= 0:
                continue

            efficiency_by_manager.setdefault(manager_id, {})[week] = {
                'actual_points': round(actual_points, 2),
                'optimal_points': round(optimal_points, 2),
                'points_left_on_bench': round(optimal_points - actual_points, 2),
                'efficiency': actual_points / optimal_points,
            }

    return efficiency_by_manager
