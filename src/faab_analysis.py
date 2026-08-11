#!/usr/bin/env python3
"""
FAAB (Free Agent Acquisition Budget) ledger reconstruction and relative-scarcity valuation.

Sleeper only exposes the *current* total waiver_budget_used per roster - never a running
balance over time. This module reconstructs that running balance by replaying every waiver and
FAAB-trade transaction in chronological order, then scores each spend not just by dollar amount
but by how much of the spender's own remaining budget it consumed, relative to what every other
manager had left at that same moment. See CLAUDE.md section 4.3 for the full writeup.

Only meaningful for leagues on FAAB waivers (Sleeper league settings: waiver_type == 2). For any
other waiver_type (rolling priority / reverse standings), is_faab_league() returns False and
callers should skip FAAB sections entirely.
"""

FAAB_WAIVER_TYPE = 2
MAX_SCARCITY_MULTIPLIER = 3.0  # caps the "you had almost nothing left" blowup term


def is_faab_league(league_settings):
    """True if this league uses FAAB bidding rather than rolling/reverse-standings waivers."""
    return (league_settings or {}).get('waiver_type') == FAAB_WAIVER_TYPE


def _score_spend(amount, balance_before, others_avg_before):
    """Score a single FAAB spend by relative scarcity. See CLAUDE.md section 4.3."""
    commitment_ratio = (amount / balance_before) if balance_before > 0 else 1.0
    relative_scarcity = (balance_before / others_avg_before) if others_avg_before > 0 else 1.0
    scarcity_multiplier = min(MAX_SCARCITY_MULTIPLIER, (1.0 / relative_scarcity) if relative_scarcity > 0 else MAX_SCARCITY_MULTIPLIER)
    aggressiveness_score = round(min(100.0, commitment_ratio * 100.0 * scarcity_multiplier), 1)
    return {
        'commitment_ratio': round(commitment_ratio, 3),
        'relative_scarcity': round(relative_scarcity, 3),
        'aggressiveness_score': aggressiveness_score,
    }


def _flatten_chronological(transactions_by_week):
    """Flatten {week_key: [transactions]} into one list sorted by (week, created timestamp)."""
    flattened = []
    for week_key, transactions in (transactions_by_week or {}).items():
        if not transactions:
            continue
        if isinstance(week_key, str) and 'Week' in week_key:
            week_num = int(week_key.split()[1])
        else:
            week_num = int(week_key)
        for transaction in transactions:
            if not transaction or not isinstance(transaction, dict):
                continue
            # Same lenient check trade_analysis.py/main.py use: treat a missing status the same
            # as 'complete' rather than skipping it, so the ledger never disagrees with what the
            # trade/waiver analysis counted as a real transaction.
            if transaction.get('status') not in (None, 'complete'):
                continue
            flattened.append((week_num, transaction.get('created') or 0, transaction))
    flattened.sort(key=lambda item: (item[0], item[1]))
    return flattened


def build_faab_ledger(transactions_by_week, rosters, league_settings):
    """Reconstruct every roster's FAAB balance over the season and score each spend.

    Returns a dict with 'enabled': False if the league doesn't use FAAB, otherwise a full
    ledger: per-roster starting/ending balances, a chronological list of scored events, and a
    per-week balance snapshot for every roster (used by the FAAB tracker panel).
    """
    if not is_faab_league(league_settings):
        return {'enabled': False}

    total_budget = float(league_settings.get('waiver_budget') or 100)
    roster_ids = [r.get('roster_id') for r in rosters if r.get('roster_id') is not None]
    balances = {rid: total_budget for rid in roster_ids}
    balance_by_roster_and_week = {rid: {} for rid in roster_ids}

    events = []

    for week_num, _created, transaction in _flatten_chronological(transactions_by_week):
        transaction_type = transaction.get('type')
        transaction_id = transaction.get('transaction_id')

        if transaction_type == 'trade':
            for transfer in (transaction.get('waiver_budget') or []):
                sender = transfer.get('sender')
                receiver = transfer.get('receiver')
                amount = float(transfer.get('amount') or 0)
                if not amount or sender not in balances or receiver not in balances:
                    continue

                sender_before = balances[sender]
                receiver_before = balances[receiver]
                others_avg = _average_others(balances, sender)
                score = _score_spend(amount, sender_before, others_avg)
                balances[sender] -= amount
                balances[receiver] += amount

                events.append({
                    'week': week_num, 'transaction_id': transaction_id, 'source': 'trade',
                    'roster_id': sender, 'direction': 'spend', 'amount': amount,
                    'balance_before': round(sender_before, 2), 'balance_after': round(balances[sender], 2),
                    'others_avg_balance_before': round(others_avg, 2), **score,
                })
                events.append({
                    'week': week_num, 'transaction_id': transaction_id, 'source': 'trade',
                    'roster_id': receiver, 'direction': 'receive', 'amount': amount,
                    'balance_before': round(receiver_before, 2),
                    'balance_after': round(balances[receiver], 2),
                })

        else:
            roster_ids_involved = transaction.get('roster_ids') or []
            waiver_bid = (transaction.get('settings') or {}).get('waiver_bid')
            if not waiver_bid or len(roster_ids_involved) != 1:
                continue

            roster_id = roster_ids_involved[0]
            if roster_id not in balances:
                continue

            amount = float(waiver_bid)
            balance_before = balances[roster_id]
            others_avg = _average_others(balances, roster_id)
            score = _score_spend(amount, balance_before, others_avg)
            balances[roster_id] -= amount

            events.append({
                'week': week_num, 'transaction_id': transaction_id, 'source': 'waiver',
                'roster_id': roster_id, 'direction': 'spend', 'amount': amount,
                'balance_before': round(balance_before, 2), 'balance_after': round(balances[roster_id], 2),
                'others_avg_balance_before': round(others_avg, 2), **score,
            })

        for rid in roster_ids:
            balance_by_roster_and_week[rid][week_num] = round(balances[rid], 2)

    warnings = _cross_check(balances, rosters, total_budget)

    return {
        'enabled': True,
        'total_budget': total_budget,
        'balances': {rid: round(bal, 2) for rid, bal in balances.items()},
        'events': events,
        'balance_by_roster_and_week': balance_by_roster_and_week,
        'warnings': warnings,
    }


def _average_others(balances, exclude_roster_id):
    others = [bal for rid, bal in balances.items() if rid != exclude_roster_id]
    return (sum(others) / len(others)) if others else 0.0


def _cross_check(computed_balances, rosters, total_budget):
    """Compare our reconstructed balance against Sleeper's own waiver_budget_used, which
    reflects any commissioner-made adjustments our replay wouldn't see. Mismatches are
    surfaced as warnings, not treated as fatal - the relative scoring is still directionally
    useful even if a manual adjustment happened."""
    warnings = []
    for roster in rosters:
        roster_id = roster.get('roster_id')
        if roster_id not in computed_balances:
            continue
        used = (roster.get('settings') or {}).get('waiver_budget_used')
        if used is None:
            continue
        expected_balance = total_budget - used
        if abs(expected_balance - computed_balances[roster_id]) > 0.5:
            warnings.append(
                f"Roster {roster_id}: reconstructed balance {computed_balances[roster_id]:.2f} "
                f"does not match Sleeper's reported balance {expected_balance:.2f} "
                f"(likely a commissioner FAAB adjustment outside normal transactions)"
            )
    return warnings


def faab_leaderboard(ledger, roster_to_manager, user_lookup):
    """Season-long aggressiveness leaderboard: total spent, average aggressiveness score,
    and current remaining balance per manager. Empty list if FAAB isn't enabled."""
    if not ledger or not ledger.get('enabled'):
        return []

    per_roster = {}
    for event in ledger['events']:
        if event['direction'] != 'spend':
            continue
        roster_id = event['roster_id']
        per_roster.setdefault(roster_id, {'total_spent': 0.0, 'scores': []})
        per_roster[roster_id]['total_spent'] += event['amount']
        per_roster[roster_id]['scores'].append(event['aggressiveness_score'])

    leaderboard = []
    for roster_id, remaining in ledger['balances'].items():
        manager_id = roster_to_manager.get(roster_id)
        manager_name = user_lookup.get(manager_id, {}).get('display_name', f'Manager {manager_id}')
        stats = per_roster.get(roster_id, {'total_spent': 0.0, 'scores': []})
        avg_aggressiveness = round(sum(stats['scores']) / len(stats['scores']), 1) if stats['scores'] else 0.0

        leaderboard.append({
            'roster_id': roster_id,
            'manager_id': manager_id,
            'manager_name': manager_name,
            'total_spent': round(stats['total_spent'], 2),
            'remaining_balance': remaining,
            'total_budget': ledger['total_budget'],
            'avg_aggressiveness_score': avg_aggressiveness,
            'num_spends': len(stats['scores']),
        })

    leaderboard.sort(key=lambda row: row['total_spent'], reverse=True)
    return leaderboard
