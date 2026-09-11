#!/usr/bin/env python3
"""
Start/Sit Analyzer: weekly lineup advice for every rostered player, for the next real week on
the schedule - not a full lineup optimizer, a per-player Start/Consider/Sit verdict with the
reasoning shown alongside it, since a bare score without an explanation was explicitly what the
user didn't want (CLAUDE.md section 13 has the full writeup and the research behind it).

Three signals combine into one score, each also surfaced in the reasoning text so nothing is a
black box:

1. Baseline quality/form - reuses src/trade_value.py's calculate_player_trade_values() output
   directly (its 0-10 blend of recent-weeks position-adjusted performance and season-long
   ESPN-tier grade) rather than re-deriving a second, slightly-different projection formula.
   The *pre-injury* value is used here deliberately - see the injury section below.
2. Matchup - this week's opponent's Defense-vs-Position: how many fantasy points that defense
   has allowed to this position all season, expressed as a z-score against the league-wide
   average (the same z-score-against-a-baseline language already used everywhere else in this
   app - waiver scoring, draft value, trade value). Computed from this league's own real weekly
   scoring cross-referenced with the real NFL schedule (see build_defense_vs_position()) rather
   than a third-party "DvP" number, since established tools (FantasyPros, Establish The Run,
   RotoWire - see CLAUDE.md) all compute this the same way: fantasy points allowed to a
   position, not yards or some other proxy stat.
3. Injury/opportunity - a player's own injury status pulls their score down (down to an
   effective floor that always reads as "Sit" for a confirmed Out); a *teammate* ahead of them
   on their real NFL team's depth chart being hurt pushes their score up, since Sleeper's own
   depth_chart_order field says who is next in line for the snaps/touches.
"""

import json
import statistics
from collections import defaultdict
from datetime import datetime

from src.trade_value import TRADABLE_POSITIONS, calculate_player_trade_values
from src.injury_severity import injury_severity_tier, start_sit_penalty
from src.ai_overview import _page_shell
from src.utils import week_has_been_played

MATCHUP_WEIGHT = 1.0  # matchup z-score contributes point-for-point alongside the 0-10 quality scale
START_THRESHOLD = 1.5
SIT_THRESHOLD = -1.5
# Added to a player's score when a teammate immediately ahead of them on the NFL depth chart is
# hurt - calibrated so a good matchup can turn this into a real Start recommendation for a
# backup, matching the explicit request ("if a starting RB is hurt, start their replacement").
OPPORTUNITY_BOOST = {'out': 2.5, 'doubtful': 1.5}


def build_defense_vs_position(all_weekly_matchups, all_players, schedule_by_week):
    """Fantasy points allowed by every NFL team, by position, from this league's own real
    weekly scoring - every rostered player's points that week are attributed to whichever team
    they played *against* that week (via the real schedule), then averaged per (team,
    position) and z-scored against the league-wide distribution of those averages.

    This only sees players who were rostered somewhere in this fantasy league, not every NFL
    player - a deliberate, documented simplification (CLAUDE.md section 13) rather than a
    reason to pull in a whole separate box-score data source: a 10-12 team league already
    rosters most of the fantasy-relevant players at each position, and this reuses data already
    flowing through the pipeline instead of adding a new one.

    Returns {team: {position: {'avg_allowed': float, 'z_score': float, 'games': int}}}.
    """
    points_allowed = defaultdict(lambda: defaultdict(list))

    for week, matchups in (all_weekly_matchups or {}).items():
        # A future week's real NFL opponent is already known (ESPN publishes the schedule months
        # ahead), but the *points* Sleeper reports for it are a 0.0 placeholder for every
        # rostered player until the games are actually played - not missing, not None (confirmed
        # against live data). Without this guard, every unplayed week would attribute a wave of
        # fake "0 points against this future opponent" games to whoever's on the schedule that
        # week, diluting every team's real points-allowed average toward zero for the rest of
        # the season. See week_has_been_played()'s docstring.
        if not week_has_been_played(matchups):
            continue
        week_schedule = schedule_by_week.get(week) or {}
        if not week_schedule:
            continue
        for team_entry in matchups or []:
            for player_id, points in (team_entry.get('players_points') or {}).items():
                if points is None:
                    continue
                info = (all_players or {}).get(player_id) or {}
                position = info.get('position')
                player_team = info.get('team')
                if position not in TRADABLE_POSITIONS or not player_team:
                    continue
                opponent = week_schedule.get(player_team)
                if not opponent:
                    continue
                points_allowed[opponent][position].append(float(points))

    # League-wide baseline: the distribution of every team's own (team, position) average.
    team_position_avgs = defaultdict(list)
    dvp = {}
    for team, positions in points_allowed.items():
        dvp[team] = {}
        for position, values in positions.items():
            if not values:
                continue
            avg = statistics.mean(values)
            dvp[team][position] = {'avg_allowed': round(avg, 1), 'games': len(values)}
            team_position_avgs[position].append(avg)

    position_baseline = {
        position: {
            'mean': statistics.mean(avgs),
            'stdev': statistics.pstdev(avgs) if len(avgs) > 1 else 0.0,
        }
        for position, avgs in team_position_avgs.items()
    }

    for team, positions in dvp.items():
        for position, data in positions.items():
            baseline = position_baseline.get(position)
            if baseline and baseline['stdev'] > 0:
                data['z_score'] = round((data['avg_allowed'] - baseline['mean']) / baseline['stdev'], 2)
            else:
                data['z_score'] = 0.0

    return dvp


def _build_depth_charts(all_players, rostered_player_ids):
    """(nfl_team, position) -> [(depth_chart_order, player_id), ...] sorted, restricted to
    players actually rostered somewhere in this fantasy league - a depth-chart-ranked player
    nobody in this league owns isn't a useful "your likely replacement" callout."""
    charts = defaultdict(list)
    for player_id in rostered_player_ids:
        info = all_players.get(player_id) or {}
        team, position, order = info.get('team'), info.get('position'), info.get('depth_chart_order')
        if team and position and order:
            charts[(team, position)].append((order, player_id))
    for key in charts:
        charts[key].sort()
    return charts


def _opportunity_boost(player_id, all_players, depth_charts):
    """If a teammate ranked immediately ahead of this player on the real NFL depth chart is
    hurt, return (boost_points, that_teammate's_name, their_injury_status) - else (0, None, None).
    Only looks at the *next* player up the chart, not everyone above them, since a boost from a
    team's 4th-string player being hurt while the 2nd-stringer is healthy tells you nothing
    about the 3rd-stringer's opportunity.

    No boost at all if this player is themselves out/doubtful - "your teammate being hurt means
    more opportunity for you" is meaningless if you're equally unavailable (confirmed a real
    case of this: a WR on IR was showing a boost from a teammate also on IR ahead of him).
    """
    info = all_players.get(player_id) or {}
    team, position, my_order = info.get('team'), info.get('position'), info.get('depth_chart_order')
    if not (team and position and my_order):
        return 0.0, None, None
    if injury_severity_tier(info.get('injury_status')) in ('out', 'doubtful'):
        return 0.0, None, None

    chart = depth_charts.get((team, position), [])
    ahead = [pid for order, pid in chart if order < my_order and pid != player_id]
    if not ahead:
        return 0.0, None, None

    # Closest-ranked player immediately above them.
    closest_id = max(ahead, key=lambda pid: next(o for o, p in chart if p == pid))
    closest_info = all_players.get(closest_id) or {}
    tier = injury_severity_tier(closest_info.get('injury_status'))
    if tier in OPPORTUNITY_BOOST:
        return OPPORTUNITY_BOOST[tier], closest_info.get('full_name', 'Their teammate'), closest_info.get('injury_status')
    return 0.0, None, None


def _matchup_reasoning(position, opponent, matchup_z):
    if matchup_z >= 0.75:
        return f"Favorable matchup: {opponent} has allowed well above the league average in fantasy points to {position}s this season."
    if matchup_z <= -0.75:
        return f"Tough matchup: {opponent} has been one of the stingier defenses against {position}s this season."
    return f"Middle-of-the-road matchup against {opponent} - not a reason to start or sit them on its own."


def calculate_start_sit_recommendations(player_values, all_players, schedule_this_week, dvp):
    """The main scoring pass. `player_values` is calculate_player_trade_values()'s output -
    reused directly rather than re-projecting from scratch. Returns
    {player_id: {..., score, verdict, reasoning: [str, ...]}}.
    """
    rostered_ids = set(player_values.keys())
    depth_charts = _build_depth_charts(all_players, rostered_ids)

    recommendations = {}
    for player_id, pv in player_values.items():
        position = pv['position']
        team = pv['team']
        opponent = schedule_this_week.get(team)

        reasoning = []
        matchup_z = 0.0
        if opponent:
            opp_dvp = dvp.get(opponent, {}).get(position)
            if opp_dvp:
                matchup_z = opp_dvp['z_score']
                reasoning.append(_matchup_reasoning(position, opponent, matchup_z))
        else:
            reasoning.append("Bye week - not on the schedule this week.")

        injury_status = pv.get('injury_status')
        penalty = start_sit_penalty(injury_status)
        if injury_status:
            reasoning.append(
                f"{pv['name']} is listed as {injury_status}, which adds real risk to this "
                f"week's workload or availability."
            )

        boost, teammate_name, teammate_status = _opportunity_boost(player_id, all_players, depth_charts)
        if boost:
            reasoning.append(
                f"{teammate_name} ({teammate_status}) is ahead of {pv['name']} on the depth "
                f"chart and banged up, which should mean expanded opportunity this week."
            )

        # trade_value_pre_injury (not trade_value) - this module applies its own,
        # start/sit-calibrated injury adjustment below instead of double-counting
        # trade_value.py's separate multiplicative discount.
        baseline = pv['trade_value_pre_injury'] - 5.0
        score = round(baseline + MATCHUP_WEIGHT * matchup_z - penalty + boost, 2)

        # A confirmed Out (or bye week) is a hard override, not just a heavy penalty - an
        # elite player with an exceptional matchup could otherwise still clear the Start
        # threshold on points alone, which would be actively wrong advice for someone who is
        # not going to play at all (confirmed this could happen with an extreme-matchup test
        # case before adding this override).
        if opponent is None or injury_severity_tier(injury_status) == 'out':
            verdict = 'Sit'
        elif score >= START_THRESHOLD:
            verdict = 'Start'
        elif score <= SIT_THRESHOLD:
            verdict = 'Sit'
        else:
            verdict = 'Consider'

        recommendations[player_id] = {
            **pv,
            'opponent': opponent,
            'matchup_z': matchup_z,
            'score': score,
            'verdict': verdict,
            'reasoning': reasoning,
        }

    return recommendations


def build_start_sit_data(rosters, all_players, all_weekly_matchups, analyzer, roster_to_manager,
                          user_lookup, schedule_by_week, this_week):
    """Everything the client-side start/sit page needs, as one JSON-serializable dict - same
    embedded-JSON, client-side-rendered pattern as the trade analyzer and the AI Overview's
    week-interactive sections (CLAUDE.md sections 5 and 12), for the same reason: it has to
    work on the static Netlify build with no server to round-trip to.
    """
    player_values = calculate_player_trade_values(
        rosters, all_players, all_weekly_matchups, analyzer, roster_to_manager, user_lookup
    )
    dvp = build_defense_vs_position(all_weekly_matchups, all_players, schedule_by_week)
    schedule_this_week = schedule_by_week.get(this_week, {})
    recommendations = calculate_start_sit_recommendations(player_values, all_players, schedule_this_week, dvp)

    teams = {}
    for roster in rosters or []:
        roster_id = roster.get('roster_id')
        manager_id = roster_to_manager.get(roster_id)
        manager_name = (user_lookup or {}).get(manager_id, {}).get('display_name', 'Unknown')
        player_ids = [pid for pid in (roster.get('players') or []) if pid in recommendations]
        teams[roster_id] = {'manager_name': manager_name, 'player_ids': player_ids}

    return {
        'players': recommendations,
        'teams': teams,
        'week': this_week,
    }


# ---- rendering ----

_START_SIT_STYLE = """<style>
    .ss-toolbar { margin-bottom: 16px; }
    .ss-team-select {
        width: 100%; padding: 12px 14px; border-radius: 12px; border: 1px solid var(--line);
        background: var(--void); color: var(--ink); font-family: var(--font-sans); font-size: 0.95rem;
    }
    .ss-position-group { margin-top: 18px; }
    .ss-position-title { font-family: var(--font-display); font-weight: 600; color: var(--ink-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }
    .ss-card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; margin-bottom: 10px; }
    .ss-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .ss-name { font-weight: 700; font-size: 1rem; }
    .ss-meta { color: var(--ink-muted); font-size: 0.8rem; margin-top: 2px; }
    .ss-badge { font-family: var(--font-display); font-weight: 600; font-size: 0.8rem; padding: 5px 14px; border-radius: 980px; white-space: nowrap; }
    .ss-badge-start { background: rgba(52, 211, 153, 0.16); color: var(--good); }
    .ss-badge-consider { background: rgba(255, 106, 43, 0.16); color: var(--accent); }
    .ss-badge-sit { background: rgba(248, 113, 113, 0.16); color: var(--bad); }
    .ss-reasoning { margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--line); }
    .ss-reasoning p { color: var(--ink-muted); font-size: 0.85rem; line-height: 1.5; margin: 4px 0; }
    @media (max-width: 640px) {
        .ss-name { font-size: 0.95rem; }
        .ss-badge { font-size: 0.75rem; padding: 4px 10px; }
    }
</style>"""

_START_SIT_JS_TEMPLATE = r"""
const SS_DATA = __START_SIT_DATA__;
const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE'];

function ssEscapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s == null ? '' : String(s);
    return div.innerHTML;
}

function ssBadgeClass(verdict) {
    if (verdict === 'Start') return 'ss-badge-start';
    if (verdict === 'Sit') return 'ss-badge-sit';
    return 'ss-badge-consider';
}

function ssPlayerCard(p) {
    const oppText = p.opponent ? ('vs ' + ssEscapeHtml(p.opponent)) : 'Bye week';
    const reasoning = (p.reasoning || []).map(r => `<p>${ssEscapeHtml(r)}</p>`).join('');
    return `
        <div class="ss-card">
            <div class="ss-card-head">
                <div>
                    <div class="ss-name">${ssEscapeHtml(p.name)}</div>
                    <div class="ss-meta">${p.position} - ${ssEscapeHtml(p.team)} - ${oppText}</div>
                </div>
                <span class="ss-badge ${ssBadgeClass(p.verdict)}">${p.verdict}</span>
            </div>
            <div class="ss-reasoning">${reasoning}</div>
        </div>
    `;
}

function ssRenderTeam(rosterId) {
    const container = document.getElementById('ssPlayers');
    if (rosterId === '' || rosterId == null) { container.innerHTML = ''; return; }
    const team = SS_DATA.teams[rosterId];
    const byPosition = {};
    team.player_ids.forEach(pid => {
        const p = SS_DATA.players[pid];
        if (!byPosition[p.position]) byPosition[p.position] = [];
        byPosition[p.position].push(p);
    });
    Object.values(byPosition).forEach(list => list.sort((a, b) => b.score - a.score));

    let html = '';
    POSITION_ORDER.forEach(pos => {
        if (!byPosition[pos]) return;
        html += `<div class="ss-position-group"><div class="ss-position-title">${pos}</div>`;
        html += byPosition[pos].map(ssPlayerCard).join('');
        html += `</div>`;
    });
    container.innerHTML = html || "<p class='empty'>No tradable-position players rostered.</p>";
}

document.addEventListener('DOMContentLoaded', function () {
    const select = document.getElementById('ssTeamSelect');
    Object.keys(SS_DATA.teams).forEach(rosterId => {
        const opt = document.createElement('option');
        opt.value = rosterId;
        opt.textContent = SS_DATA.teams[rosterId].manager_name;
        select.appendChild(opt);
    });
    select.addEventListener('change', () => ssRenderTeam(select.value));
    if (select.options.length > 1) {
        select.selectedIndex = 1;
        ssRenderTeam(select.value);
    }
});
"""


def render_start_sit_html(data, analysis_info):
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

    body = f"""
    {_START_SIT_STYLE}
    <div class="section-card">
        <h2>Start/Sit Analyzer - Week {data['week']}</h2>
        <p class="section-caption">
            Every rostered QB/RB/WR/TE, ranked by a blend of season-long quality, recent form,
            this week's matchup (how many fantasy points their opponent has allowed to that
            position all season), and injury/opportunity - including a boost for a backup
            whose teammate ahead of them on the depth chart is banged up. This is advice, not
            an autopilot - always weigh your own roster needs and bye weeks too.
        </p>
        <div class="ss-toolbar">
            <select id="ssTeamSelect" class="ss-team-select">
                <option value="">Select a team...</option>
            </select>
        </div>
        <div id="ssPlayers"></div>
    </div>
    """

    js = _START_SIT_JS_TEMPLATE.replace('__START_SIT_DATA__', json.dumps(data))
    extra_script = f"<script>{js}</script>"

    return _page_shell(
        title=f"Start/Sit - {league_name} ({season})",
        header_title=f"{league_name} &mdash; Start/Sit Analyzer",
        header_subtitle=f"Season {season} &middot; Generated {generated_at}",
        body_html=body,
        extra_script=extra_script,
    )


def build_start_sit_report(output_data, rosters, all_players, all_weekly_matchups, analyzer,
                            roster_to_manager, user_lookup, schedule_by_week, this_week):
    """Entry point mirroring build_trade_analyzer()/build_draft_info() - called from main.py."""
    data = build_start_sit_data(
        rosters, all_players, all_weekly_matchups, analyzer, roster_to_manager, user_lookup,
        schedule_by_week, this_week,
    )
    analysis_info = output_data.get('analysis_info') or {}
    return render_start_sit_html(data, analysis_info)
