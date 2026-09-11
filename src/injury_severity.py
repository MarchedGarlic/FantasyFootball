#!/usr/bin/env python3
"""
Shared injury-severity classification, used by both src/trade_value.py (discount a hurt
player's trade value) and src/start_sit.py (recommend sitting a hurt player / starting their
likely replacement).

Tiers follow the NFL's own official practice-report designations (Out / Doubtful / Questionable
- in decreasing order of "will not play this week"), extended to cover Sleeper's other
`injury_status` values that carry the same practical meaning (checked against real Sleeper
player data - the full set of non-null values seen there is Questionable, Doubtful, Out, IR,
PUP, Sus, COV, NA, DNR).
"""

# Player is not expected to be available at all this week (or, for Sus, isn't injured but is
# just as unavailable for fantasy purposes).
OUT_STATUSES = {'Out', 'IR', 'PUP', 'Sus', 'DNR', 'NA'}
# Officially unlikely to play, but not a certainty.
DOUBTFUL_STATUSES = {'Doubtful'}
# Uncertain - genuinely could go either way.
QUESTIONABLE_STATUSES = {'Questionable', 'COV'}

# Trade-value discount multipliers (CLAUDE.md: "severe injury reduces value a lot, mild
# reduces it, but not as much"). Applied to a player's trade_value in src/trade_value.py.
TRADE_VALUE_DISCOUNT = {
    'out': 0.5,          # long-term/confirmed-out - half value, not zero: bench stash value,
                          # and "Out" this week isn't necessarily out next week.
    'doubtful': 0.75,
    'questionable': 0.9,
    'healthy': 1.0,
}

# Start/sit score penalty (subtracted from the player's own matchup/form score, on the same
# roughly 0-10 grade-point scale src/start_sit.py works in).
START_SIT_PENALTY = {
    'out': 6.0,          # effectively forces a Sit verdict regardless of matchup
    'doubtful': 3.5,
    'questionable': 1.0,  # a real but small ding - a questionable player still often plays
    'healthy': 0.0,
}


def injury_severity_tier(injury_status):
    """Classify a Sleeper `injury_status` string into 'out' / 'doubtful' / 'questionable' /
    'healthy'. None or an unrecognized value is treated as healthy rather than guessed at."""
    if not injury_status:
        return 'healthy'
    if injury_status in OUT_STATUSES:
        return 'out'
    if injury_status in DOUBTFUL_STATUSES:
        return 'doubtful'
    if injury_status in QUESTIONABLE_STATUSES:
        return 'questionable'
    return 'healthy'


def trade_value_discount_multiplier(injury_status):
    return TRADE_VALUE_DISCOUNT[injury_severity_tier(injury_status)]


def start_sit_penalty(injury_status):
    return START_SIT_PENALTY[injury_severity_tier(injury_status)]
