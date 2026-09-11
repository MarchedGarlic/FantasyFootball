#!/usr/bin/env python3
"""Unit tests for src/injury_severity.py's shared injury classification."""

from src.injury_severity import (
    injury_severity_tier,
    trade_value_discount_multiplier,
    start_sit_penalty,
)


def test_tier_classification_matches_real_sleeper_values():
    # The full set of non-null injury_status values observed in real Sleeper player data.
    assert injury_severity_tier(None) == 'healthy'
    assert injury_severity_tier('Out') == 'out'
    assert injury_severity_tier('IR') == 'out'
    assert injury_severity_tier('PUP') == 'out'
    assert injury_severity_tier('Sus') == 'out'
    assert injury_severity_tier('DNR') == 'out'
    assert injury_severity_tier('NA') == 'out'
    assert injury_severity_tier('Doubtful') == 'doubtful'
    assert injury_severity_tier('Questionable') == 'questionable'
    assert injury_severity_tier('COV') == 'questionable'
    assert injury_severity_tier('SomeUnknownFutureStatus') == 'healthy'


def test_trade_value_discount_gets_more_severe_with_status():
    healthy = trade_value_discount_multiplier(None)
    questionable = trade_value_discount_multiplier('Questionable')
    doubtful = trade_value_discount_multiplier('Doubtful')
    out = trade_value_discount_multiplier('Out')
    assert healthy == 1.0
    assert healthy > questionable > doubtful > out
    assert out > 0  # never worth literally zero - still real bench/stash value


def test_start_sit_penalty_gets_larger_with_severity():
    assert start_sit_penalty(None) == 0.0
    assert start_sit_penalty('Questionable') < start_sit_penalty('Doubtful') < start_sit_penalty('Out')
