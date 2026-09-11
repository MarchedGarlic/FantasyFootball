#!/usr/bin/env python3
"""
Hypothetical Trade Analyzer: value any currently-rostered player (and FAAB) for "what if"
trades a manager is considering - not to be confused with src/trade_analysis.py, which scores
trades that already happened.

Methodology (see CLAUDE.md's Hypothetical Trade Analyzer section for the full writeup and the
research it's grounded in - established tools like FantasyCalc/DraftSharks/RotoTrade converge on
"Value Over Replacement" (a player's recent/projected points vs. a position baseline) for player
value and variance for floor/ceiling; this reuses exactly that idea with data already flowing
through this app instead of a paid ROS-projection API):

- A player's trade value blends two signals already computed elsewhere in this codebase: their
  ESPN-tier season-long grade (grade_player() - stable, "how good are they on paper") and their
  recent-weeks position-adjusted z-score (the same weekly-position-baseline machinery
  analyze_waiver_pickups() already built - "how are they playing right now"). Recency is
  weighted higher than in Draft Rating's quality/value blend (which is preseason, so quality
  dominates) - mid-season, recent form matters more, but one flukey week shouldn't fully
  override an established quality level either.
- Floor/ceiling are the player's own recent-weeks points, mean +/- one standard deviation - a
  real volatility measure from their actual game log, not a hand-picked range.
- FAAB is converted into the same grade-point scale player values use via this league's own
  empirically observed "value per dollar spent" (from analyze_waiver_pickups()' own scored
  history, already computed) rather than an arbitrary flat conversion, falling back to a
  documented constant only when the league doesn't have enough real FAAB spending yet to
  calibrate its own rate.
- A multi-team trade's fairness is just each team's own net value (value received - value given
  up, players and FAAB together) - the same per-manager attribution src/trade_analysis.py
  already uses for real 3+ team trades (CLAUDE.md section 4.1), not a bespoke N-way algorithm.
"""

import json
import statistics
from datetime import datetime

from src.trade_analysis import _build_weekly_position_baselines, _build_player_weekly_points
from src.ai_overview import _page_shell
from src.injury_severity import trade_value_discount_multiplier

RECENT_WEEKS_WINDOW = 4  # "current form" - long enough to smooth one flukey week, short enough
                          # to actually reflect recent performance rather than diluting into a
                          # season-long average a redraft trade shouldn't weight as heavily.
RECENT_FORM_WEIGHT = 0.6  # vs. 0.4 for the season-long ESPN-tier grade.
VALUE_Z_SCORE_SCALE = 2.5  # matches waiver/draft scoring's z-to-0-10 mapping (CLAUDE.md 4.5/5).
TRADABLE_POSITIONS = {'QB', 'RB', 'WR', 'TE'}  # kickers/DST have no ESPN-tier grade or
                                                 # meaningful position baseline here - excluded
                                                 # rather than given a fabricated value.
MIN_FAAB_SPENT_TO_CALIBRATE = 20.0  # below this, a league hasn't spent enough for its own
                                     # observed value-per-dollar to be trustworthy.
DEFAULT_FAAB_VALUE_PER_DOLLAR = 0.05  # z-score-equivalent per dollar when falling back - roughly
                                       # "a genuinely great ($30+) FAAB pickup is worth about as
                                       # much as a solidly-above-average week from a rostered
                                       # player," matching the "Elite Pickup" z >= 1.5 threshold
                                       # documented in trade_analysis.py's waiver methodology.


def _recent_weeks(weeks_sorted, window=RECENT_WEEKS_WINDOW):
    return weeks_sorted[-window:] if weeks_sorted else []


def calculate_player_trade_values(rosters, all_players, all_weekly_matchups, analyzer,
                                   roster_to_manager, user_lookup):
    """Every tradable (QB/RB/WR/TE) rostered player's current trade value, floor, and ceiling.

    Returns {player_id: {name, position, team, roster_id, manager_name, trade_value, floor,
    ceiling, recent_avg, espn_grade}}.
    """
    weeks_sorted = sorted((all_weekly_matchups or {}).keys())
    recent = _recent_weeks(weeks_sorted)
    player_weekly_points = _build_player_weekly_points(all_weekly_matchups)
    position_baselines = _build_weekly_position_baselines(all_weekly_matchups, all_players)

    values = {}
    for roster in rosters or []:
        roster_id = roster.get('roster_id')
        manager_id = roster_to_manager.get(roster_id)
        manager_name = (user_lookup or {}).get(manager_id, {}).get('display_name', 'Unknown')

        for player_id in roster.get('players') or []:
            info = (all_players or {}).get(player_id) or {}
            position = info.get('position')
            if position not in TRADABLE_POSITIONS:
                continue

            name = (info.get('full_name')
                    or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                    or f"Player_{player_id}")

            weekly_points = player_weekly_points.get(player_id, {})
            recent_points = [weekly_points[w] for w in recent if w in weekly_points]

            if recent_points:
                recent_avg = statistics.mean(recent_points)
                recent_stdev = (statistics.pstdev(recent_points) if len(recent_points) > 1
                                 else recent_avg * 0.3)
                z_scores = []
                for w in recent:
                    if w not in weekly_points:
                        continue
                    baseline = position_baselines.get(w, {}).get(position)
                    if not baseline or baseline['stdev'] <= 0:
                        continue
                    z_scores.append((weekly_points[w] - baseline['mean']) / baseline['stdev'])
                form_z = statistics.mean(z_scores) if z_scores else 0.0
            else:
                # No recent games (e.g. injured/bye every recent week) - fall back to the ESPN
                # grade alone rather than zeroing them out, which would undervalue a good
                # player who's simply been out.
                recent_avg = 0.0
                recent_stdev = 0.0
                form_z = None

            floor = max(0.0, recent_avg - recent_stdev)
            ceiling = recent_avg + recent_stdev

            espn_grade = analyzer.grade_player(name, position)['grade']
            if form_z is None:
                trade_value = espn_grade
            else:
                form_grade = max(0.0, min(10.0, 5.0 + form_z * VALUE_Z_SCORE_SCALE))
                trade_value = RECENT_FORM_WEIGHT * form_grade + (1 - RECENT_FORM_WEIGHT) * espn_grade

            # Injury discount is applied to the tradeable value only, not to floor/ceiling/
            # espn_grade - those describe the player's real performance range and season-long
            # quality, which don't change because they're hurt; what changes is how much of
            # that you can actually count on getting in a trade right now.
            injury_status = info.get('injury_status')
            discount = trade_value_discount_multiplier(injury_status)
            trade_value_pre_injury = trade_value
            trade_value = trade_value * discount

            values[player_id] = {
                'name': name,
                'position': position,
                'team': info.get('team') or 'FA',
                'roster_id': roster_id,
                'manager_name': manager_name,
                'trade_value': round(trade_value, 2),
                'floor': round(floor, 1),
                'ceiling': round(ceiling, 1),
                'recent_avg': round(recent_avg, 1),
                'espn_grade': round(espn_grade, 1),
                'injury_status': injury_status,
                'trade_value_pre_injury': round(trade_value_pre_injury, 2),
            }

    return values


def calculate_faab_value_per_dollar(waiver_impacts):
    """This league's own observed z-score-equivalent value per FAAB dollar spent, from its
    actual waiver activity (already scored by analyze_waiver_pickups()) - falls back to a
    documented constant only when there isn't enough real spending yet to trust the rate.
    """
    total_impact = 0.0
    total_spent = 0.0
    for w in waiver_impacts or []:
        spent = w.get('faab_spent')
        if spent:
            total_spent += spent
            total_impact += w.get('combined_impact', 0.0)

    if total_spent >= MIN_FAAB_SPENT_TO_CALIBRATE:
        rate = total_impact / total_spent
        # A league where FAAB spends happened to score below-average on balance says something
        # about this league's waiver bidding, not about the intrinsic value of holding FAAB -
        # having the resource is never worth *less* than nothing, so a non-positive observed
        # rate falls back to the documented default instead of making it a trade liability.
        if rate > 0:
            return rate
    return DEFAULT_FAAB_VALUE_PER_DOLLAR


def calculate_faab_trade_value(amount, faab_value_per_dollar):
    """FAAB dollars converted into the same grade-point scale calculate_player_trade_values()
    uses, so a trade leg's net value can just sum players and FAAB together - amount is a pure
    magnitude (added when received, subtracted when given), not an absolute 0-10 level the way
    a player's own trade_value is.
    """
    return round(amount * faab_value_per_dollar * VALUE_Z_SCORE_SCALE, 2)


def build_trade_analyzer_data(rosters, all_players, all_weekly_matchups, analyzer,
                               roster_to_manager, user_lookup, faab_ledger, waiver_impacts):
    """Everything the client-side trade builder needs, as one JSON-serializable dict - embedded
    directly in trade_analyzer.html the same way ai_overview.py embeds matchup_results, so the
    static Netlify build works identically to the live Flask app (see CLAUDE.md section 5's
    week-interactive sections for why: no server round-trip for a static export).
    """
    player_values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, analyzer, roster_to_manager, user_lookup
    )

    faab_enabled = bool(faab_ledger and faab_ledger.get('enabled'))
    faab_value_per_dollar = calculate_faab_value_per_dollar(waiver_impacts) if faab_enabled else 0.0
    # Pre-multiplied so the client-side trade builder just does amount * this constant, instead
    # of re-deriving the z-score-to-grade-point math in JS and risking the two implementations
    # drifting apart.
    faab_grade_points_per_dollar = calculate_faab_trade_value(1.0, faab_value_per_dollar) if faab_enabled else 0.0

    teams = {}
    for roster in rosters or []:
        roster_id = roster.get('roster_id')
        manager_id = roster_to_manager.get(roster_id)
        manager_name = (user_lookup or {}).get(manager_id, {}).get('display_name', 'Unknown')
        player_ids = [
            pid for pid in (roster.get('players') or [])
            if pid in player_values
        ]
        teams[roster_id] = {
            'manager_name': manager_name,
            'player_ids': player_ids,
            'faab_balance': (faab_ledger or {}).get('balances', {}).get(roster_id, 0.0) if faab_enabled else None,
        }

    return {
        'players': player_values,
        'teams': teams,
        'faab_enabled': faab_enabled,
        'faab_grade_points_per_dollar': round(faab_grade_points_per_dollar, 4),
        'recent_weeks_window': RECENT_WEEKS_WINDOW,
    }


# ---- rendering: an interactive "what if" trade builder, not a computed report ----
# Client-side and self-contained (the trade data is embedded as JSON, same as ai_overview.py's
# week-interactive sections) so this works identically on the static Netlify build and the live
# Flask app - no server round-trip to price a hypothetical trade.

_TRADE_ANALYZER_STYLE = """<style>
    .trade-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
    .trade-add-btn {
        background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent);
        border-radius: 980px; padding: 9px 18px; font-weight: 600; font-size: 0.88rem; cursor: pointer;
    }
    .trade-add-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .trade-teams { display: flex; flex-direction: column; gap: 16px; }
    .trade-team-card { background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 16px; }
    .trade-team-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
    .trade-team-head select {
        flex: 1; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line);
        background: var(--void); color: var(--ink); font-family: var(--font-sans); font-size: 0.95rem;
    }
    .trade-remove-btn {
        background: none; border: 1px solid var(--line); color: var(--ink-muted); border-radius: 10px;
        width: 36px; height: 36px; font-size: 1.1rem; cursor: pointer; flex-shrink: 0;
    }
    .trade-search {
        width: 100%; padding: 9px 12px; border-radius: 10px; border: 1px solid var(--line);
        background: var(--void); color: var(--ink); font-family: var(--font-sans); font-size: 0.9rem;
        margin-bottom: 8px;
    }
    .trade-player-list { max-height: 260px; overflow-y: auto; border: 1px solid var(--line); border-radius: 12px; }
    .trade-player-row { display: flex; align-items: center; gap: 10px; padding: 9px 10px; border-bottom: 1px solid var(--line); }
    .trade-player-row:last-child { border-bottom: none; }
    .trade-player-row label { flex: 1; font-size: 0.88rem; cursor: pointer; }
    .trade-player-meta { color: var(--ink-muted); font-size: 0.78rem; }
    .trade-injury-tag { color: var(--bad); font-weight: 700; }
    .trade-player-value { font-weight: 700; color: var(--ink); font-size: 0.88rem; white-space: nowrap; }
    .trade-faab-row { display: flex; align-items: center; gap: 10px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--line); }
    .trade-faab-row input { width: 90px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--line); background: var(--void); color: var(--ink); font-family: var(--font-sans); }
    .trade-dest-select {
        padding: 6px 10px; border-radius: 980px; border: 1px solid var(--accent);
        background: var(--void); color: var(--accent); font-family: var(--font-sans);
        font-size: 0.82rem; font-weight: 600; flex-shrink: 0;
    }
    .trade-results { margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }
    .trade-result-card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
    .trade-result-name { font-weight: 600; }
    .trade-result-net { font-size: 1.3rem; font-weight: 700; font-family: var(--font-display); }
    .trade-verdict { text-align: center; font-size: 1.05rem; font-weight: 600; margin-top: 8px; padding: 12px; border-radius: 14px; background: var(--surface-raised); }
    @media (max-width: 640px) {
        .trade-player-value { font-size: 0.8rem; }
        .trade-result-net { font-size: 1.1rem; }
    }
</style>"""

_TRADE_ANALYZER_JS_TEMPLATE = r"""
const TRADE_DATA = __TRADE_DATA__;
const MAX_TEAMS = 5;
let slots = [];
let searchTerms = [];

function otherPickedSlots(slotIdx) {
    const opts = [];
    slots.forEach((s, i) => { if (i !== slotIdx && s.rosterId != null) opts.push(i); });
    return opts;
}

function pickedRosterIds() {
    return slots.map(s => s.rosterId).filter(x => x != null);
}

function addTeam() {
    if (slots.length >= MAX_TEAMS) return;
    slots.push({ rosterId: null, sending: [] });
    searchTerms.push('');
    render();
}

function removeTeam(idx) {
    if (slots.length <= 2) return;
    slots.splice(idx, 1);
    searchTerms.splice(idx, 1);
    slots.forEach(s => {
        s.sending.forEach(item => {
            if (item.destSlot === idx) item.destSlot = null;
            else if (item.destSlot != null && item.destSlot > idx) item.destSlot -= 1;
        });
    });
    render();
}

function setTeam(idx, rosterIdStr) {
    slots[idx].rosterId = rosterIdStr === '' ? null : Number(rosterIdStr);
    slots[idx].sending = [];
    render();
}

function setSearch(idx, value) {
    searchTerms[idx] = value.toLowerCase();
    renderTeamList(idx);
}

function defaultDest(slotIdx) {
    const opts = otherPickedSlots(slotIdx);
    return opts.length ? opts[0] : null;
}

function togglePlayer(slotIdx, playerId, checked) {
    const slot = slots[slotIdx];
    if (checked) {
        slot.sending.push({ type: 'player', id: playerId, destSlot: defaultDest(slotIdx) });
    } else {
        slot.sending = slot.sending.filter(x => !(x.type === 'player' && x.id === playerId));
    }
    render();
}

function setFaab(slotIdx, amountStr) {
    const slot = slots[slotIdx];
    slot.sending = slot.sending.filter(x => x.type !== 'faab');
    const team = TRADE_DATA.teams[slot.rosterId];
    // The input's max="" attribute is a soft hint at best (nothing stops typing past it in
    // every browser) - clamp here too so a team can never offer more FAAB than they actually
    // have, since that's a real constraint of the hypothetical trade, not just a UI nicety.
    const amt = Math.min(parseFloat(amountStr) || 0, team.faab_balance);
    if (amt > 0) slot.sending.push({ type: 'faab', amount: amt, destSlot: defaultDest(slotIdx) });
    render();
}

function setDest(slotIdx, key, destStr) {
    const slot = slots[slotIdx];
    const item = slot.sending.find(x => (x.type === 'player' ? x.id : 'faab') === key);
    if (item) item.destSlot = destStr === '' ? null : Number(destStr);
    renderResults();
}

function computeResults() {
    const net = slots.map(() => 0);
    const received = slots.map(() => []);
    const sent = slots.map(() => []);

    slots.forEach((slot, i) => {
        if (slot.rosterId == null) return;
        slot.sending.forEach(item => {
            let value, label;
            if (item.type === 'player') {
                const p = TRADE_DATA.players[item.id];
                if (!p) return;
                value = p.trade_value;
                label = p.name + ' (' + p.position + ')';
            } else {
                value = item.amount * TRADE_DATA.faab_grade_points_per_dollar;
                label = '$' + item.amount + ' FAAB';
            }
            net[i] -= value;
            sent[i].push(label);
            if (item.destSlot != null && slots[item.destSlot] && slots[item.destSlot].rosterId != null) {
                net[item.destSlot] += value;
                received[item.destSlot].push(label);
            }
        });
    });
    return { net, received, sent };
}

function verdictFor(net) {
    const active = net.filter((_, i) => slots[i].rosterId != null);
    if (active.length < 2) return '';
    const spread = Math.max(...active) - Math.min(...active);
    if (spread < 1.0) return "Fair trade - close enough in value that it comes down to roster need.";
    if (spread < 3.0) return "Slight edge to one side, but defensible for the team giving up a bit of value.";
    if (spread < 6.0) return "Lopsided - the team on the short end should ask for more before agreeing.";
    return "Highly lopsided - this is the kind of trade that gets vetoed. Someone is getting scammed.";
}

function playerRowHtml(slotIdx, playerId) {
    const p = TRADE_DATA.players[playerId];
    const slot = slots[slotIdx];
    const sendingItem = slot.sending.find(x => x.type === 'player' && x.id === playerId);
    const checked = !!sendingItem;
    const destOptions = otherPickedSlots(slotIdx).map(i =>
        `<option value="${i}" ${sendingItem && sendingItem.destSlot === i ? 'selected' : ''}>${escapeHtml(TRADE_DATA.teams[slots[i].rosterId].manager_name)}</option>`
    ).join('');
    const injuryNote = p.injury_status
        ? ` - <span class="trade-injury-tag">${escapeHtml(p.injury_status)}</span> (value cut from ${p.trade_value_pre_injury.toFixed(1)})`
        : '';
    return `
        <div class="trade-player-row">
            <input type="checkbox" ${checked ? 'checked' : ''}
                onchange="togglePlayer(${slotIdx}, '${playerId}', this.checked)">
            <label onclick="const cb=this.previousElementSibling; cb.checked=!cb.checked; togglePlayer(${slotIdx}, '${playerId}', cb.checked);">
                ${escapeHtml(p.name)}
                <div class="trade-player-meta">${p.position} - ${escapeHtml(p.team)} - floor ${p.floor} / ceiling ${p.ceiling}${injuryNote}</div>
            </label>
            <div class="trade-player-value">${p.trade_value.toFixed(1)}</div>
            ${checked ? `<select class="trade-dest-select" onchange="setDest(${slotIdx}, '${playerId}', this.value)">
                <option value="">send to...</option>${destOptions}
            </select>` : ''}
        </div>
    `;
}

function renderTeamList(slotIdx) {
    const slot = slots[slotIdx];
    const listEl = document.getElementById('tradeList' + slotIdx);
    if (!listEl || slot.rosterId == null) return;
    const team = TRADE_DATA.teams[slot.rosterId];
    const term = searchTerms[slotIdx] || '';
    const ids = team.player_ids
        .filter(pid => TRADE_DATA.players[pid] && TRADE_DATA.players[pid].name.toLowerCase().includes(term))
        .sort((a, b) => TRADE_DATA.players[b].trade_value - TRADE_DATA.players[a].trade_value);
    listEl.innerHTML = ids.map(pid => playerRowHtml(slotIdx, pid)).join('') || '<p class="empty" style="padding:12px;">No matching players.</p>';
}

function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
}

function teamCardHtml(slotIdx) {
    const slot = slots[slotIdx];
    const usedIds = pickedRosterIds();
    const teamOptions = Object.keys(TRADE_DATA.teams).map(rid => {
        const ridNum = Number(rid);
        if (usedIds.includes(ridNum) && slot.rosterId !== ridNum) return '';
        return `<option value="${rid}" ${slot.rosterId === ridNum ? 'selected' : ''}>${escapeHtml(TRADE_DATA.teams[rid].manager_name)}</option>`;
    }).join('');

    let body = '';
    if (slot.rosterId != null) {
        const team = TRADE_DATA.teams[slot.rosterId];
        const faabItem = slot.sending.find(x => x.type === 'faab');
        // Destination selector only matters once 3+ teams are in the trade (with exactly 2,
        // there's only one place FAAB could go) - shown whenever there's an amount to route,
        // same as a player row only shows its "send to" select once checked.
        const faabDestOptions = otherPickedSlots(slotIdx).map(i =>
            `<option value="${i}" ${faabItem && faabItem.destSlot === i ? 'selected' : ''}>${escapeHtml(TRADE_DATA.teams[slots[i].rosterId].manager_name)}</option>`
        ).join('');
        const faabRow = TRADE_DATA.faab_enabled ? `
            <div class="trade-faab-row">
                <span>Send FAAB:</span>
                <input type="number" min="0" max="${team.faab_balance}" step="1" placeholder="$0"
                    value="${faabItem ? faabItem.amount : ''}"
                    onchange="setFaab(${slotIdx}, this.value)">
                <span class="trade-player-meta">of $${team.faab_balance} remaining</span>
                ${faabItem ? `<select class="trade-dest-select" onchange="setDest(${slotIdx}, 'faab', this.value)">
                    <option value="">send to...</option>${faabDestOptions}
                </select>` : ''}
            </div>
        ` : '';
        body = `
            <input class="trade-search" type="text" placeholder="Search ${escapeHtml(team.manager_name)}'s roster..."
                oninput="setSearch(${slotIdx}, this.value)">
            <div class="trade-player-list" id="tradeList${slotIdx}"></div>
            ${faabRow}
        `;
    }

    return `
        <div class="trade-team-card">
            <div class="trade-team-head">
                <select onchange="setTeam(${slotIdx}, this.value)">
                    <option value="">Select a team...</option>
                    ${teamOptions}
                </select>
                ${slots.length > 2 ? `<button class="trade-remove-btn" onclick="removeTeam(${slotIdx})" aria-label="Remove team">&times;</button>` : ''}
            </div>
            ${body}
        </div>
    `;
}

function renderResults() {
    const { net } = computeResults();
    const container = document.getElementById('tradeResults');
    const cards = slots.map((slot, i) => {
        if (slot.rosterId == null) return '';
        const team = TRADE_DATA.teams[slot.rosterId];
        const n = net[i];
        const color = n > 0.05 ? 'var(--good)' : n < -0.05 ? 'var(--bad)' : 'var(--ink-muted)';
        const sign = n > 0 ? '+' : '';
        return `
            <div class="trade-result-card">
                <span class="trade-result-name">${escapeHtml(team.manager_name)}</span>
                <span class="trade-result-net" style="color:${color};">${sign}${n.toFixed(1)}</span>
            </div>
        `;
    }).join('');
    const verdict = verdictFor(net);
    container.innerHTML = cards + (verdict ? `<div class="trade-verdict">${verdict}</div>` : '');
}

function autosizeSelf() {
    // This report's height changes constantly as the user builds out a trade (adding teams,
    // expanding a roster list) - long after the embedding page's own wireIframeAutosize() has
    // stopped watching (it disconnects its ResizeObserver ~8s after load, tuned for Bokeh's
    // brief async reflow on other reports, not a page that's interactive indefinitely). Same
    // origin, so this page can just resize its own iframe directly instead. Called synchronously
    // right after the DOM mutation that might have changed the page's height, not deferred via
    // requestAnimationFrame - reading a layout property like scrollHeight forces the browser to
    // resolve layout on demand, so the value is already correct without waiting for a paint.
    try {
        if (window.frameElement) {
            window.frameElement.style.height = document.documentElement.scrollHeight + 'px';
        }
    } catch (e) { /* not embedded in an iframe (e.g. opened via "Open full size") - fine */ }
}

function render() {
    document.getElementById('tradeTeams').innerHTML = slots.map((_, i) => teamCardHtml(i)).join('');
    document.getElementById('addTeamBtn').disabled = slots.length >= MAX_TEAMS;
    slots.forEach((slot, i) => { if (slot.rosterId != null) renderTeamList(i); });
    renderResults();
    autosizeSelf();
}

document.addEventListener('DOMContentLoaded', function () {
    slots = [{ rosterId: null, sending: [] }, { rosterId: null, sending: [] }];
    searchTerms = ['', ''];
    document.getElementById('addTeamBtn').addEventListener('click', addTeam);
    render();
});
"""


def build_trade_analyzer(output_data, rosters, all_players, all_weekly_matchups, analyzer,
                          roster_to_manager, user_lookup, faab_ledger, waiver_impacts):
    """Entry point mirroring build_ai_overview()/build_draft_info() - called from main.py to
    render trade_analyzer.html. Degrades to an empty-but-valid page (never a hard failure) if a
    league somehow has no tradable rostered players, matching every other report's pattern.
    """
    data = build_trade_analyzer_data(
        rosters, all_players, all_weekly_matchups, analyzer, roster_to_manager, user_lookup,
        faab_ledger, waiver_impacts,
    )

    analysis_info = output_data.get('analysis_info') or {}
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

    if not data['players']:
        body = "<p class='empty'>No tradable rostered players found for this league/season.</p>"
        return _page_shell(
            title=f"Trade Analyzer - {league_name} ({season})",
            header_title=f"{league_name} &mdash; Trade Analyzer",
            header_subtitle=f"Season {season} &middot; Generated {generated_at}",
            body_html=body,
        )

    body = f"""
    {_TRADE_ANALYZER_STYLE}
    <div class="section-card">
        <h2>Build a Hypothetical Trade</h2>
        <p class="section-caption">
            Pick 2-5 teams, choose who's sending what to whom (players and{' FAAB' if data['faab_enabled'] else ''}),
            and see who comes out ahead. Trade value blends each player's season-long ESPN-tier grade with
            their last {data['recent_weeks_window']} weeks of position-adjusted performance - floor and ceiling
            come from their own recent game-to-game swings, not a guess.
        </p>
        <div class="trade-toolbar">
            <span class="trade-player-meta">Nothing here is saved or sent to anyone - purely hypothetical.</span>
            <button id="addTeamBtn" class="trade-add-btn" type="button">+ Add Team</button>
        </div>
        <div class="trade-teams" id="tradeTeams"></div>
        <div class="trade-results" id="tradeResults"></div>
    </div>
    """

    js = _TRADE_ANALYZER_JS_TEMPLATE.replace('__TRADE_DATA__', json.dumps(data))
    extra_script = f"<script>{js}</script>"

    return _page_shell(
        title=f"Trade Analyzer - {league_name} ({season})",
        header_title=f"{league_name} &mdash; Trade Analyzer",
        header_subtitle=f"Season {season} &middot; Generated {generated_at}",
        body_html=body,
        extra_script=extra_script,
    )
