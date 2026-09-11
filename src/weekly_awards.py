#!/usr/bin/env python3
"""
Weekly Awards: a lighthearted per-week recap - explicit user request, reframed from a season-long
awards page to a weekly one ("I would love the season awards page, but make it weekly awards").

Every award is derived from data this app already computes elsewhere (matchup results, the
upset-detection already used by the AI Overview, waiver-pickup position-adjusted z-scores, the
FAAB ledger's commitment-ratio scoring) plus one new computation: an "optimal lineup" solve, used
for the Bench Blunder / Lineup Ninja awards, that finds how many points a manager left on their
bench that week given their actual roster slots.
"""

import json
from collections import defaultdict
from datetime import datetime

from src.ai_overview import _page_shell, biggest_upsets

# Sleeper roster slot -> eligible positions, for the slots actually seen across common league
# formats (standard + the flex/IDP variants Sleeper supports). A slot name not listed here is
# treated as its own literal position (e.g. 'QB', 'DEF', 'K') - the correct fallback, since every
# single-position slot's name already matches the position string Sleeper puts on the player.
FLEX_ELIGIBILITY = {
    'FLEX': {'RB', 'WR', 'TE'},
    'WRRB_FLEX': {'RB', 'WR'},
    'WR_RB': {'RB', 'WR'},
    'REC_FLEX': {'WR', 'TE'},
    'WR_TE': {'WR', 'TE'},
    'SUPER_FLEX': {'QB', 'RB', 'WR', 'TE'},
    'SUPERFLEX': {'QB', 'RB', 'WR', 'TE'},
    'IDP_FLEX': {'DL', 'LB', 'DB'},
}
NON_STARTING_SLOTS = {'BN', 'IR', 'TAXI'}
MIN_NOTABLE_BENCH_POINTS = 0.5  # below this, "left points on the bench" isn't a real story


def _optimal_lineup_points(team, all_players, roster_positions):
    """Best total this roster could have scored that week from its own actual players, given its
    real roster slots. Greedy, most-restrictive-slot-first assignment (fill single-position slots
    first, then flex slots ordered by fewest eligible positions) rather than a full bipartite-
    matching solve - the same heuristic real "optimal lineup" tools use in practice, since a real
    fantasy roster essentially never produces a case where this disagrees with the true optimum
    (that would need two-plus flex slots simultaneously contested by players eligible for only
    the scarcer one). Returns None if this league's roster_positions aren't available.
    """
    starting_slots = [s for s in (roster_positions or []) if s not in NON_STARTING_SLOTS]
    if not starting_slots:
        return None

    points_by_player = team.get('players_points') or {}
    pool = []
    for player_id in (team.get('players') or []):
        points = points_by_player.get(player_id)
        if points is None:
            continue
        position = (all_players or {}).get(player_id, {}).get('position')
        if not position:
            continue
        pool.append({'player_id': player_id, 'position': position, 'points': float(points)})

    ordered_slots = sorted(starting_slots, key=lambda slot: len(FLEX_ELIGIBILITY.get(slot, {slot})))

    used_ids = set()
    total = 0.0
    for slot in ordered_slots:
        eligible = FLEX_ELIGIBILITY.get(slot, {slot})
        candidates = [p for p in pool if p['player_id'] not in used_ids and p['position'] in eligible]
        if not candidates:
            continue
        best = max(candidates, key=lambda p: p['points'])
        used_ids.add(best['player_id'])
        total += best['points']

    return round(total, 2)


def _bench_points_by_roster(all_weekly_matchups, all_players, roster_positions, week):
    """{roster_id: {'actual', 'optimal', 'bench_points'}} for one week."""
    results = {}
    for team in (all_weekly_matchups.get(week) or []):
        roster_id = team.get('roster_id')
        if roster_id is None:
            continue
        optimal = _optimal_lineup_points(team, all_players, roster_positions)
        if optimal is None:
            continue
        actual = round(float(team.get('points') or 0.0), 2)
        results[roster_id] = {
            'actual': actual,
            'optimal': optimal,
            'bench_points': round(max(0.0, optimal - actual), 2),
        }
    return results


def _manager_name(roster_id, roster_to_manager, user_lookup):
    manager_id = roster_to_manager.get(roster_id)
    return (user_lookup or {}).get(manager_id, {}).get('display_name', 'Unknown')


def _winner_loser_names(matchup):
    winner_uid = matchup['winner_user_id']
    idx = 0 if matchup['user_ids'][0] == winner_uid else 1
    return matchup['manager_names'][idx], matchup['manager_names'][1 - idx]


def build_weekly_awards_for_week(matchups, bench_data, roster_to_manager, user_lookup,
                                  upsets_this_week, waiver_impacts_this_week, faab_events_this_week):
    """The award list for one already-played week. `bench_data` should already be restricted to
    rosters that actually played a real matchup this week (see build_weekly_awards_data)."""
    awards = []

    real_matchups = [m for m in (matchups or []) if len(m.get('scores', [])) == 2 and min(m['scores']) > 0]

    all_entries = [
        {'manager_name': name, 'score': score}
        for m in real_matchups
        for name, score in zip(m['manager_names'], m['scores'])
    ]
    if all_entries:
        top = max(all_entries, key=lambda e: e['score'])
        low = min(all_entries, key=lambda e: e['score'])
        awards.append({
            'id': 'top_score', 'emoji': '🏆', 'title': 'Top Score',
            'winner': top['manager_name'],
            'detail': f"Put up {top['score']:.1f} points this week - the highest in the league.",
        })
        awards.append({
            'id': 'low_score', 'emoji': '🥶', 'title': 'Ice Cold',
            'winner': low['manager_name'],
            'detail': f"Scored just {low['score']:.1f} points this week - the lowest in the league.",
        })

    if real_matchups:
        blowout = max(real_matchups, key=lambda m: m['margin'])
        b_winner, b_loser = _winner_loser_names(blowout)
        awards.append({
            'id': 'blowout', 'emoji': '💥', 'title': 'Biggest Blowout',
            'winner': b_winner,
            'detail': f"Beat {b_loser} by {blowout['margin']:.1f} points.",
        })

        nailbiter = min(real_matchups, key=lambda m: m['margin'])
        n_winner, n_loser = _winner_loser_names(nailbiter)
        awards.append({
            'id': 'nailbiter', 'emoji': '😬', 'title': 'Nail-Biter',
            'winner': n_winner,
            'detail': f"Squeaked past {n_loser} by just {nailbiter['margin']:.1f} points.",
        })

    if upsets_this_week:
        best_upset = max(upsets_this_week, key=lambda u: u['upset_score'])
        awards.append({
            'id': 'upset', 'emoji': '😱', 'title': 'Upset of the Week',
            'winner': best_upset['winner'],
            'detail': (
                f"Ranked #{best_upset['winner_rank_entering']} entering the week but beat "
                f"#{best_upset['loser_rank_entering']}-ranked {best_upset['loser']} by "
                f"{best_upset['margin']:.1f} points."
            ),
        })

    if waiver_impacts_this_week:
        best_pickup = max(waiver_impacts_this_week, key=lambda w: w['combined_impact'])
        if best_pickup['combined_impact'] > 0:
            players = ', '.join(best_pickup['players_added'])
            awards.append({
                'id': 'waiver_hero', 'emoji': '🎯', 'title': 'Waiver Wire Hero',
                'winner': best_pickup['manager_name'],
                'detail': (
                    f"Picked up {players}, who scored {best_pickup['combined_impact']:.1f} "
                    f"standard deviations above a typical rostered player at their position."
                ),
            })

    if bench_data:
        blunder_rid = max(bench_data, key=lambda rid: bench_data[rid]['bench_points'])
        if bench_data[blunder_rid]['bench_points'] >= MIN_NOTABLE_BENCH_POINTS:
            awards.append({
                'id': 'bench_blunder', 'emoji': '🪑', 'title': 'Bench Blunder',
                'winner': _manager_name(blunder_rid, roster_to_manager, user_lookup),
                'detail': (
                    f"Left {bench_data[blunder_rid]['bench_points']:.1f} points on the bench - "
                    f"their best possible lineup would have scored {bench_data[blunder_rid]['optimal']:.1f}."
                ),
            })

        ninja_rid = min(bench_data, key=lambda rid: bench_data[rid]['bench_points'])
        awards.append({
            'id': 'lineup_ninja', 'emoji': '✅', 'title': 'Lineup Ninja',
            'winner': _manager_name(ninja_rid, roster_to_manager, user_lookup),
            'detail': (
                f"Started their best possible lineup - only "
                f"{bench_data[ninja_rid]['bench_points']:.1f} points left on the bench."
            ),
        })

    if faab_events_this_week:
        biggest_spend = max(faab_events_this_week, key=lambda e: e['amount'])
        awards.append({
            'id': 'faab_splash', 'emoji': '💰', 'title': 'FAAB Splash',
            'winner': _manager_name(biggest_spend['roster_id'], roster_to_manager, user_lookup),
            'detail': (
                f"Spent ${biggest_spend['amount']:.0f} in FAAB - "
                f"{biggest_spend['commitment_ratio'] * 100:.0f}% of their remaining budget at the time."
            ),
        })

    return awards


def build_weekly_awards_data(rosters, all_players, all_weekly_matchups, matchup_results,
                              roster_positions, roster_to_manager, user_lookup,
                              power_rank_history, waiver_impacts, faab_ledger):
    """Everything the client-side Weekly Awards page needs, as one JSON-serializable dict - same
    embedded-JSON pattern as the trade analyzer/start-sit/AI Overview week-interactive sections,
    for the same reason: it has to work on the static Netlify build with no server to round-trip
    to. Also returned as plain data (not just HTML) so main.py can feed it into the Weekly
    Digest's Markdown export too, the same way start_sit_data already is.
    """
    manager_names = {uid: info.get('display_name', 'Unknown') for uid, info in (user_lookup or {}).items()}

    # No `limit` cap here (unlike the AI Overview's season-wide "biggest upsets" list) - every
    # week needs its own upset winner considered, not just the handful of biggest upsets overall.
    all_upsets = biggest_upsets(matchup_results, power_rank_history, manager_names, limit=len(matchup_results or {}) * 20 + 1)
    upsets_by_week = defaultdict(list)
    for u in all_upsets:
        upsets_by_week[u['week']].append(u)

    waivers_by_week = defaultdict(list)
    for w in (waiver_impacts or []):
        waivers_by_week[w['week']].append(w)

    faab_events_by_week = defaultdict(list)
    if faab_ledger and faab_ledger.get('enabled'):
        for event in faab_ledger.get('events', []):
            if event.get('direction') == 'spend':
                faab_events_by_week[event['week']].append(event)

    weeks_with_data = sorted(
        week for week, matchups in (matchup_results or {}).items()
        if any(len(m.get('scores', [])) == 2 and min(m['scores']) > 0 for m in (matchups or []))
    )

    weeks_out = {}
    for week in weeks_with_data:
        week_matchups = matchup_results.get(week, [])
        active_roster_ids = {
            rid
            for m in week_matchups
            if len(m.get('scores', [])) == 2 and min(m['scores']) > 0
            for rid in m['roster_ids']
        }
        bench_data = _bench_points_by_roster(all_weekly_matchups, all_players, roster_positions, week)
        bench_data = {rid: v for rid, v in bench_data.items() if rid in active_roster_ids}

        weeks_out[week] = build_weekly_awards_for_week(
            week_matchups, bench_data, roster_to_manager, user_lookup,
            upsets_by_week.get(week, []), waivers_by_week.get(week, []), faab_events_by_week.get(week, []),
        )

    return {
        'weeks': weeks_out,
        'available_weeks': weeks_with_data,
        'default_week': weeks_with_data[-1] if weeks_with_data else None,
    }


# ---- rendering ----

_WEEKLY_AWARDS_STYLE = """<style>
    .wa-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; margin-top: 16px; }
    .wa-card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 18px 16px; }
    .wa-emoji { font-size: 1.7rem; line-height: 1; }
    .wa-title { font-family: var(--font-display); font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ink-muted); margin: 10px 0 4px; }
    .wa-winner { font-size: 1.1rem; font-weight: 700; }
    .wa-detail { color: var(--ink-muted); font-size: 0.85rem; margin-top: 6px; line-height: 1.45; }
</style>"""

_WEEKLY_AWARDS_JS_TEMPLATE = r"""
const WA_DATA = __WEEKLY_AWARDS_DATA__;

function waEscapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
}

function waRenderWeek(week) {
    const container = document.getElementById('waGrid');
    const awards = WA_DATA.weeks[week] || [];
    if (!awards.length) {
        container.innerHTML = "<p class='empty'>No awards for this week yet.</p>";
        return;
    }
    container.innerHTML = awards.map(a => `
        <div class="wa-card">
            <div class="wa-emoji">${a.emoji}</div>
            <div class="wa-title">${waEscapeHtml(a.title)}</div>
            <div class="wa-winner">${waEscapeHtml(a.winner)}</div>
            <div class="wa-detail">${waEscapeHtml(a.detail)}</div>
        </div>
    `).join('');
}

document.addEventListener('DOMContentLoaded', function () {
    const select = document.getElementById('waWeekSelect');
    const weeks = (WA_DATA.available_weeks || []).slice().reverse();
    weeks.forEach(w => {
        const opt = document.createElement('option');
        opt.value = w;
        opt.textContent = 'Week ' + w;
        select.appendChild(opt);
    });
    select.addEventListener('change', () => waRenderWeek(select.value));
    if (WA_DATA.default_week != null) {
        select.value = WA_DATA.default_week;
        waRenderWeek(WA_DATA.default_week);
    }
});
"""


def render_weekly_awards_html(data, analysis_info):
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

    body = f"""
    {_WEEKLY_AWARDS_STYLE}
    <div class="section-card">
        <h2>Weekly Awards</h2>
        <p class="section-caption">
            A lighthearted recap of each week, not a season-long trend - who went off, who got
            shut down, the closest call, the biggest blowout, the best waiver pickup, and who
            left the most points on their bench by not starting their best possible lineup.
        </p>
        <div class="week-picker-row">
            <label for="waWeekSelect">Week:</label>
            <select id="waWeekSelect"></select>
        </div>
        <div id="waGrid" class="wa-grid"></div>
    </div>
    """

    js = _WEEKLY_AWARDS_JS_TEMPLATE.replace('__WEEKLY_AWARDS_DATA__', json.dumps(data))
    extra_script = f"<script>{js}</script>"

    return _page_shell(
        title=f"Weekly Awards - {league_name} ({season})",
        header_title=f"{league_name} &mdash; Weekly Awards",
        header_subtitle=f"Season {season} &middot; Generated {generated_at}",
        body_html=body,
        extra_script=extra_script,
    )


def build_weekly_awards_report(output_data, rosters, all_players, all_weekly_matchups,
                                matchup_results, roster_positions, roster_to_manager, user_lookup,
                                power_rank_history, waiver_impacts, faab_ledger):
    """Entry point mirroring build_trade_analyzer()/build_start_sit_report() - called from
    main.py. Returns (data, html_page) so the same precomputed award data can also feed the
    Weekly Digest export without recomputing it a second time (mirrors start_sit_data)."""
    data = build_weekly_awards_data(
        rosters, all_players, all_weekly_matchups, matchup_results, roster_positions,
        roster_to_manager, user_lookup, power_rank_history, waiver_impacts, faab_ledger,
    )
    analysis_info = output_data.get('analysis_info') or {}
    return data, render_weekly_awards_html(data, analysis_info)
