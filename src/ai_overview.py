#!/usr/bin/env python3
"""
AI Overview - fully deterministic, no LLM call (see CLAUDE.md sections 1 and 5 for why).

The old version imported `openai`, read OPENAI_API_KEY, and then a hardcoded line always called
a mock generator instead of ever actually calling OpenAI. This module replaces that entirely:
every section below is computed from real per-week data that main.py now persists (previously
fetched from Sleeper and discarded before it reached a JSON file).

Sections: top performers (head-to-head matchup winners, any week), biggest upsets, power ranking
movers (last week vs this week), matchups to watch, a projected playoff bracket (any week),
median standings, and top waiver pickups.

Top Performers and the playoff bracket/standings are week-interactive: rather than round-trip to
the server for every week change, every week's matchup data is embedded as JSON in the page and
a small vanilla-JS layer re-renders those two sections client-side when the week picker changes.
This keeps the page a single static HTML file (same as every other report) while still being
interactive.
"""

import json
from datetime import datetime


def biggest_upsets(matchup_results, power_rank_history, manager_names, limit=5):
    """Wins by the team that entered the week ranked worse in power rating than their
    opponent, weighted by how big the rank gap and the margin of victory were."""
    upsets = []
    weeks = sorted(int(w) for w in matchup_results.keys())

    for week in weeks:
        prior_ranks = power_rank_history.get(week - 1, power_rank_history.get(str(week - 1)))
        if not prior_ranks:
            continue
        rank_by_user = {r['user_id']: r['rank'] for r in prior_ranks}

        for m in matchup_results.get(week, []) or []:
            user_ids = m.get('user_ids', [None, None])
            winner_uid = m.get('winner_user_id')
            if winner_uid is None or len(user_ids) != 2:
                continue

            # A 0-point score is a team that never set a lineup that week (already eliminated,
            # on a bye between playoff rounds, etc.) - a real Sleeper result seen in testing,
            # but not a real "upset": the margin is only huge because one side forfeited, not
            # because the underdog outplayed anyone.
            scores = m.get('scores', [0, 0])
            if len(scores) != 2 or min(scores) <= 0:
                continue

            u1, u2 = user_ids
            loser_uid = u2 if winner_uid == u1 else u1
            if winner_uid not in rank_by_user or loser_uid not in rank_by_user:
                continue

            winner_rank = rank_by_user[winner_uid]
            loser_rank = rank_by_user[loser_uid]
            if winner_rank <= loser_rank:
                continue  # the favorite (or an even matchup) won - not an upset

            rank_gap = winner_rank - loser_rank
            upset_score = round(rank_gap + (m.get('margin', 0) / 10.0), 1)

            upsets.append({
                'week': week,
                'winner': manager_names.get(winner_uid, 'Unknown'),
                'loser': manager_names.get(loser_uid, 'Unknown'),
                'winner_rank_entering': winner_rank,
                'loser_rank_entering': loser_rank,
                'margin': m.get('margin', 0),
                'upset_score': upset_score,
            })

    upsets.sort(key=lambda u: u['upset_score'], reverse=True)
    return upsets[:limit]


def power_rank_movers(power_rank_history, manager_names, limit=None):
    """Rank delta from the previous week to the most recent week - the 'last week vs this
    week' power ranking comparison. The per-week series already existed in
    power_rankings.py/fantasy_analysis.json; this is the first time it's diffed week-over-week."""
    weeks = sorted(int(w) for w in power_rank_history.keys()) if power_rank_history else []
    if len(weeks) < 2:
        return {'this_week': weeks[-1] if weeks else None, 'last_week': None, 'movers': []}

    this_week, last_week = weeks[-1], weeks[-2]
    this_ranks = {r['user_id']: r for r in power_rank_history[this_week]}
    last_ranks = {r['user_id']: r for r in power_rank_history[last_week]}

    movers = []
    for user_id, this_r in this_ranks.items():
        last_r = last_ranks.get(user_id)
        if not last_r:
            continue
        movers.append({
            'user_id': user_id,
            'manager_name': manager_names.get(user_id, 'Unknown'),
            'last_week_rank': last_r['rank'],
            'this_week_rank': this_r['rank'],
            'delta': last_r['rank'] - this_r['rank'],  # positive = moved up in the rankings
            'rating': this_r['rating'],
        })

    movers.sort(key=lambda m: abs(m['delta']), reverse=True)
    if limit:
        movers = movers[:limit]

    return {'this_week': this_week, 'last_week': last_week, 'movers': movers}


def standings_from_rosters(rosters, roster_to_manager, manager_names):
    """Real *current* standings (wins, then points-for as tiebreak) from Sleeper's own roster
    settings - used only for 'Matchups to Watch' (which is inherently about the upcoming week,
    not a historical one). Top Performers and the playoff bracket use the week-interactive
    client-side standings reconstruction instead (see MATCHUP_DATA in the rendered page)."""
    standings = []
    for roster in rosters:
        settings = roster.get('settings') or {}
        wins = settings.get('wins', 0)
        losses = settings.get('losses', 0)
        ties = settings.get('ties', 0)
        points_for = settings.get('fpts', 0) + settings.get('fpts_decimal', 0) / 100.0
        user_id = roster_to_manager.get(roster.get('roster_id'))

        standings.append({
            'user_id': user_id,
            'roster_id': roster.get('roster_id'),
            'manager_name': manager_names.get(user_id, 'Unknown'),
            'wins': wins, 'losses': losses, 'ties': ties,
            'points_for': round(points_for, 1),
        })

    standings.sort(key=lambda t: (t['wins'], t['points_for']), reverse=True)
    for i, team in enumerate(standings):
        team['rank'] = i + 1

    return standings


def matchups_to_watch(next_week_matchups, standings, playoff_teams_count, limit=3):
    """Upcoming pairings scored by standings stakes - both teams in a playoff spot, a team on
    the bubble, or a close-in-the-standings head-to-head."""
    if not next_week_matchups:
        return []

    playoff_teams_count = playoff_teams_count or 6
    rank_by_user = {t['user_id']: t for t in standings}

    scored = []
    for m in next_week_matchups:
        user_ids = m.get('user_ids', [None, None])
        if len(user_ids) != 2:
            continue
        t1, t2 = rank_by_user.get(user_ids[0]), rank_by_user.get(user_ids[1])
        if not t1 or not t2:
            continue

        stakes = 0
        notes = []
        if t1['rank'] <= playoff_teams_count and t2['rank'] <= playoff_teams_count:
            stakes += 3
            notes.append("Both teams currently hold a playoff spot")
        if abs(t1['rank'] - playoff_teams_count) <= 1 or abs(t2['rank'] - playoff_teams_count) <= 1:
            stakes += 2
            notes.append("Involves a team on the playoff bubble")
        if abs(t1['rank'] - t2['rank']) <= 1:
            stakes += 1
            notes.append("Closely-ranked head-to-head")

        scored.append({
            'manager_names': [t1['manager_name'], t2['manager_name']],
            'ranks': [t1['rank'], t2['rank']],
            'records': [f"{t1['wins']}-{t1['losses']}", f"{t2['wins']}-{t2['losses']}"],
            'stakes_score': stakes,
            'notes': notes or ["Standard matchup"],
        })

    scored.sort(key=lambda m: m['stakes_score'], reverse=True)
    return scored[:limit]


def median_standings_table(median_standings):
    """'If a median-scoring rule had been in place all season' standings.

    Each week, every team still plays its real head-to-head matchup, but the top half of
    scorers league-wide also get a bonus win against "the median" and the bottom half get a
    bonus loss, regardless of who they actually played. Beating both your opponent and the
    median in the same week goes 2-0; being the 2nd-highest score in a week against the
    highest-scoring team goes 1-1 (loses the head-to-head, still beats the median). The
    underlying per-week math lives in median_record_calculator.py - this just presents the
    manager-level season totals it already computes as a comparable secondary standings.
    """
    rows = []
    for uid, data in (median_standings or {}).items():
        regular = data.get('regular_record') or {}
        median = data.get('median_record') or {}
        combined = data.get('combined_record') or {}
        combined_games = combined.get('wins', 0) + combined.get('losses', 0)
        combined_pct = (combined.get('wins', 0) / combined_games) if combined_games else 0.0

        rows.append({
            'name': data.get('name', 'Unknown'),
            'regular_wins': regular.get('wins', 0),
            'regular_losses': regular.get('losses', 0),
            'regular_ties': regular.get('ties', 0),
            'median_wins': median.get('wins', 0),
            'median_losses': median.get('losses', 0),
            'combined_wins': combined.get('wins', 0),
            'combined_losses': combined.get('losses', 0),
            'combined_pct': combined_pct,
        })

    rows.sort(key=lambda r: r['combined_pct'], reverse=True)
    for i, row in enumerate(rows):
        row['rank'] = i + 1

    return rows


def top_waiver_pickups(waiver_impacts, faab_enabled, limit=5):
    """Season-best and this-week-best waiver/free-agent pickups, from the de-duplicated
    (one entry per transaction, not per added player) waiver analysis."""
    if not waiver_impacts:
        return {'season': [], 'this_week': [], 'this_week_num': None, 'faab_enabled': faab_enabled}

    season_top = sorted(waiver_impacts, key=lambda w: w['combined_impact'], reverse=True)[:limit]
    this_week_num = max(w['week'] for w in waiver_impacts)
    this_week_top = sorted(
        [w for w in waiver_impacts if w['week'] == this_week_num],
        key=lambda w: w['combined_impact'], reverse=True
    )[:limit]

    return {
        'season': season_top, 'this_week': this_week_top,
        'this_week_num': this_week_num, 'faab_enabled': faab_enabled,
    }


def _most_recent_completed_week(matchup_results):
    completed = [
        int(week) for week, matchups in matchup_results.items()
        if any((m['scores'][0] or 0) + (m['scores'][1] or 0) > 0 for m in matchups)
    ]
    return max(completed) if completed else None


def _next_scheduled_week(matchup_results, after_week):
    if after_week is None:
        return None
    candidate = matchup_results.get(after_week + 1, matchup_results.get(str(after_week + 1)))
    return candidate or None


def build_ai_overview(output_data, detailed_data, roster_data, league_settings, faab_ledger=None):
    """Compute every section and render them as one HTML page."""
    manager_names = {
        uid: data.get('manager_name', 'Unknown')
        for uid, data in (output_data.get('power_ratings') or {}).items()
    }
    power_rank_history = output_data.get('power_rank_history') or {}
    power_rank_history = {int(k): v for k, v in power_rank_history.items()}

    matchup_results = detailed_data.get('matchup_results') or {}
    matchup_results = {int(k): v for k, v in matchup_results.items()}

    rosters = roster_data.get('rosters') or []
    roster_to_manager = {
        r.get('roster_id'): r.get('owner_id')
        for r in rosters if r.get('roster_id') is not None
    }

    analysis_info = output_data.get('analysis_info') or {}
    playoff_teams_count = analysis_info.get('playoff_teams') or league_settings.get('playoff_teams') or 6
    faab_enabled = analysis_info.get('faab_enabled', False)

    current_week = _most_recent_completed_week(matchup_results)
    next_week_matchups = _next_scheduled_week(matchup_results, current_week)

    # Only used for "Matchups to Watch" (inherently about the real upcoming week - see the
    # docstring on standings_from_rosters for why this doesn't feed the week-picker sections).
    real_standings = standings_from_rosters(rosters, roster_to_manager, manager_names)

    sections = {
        'upsets': biggest_upsets(matchup_results, power_rank_history, manager_names),
        'power_movers': power_rank_movers(power_rank_history, manager_names),
        'matchups_to_watch': matchups_to_watch(next_week_matchups, real_standings, playoff_teams_count),
        'median_standings': median_standings_table(output_data.get('median_standings') or {}),
        'waiver_pickups': top_waiver_pickups(
            (output_data.get('trade_analysis') or {}).get('waiver_impacts') or [], faab_enabled
        ),
    }

    weeks_available = sorted(matchup_results.keys())

    return render_ai_overview_html(
        analysis_info, sections, faab_ledger, roster_to_manager, manager_names,
        matchup_results=matchup_results, weeks_available=weeks_available,
        current_week=current_week, playoff_teams_count=playoff_teams_count,
    )


# ---- rendering (server-rendered sections) ----

def _card(title, body_html, extra_attrs=""):
    return f"""
    <div class="section-card" {extra_attrs}>
        <h2>{title}</h2>
        {body_html}
    </div>
    """


def _render_upsets(upsets):
    if not upsets:
        return "<p class='empty'>No upsets detected yet (need at least two completed weeks).</p>"
    items = "".join(
        f"""<li>
            <strong>Week {u['week']}:</strong> {u['winner']} (ranked #{u['winner_rank_entering']})
            upset {u['loser']} (ranked #{u['loser_rank_entering']}) by {u['margin']:.1f} points
            <span class="badge">upset score {u['upset_score']}</span>
        </li>"""
        for u in upsets
    )
    return f"<ul class='upset-list'>{items}</ul>"


def _render_power_movers(section):
    if not section['movers']:
        return "<p class='empty'>Need at least two weeks of data to compare power rankings.</p>"
    rows = "".join(
        f"""<tr>
            <td>{m['manager_name']}</td>
            <td class="num">#{m['last_week_rank']}</td>
            <td class="num">#{m['this_week_rank']}</td>
            <td class="num {'positive' if m['delta'] > 0 else 'negative' if m['delta'] < 0 else ''}">
                {'+' if m['delta'] > 0 else ''}{m['delta']}
            </td>
        </tr>"""
        for m in section['movers']
    )
    return f"""
    <p class="section-caption">Week {section['last_week']} to Week {section['this_week']}</p>
    <div class="table-scroll"><table>
        <tr><th>Manager</th><th>Last Week</th><th>This Week</th><th>Change</th></tr>
        {rows}
    </table></div>
    """


def _render_matchups_to_watch(matchups):
    if not matchups:
        return "<p class='empty'>No upcoming schedule data available yet.</p>"
    items = "".join(
        f"""<li>
            <strong>{m['manager_names'][0]} (#{m['ranks'][0]}, {m['records'][0]})</strong> vs
            <strong>{m['manager_names'][1]} (#{m['ranks'][1]}, {m['records'][1]})</strong>
            <div class="notes">{' | '.join(m['notes'])}</div>
        </li>"""
        for m in matchups
    )
    return f"<ul class='matchup-list'>{items}</ul>"


def _render_median_standings(rows):
    if not rows:
        return "<p class='empty'>No median standings available yet.</p>"

    table_rows = "".join(
        f"""<tr>
            <td>#{r['rank']}</td>
            <td>{r['name']}</td>
            <td class="num">{r['regular_wins']}-{r['regular_losses']}{'-' + str(r['regular_ties']) if r['regular_ties'] else ''}</td>
            <td class="num">{r['median_wins']}-{r['median_losses']}</td>
            <td class="num">{r['combined_wins']}-{r['combined_losses']}</td>
            <td class="num">{r['combined_pct'] * 100:.1f}%</td>
        </tr>"""
        for r in rows
    )

    return f"""
    <p class="section-caption">If every week also counted as a win/loss against the league median score</p>
    <div class="table-scroll"><table>
        <tr>
            <th>Rank</th><th>Manager</th><th>Real Record</th><th>vs. Median</th>
            <th>Combined</th><th>Combined %</th>
        </tr>
        {table_rows}
    </table></div>
    <p class="notes" style="margin-top: 10px;">
        Each week, the top half of scorers league-wide also get a bonus win against "the median" and the
        bottom half get a bonus loss - regardless of who they actually played. Beat both your real
        opponent and the median in the same week and you go 2-0; be the 2nd-highest score in a week the
        top scorer also plays in and you go 1-1 (lose the head-to-head, still beat the median).
    </p>
    """


def _render_waiver_pickups(section):
    if not section['season']:
        return "<p class='empty'>No waiver/free-agent activity analyzed yet.</p>"

    def pickup_row(w):
        faab = f"${w['faab_spent']:.0f}" if section['faab_enabled'] and w.get('faab_spent') else "-"
        return f"""<tr>
            <td>Week {w['week']}</td><td>{w['manager_name']}</td>
            <td>{w.get('player_added', 'Unknown')}</td>
            <td class="num">{w['combined_impact']:+.1f}</td>
            <td class="num">{faab}</td>
        </tr>"""

    season_rows = "".join(pickup_row(w) for w in section['season'])
    header = "<tr><th>Week</th><th>Manager</th><th>Player Added</th><th>Impact</th><th>FAAB</th></tr>"

    this_week_html = ""
    if section['this_week']:
        this_week_rows = "".join(pickup_row(w) for w in section['this_week'])
        this_week_html = f"""
        <p class="section-caption">This week's best pickups (Week {section['this_week_num']})</p>
        <div class="table-scroll"><table>{header}{this_week_rows}</table></div>
        """

    return f"""
    {this_week_html}
    <p class="section-caption">Season-best pickups</p>
    <div class="table-scroll"><table>{header}{season_rows}</table></div>
    """


def _render_faab_tracker(faab_ledger, roster_to_manager, manager_names):
    if not faab_ledger or not faab_ledger.get('enabled'):
        return ""

    # roster_to_manager's keys come straight from an in-memory rosters list (always int); a
    # faab_ledger reloaded from JSON (rather than passed straight from the same analysis run)
    # comes back with string dict keys, since JSON object keys are always strings - normalize
    # so a lookup miss doesn't silently fall back to "Roster {id}" instead of the real name.
    lookup_by_str = {str(k): v for k, v in roster_to_manager.items()}

    rows = []
    for roster_id, balance in sorted(faab_ledger['balances'].items(), key=lambda kv: kv[1], reverse=True):
        user_id = roster_to_manager.get(roster_id, lookup_by_str.get(str(roster_id)))
        name = manager_names.get(user_id, f'Roster {roster_id}')
        total = faab_ledger['total_budget']
        pct = (balance / total * 100) if total else 0
        rows.append(f"""<tr>
            <td>{name}</td>
            <td class="num">${balance:.0f} / ${total:.0f}</td>
            <td><div class="faab-bar"><div class="faab-bar-fill" style="width:{max(0, min(100, pct)):.0f}%"></div></div></td>
        </tr>""")

    return _card("FAAB Tracker", f"""
    <p class="section-caption">Remaining budget by manager</p>
    <div class="table-scroll"><table><tr><th>Manager</th><th>Remaining</th><th></th></tr>{''.join(rows)}</table></div>
    """)


# ---- client-side week-interactive sections (Top Performers + Playoff Bracket/Standings) ----
# See the big <script> block below - BRACKET_TEMPLATES describes the seeded matchup tree for
# Sleeper's three supported playoff field sizes (4/6/8 teams, per their own API docs); anything
# else falls back to a flat seed list with no bracket tree.

_WEEK_INTERACTIVE_JS = r"""
const MATCHUP_DATA = __MATCHUP_DATA__;
const MANAGER_NAMES = __MANAGER_NAMES__;
const WEEKS_AVAILABLE = __WEEKS_AVAILABLE__;
const PLAYOFF_TEAMS_COUNT = __PLAYOFF_TEAMS_COUNT__;
const CURRENT_WEEK = __CURRENT_WEEK__;

const BRACKET_TEMPLATES = {
    4: [
        [ {a:{seed:1}, b:{seed:4}}, {a:{seed:2}, b:{seed:3}} ],
        [ {a:{winnerOf:[0,0]}, b:{winnerOf:[0,1]}} ],
    ],
    6: [
        [ {a:{seed:3}, b:{seed:6}}, {a:{seed:4}, b:{seed:5}} ],
        [ {a:{seed:1}, b:{winnerOf:[0,1]}}, {a:{seed:2}, b:{winnerOf:[0,0]}} ],
        [ {a:{winnerOf:[1,0]}, b:{winnerOf:[1,1]}} ],
    ],
    8: [
        [ {a:{seed:1},b:{seed:8}}, {a:{seed:4},b:{seed:5}}, {a:{seed:3},b:{seed:6}}, {a:{seed:2},b:{seed:7}} ],
        [ {a:{winnerOf:[0,0]}, b:{winnerOf:[0,1]}}, {a:{winnerOf:[0,2]}, b:{winnerOf:[0,3]}} ],
        [ {a:{winnerOf:[1,0]}, b:{winnerOf:[1,1]}} ],
    ],
};

function computeStandingsThroughWeek(week) {
    const standings = {};
    for (const w of WEEKS_AVAILABLE) {
        if (w > week) break;
        for (const m of (MATCHUP_DATA[w] || [])) {
            const [u1, u2] = m.user_ids;
            const [s1, s2] = m.scores;
            if (u1 == null || u2 == null) continue;
            if (!standings[u1]) standings[u1] = {wins: 0, losses: 0, ties: 0, points_for: 0};
            if (!standings[u2]) standings[u2] = {wins: 0, losses: 0, ties: 0, points_for: 0};
            standings[u1].points_for += s1 || 0;
            standings[u2].points_for += s2 || 0;
            if (s1 > s2) { standings[u1].wins++; standings[u2].losses++; }
            else if (s2 > s1) { standings[u2].wins++; standings[u1].losses++; }
            else { standings[u1].ties++; standings[u2].ties++; }
        }
    }
    const rows = Object.entries(standings).map(([uid, s]) => ({
        user_id: uid, manager_name: MANAGER_NAMES[uid] || 'Unknown',
        wins: s.wins, losses: s.losses, ties: s.ties, points_for: Math.round(s.points_for * 10) / 10,
    }));
    rows.sort((a, b) => (b.wins - a.wins) || (b.points_for - a.points_for));
    rows.forEach((r, i) => { r.rank = i + 1; });
    return rows;
}

function renderTopPerformers(week) {
    const container = document.getElementById('topPerformersBody');
    const matchups = (MATCHUP_DATA[week] || []).filter(m => m.winner_user_id != null);
    if (!matchups.length) {
        container.innerHTML = "<p class='empty'>No completed matchups for this week.</p>";
        return;
    }
    const rows = matchups.map(m => {
        const winnerIdx = m.user_ids[0] === m.winner_user_id ? 0 : 1;
        const loserIdx = 1 - winnerIdx;
        return {
            winner: MANAGER_NAMES[m.user_ids[winnerIdx]] || m.manager_names[winnerIdx],
            loser: MANAGER_NAMES[m.user_ids[loserIdx]] || m.manager_names[loserIdx],
            winnerScore: m.scores[winnerIdx], loserScore: m.scores[loserIdx], margin: m.margin,
        };
    }).sort((a, b) => b.winnerScore - a.winnerScore);

    const body = rows.map((r, i) => `
        <tr>
            <td>${i + 1}</td>
            <td><strong>${r.winner}</strong></td>
            <td class="num">${r.winnerScore.toFixed(1)}</td>
            <td>${r.loser}</td>
            <td class="num">${r.loserScore.toFixed(1)}</td>
            <td class="num">${r.margin.toFixed(1)}</td>
        </tr>
    `).join('');
    container.innerHTML = `
        <div class="table-scroll"><table>
            <tr><th>#</th><th>Winner</th><th>Score</th><th>Lost To</th><th>Score</th><th>Margin</th></tr>
            ${body}
        </table></div>
    `;
}

function renderStandingsTable(week, standings) {
    const container = document.getElementById('standingsBody');
    const inTeams = standings.slice(0, PLAYOFF_TEAMS_COUNT);
    const bubble = standings.slice(PLAYOFF_TEAMS_COUNT, PLAYOFF_TEAMS_COUNT + 2);
    const cutoffWins = inTeams.length ? inTeams[inTeams.length - 1].wins : 0;

    const row = (t, extra) => `
        <tr>
            <td>#${t.rank}</td><td>${t.manager_name}</td>
            <td class="num">${t.wins}-${t.losses}${t.ties ? '-' + t.ties : ''}</td>
            <td class="num">${t.points_for.toFixed(1)}</td>
            <td>${extra || ''}</td>
        </tr>
    `;
    const bubbleRows = bubble.map(t => row(t, `${(cutoffWins - t.wins).toFixed(1)} GB`)).join('');

    container.innerHTML = `
        <p class="section-caption">Standings through week ${week} - top ${PLAYOFF_TEAMS_COUNT} make the playoffs</p>
        <div class="table-scroll"><table>
            <tr><th>Rank</th><th>Manager</th><th>Record</th><th>Points For</th><th></th></tr>
            ${inTeams.map(t => row(t)).join('')}
            ${bubbleRows}
        </table></div>
    `;
}

function resolveBracketSlot(slot, seeds, results) {
    if (slot.seed !== undefined) {
        const team = seeds[slot.seed - 1];
        return team ? { label: `#${slot.seed} ${team.manager_name}`, team } : { label: `#${slot.seed} TBD`, team: null };
    }
    const [r, m] = slot.winnerOf;
    return { label: `Winner of R${r + 1}G${m + 1}`, team: null };
}

function renderBracket(week, standings) {
    const container = document.getElementById('bracketBody');
    const template = BRACKET_TEMPLATES[PLAYOFF_TEAMS_COUNT];
    const seeds = standings.slice(0, PLAYOFF_TEAMS_COUNT);

    if (!template) {
        container.innerHTML = `<p class="empty">No bracket template for a ${PLAYOFF_TEAMS_COUNT}-team playoff field yet - showing seeds instead.</p>` +
            `<ol>${seeds.map(t => `<li>${t.manager_name} (${t.wins}-${t.losses})</li>`).join('')}</ol>`;
        return;
    }

    const roundsHtml = template.map((round, ri) => {
        const matchesHtml = round.map(match => {
            const a = resolveBracketSlot(match.a, seeds, null);
            const b = resolveBracketSlot(match.b, seeds, null);
            return `
                <div class="bracket-match">
                    <div class="bracket-team">${a.label}</div>
                    <div class="bracket-team">${b.label}</div>
                </div>
            `;
        }).join('');
        const roundTitle = ri === template.length - 1 ? 'Final' : `Round ${ri + 1}`;
        return `<div class="bracket-round"><div class="bracket-round-title">${roundTitle}</div>${matchesHtml}</div>`;
    }).join('');

    container.innerHTML = `
        <p class="section-caption">Seeded from standings through week ${week} - if the season ended today</p>
        <div class="bracket">${roundsHtml}</div>
    `;
}

function renderWeekInteractiveSections(week) {
    week = parseInt(week, 10);
    const standings = computeStandingsThroughWeek(week);
    renderTopPerformers(week);
    renderStandingsTable(week, standings);
    renderBracket(week, standings);
}

document.addEventListener('DOMContentLoaded', function () {
    const picker = document.getElementById('weekPicker');
    WEEKS_AVAILABLE.forEach(w => {
        const opt = document.createElement('option');
        opt.value = w;
        opt.textContent = `Week ${w}`;
        picker.appendChild(opt);
    });
    // Default to the most recently *completed* week, not just the highest week number present
    // in the data - a league's matchup data can include a future/unplayed week (0-0, no
    // winner_user_id yet), and landing there by default showed "no completed matchups" instead
    // of anything useful.
    const defaultWeek = (CURRENT_WEEK !== null && WEEKS_AVAILABLE.includes(CURRENT_WEEK))
        ? CURRENT_WEEK
        : (WEEKS_AVAILABLE.length ? WEEKS_AVAILABLE[WEEKS_AVAILABLE.length - 1] : null);
    if (defaultWeek !== null) {
        picker.value = defaultWeek;
        renderWeekInteractiveSections(defaultWeek);
    }
    picker.addEventListener('change', (e) => renderWeekInteractiveSections(e.target.value));
});
"""


def _render_week_interactive_script(matchup_results, manager_names, weeks_available, playoff_teams_count,
                                     current_week=None):
    js = _WEEK_INTERACTIVE_JS
    js = js.replace('__MATCHUP_DATA__', json.dumps(matchup_results))
    js = js.replace('__MANAGER_NAMES__', json.dumps(manager_names))
    js = js.replace('__WEEKS_AVAILABLE__', json.dumps(weeks_available))
    js = js.replace('__PLAYOFF_TEAMS_COUNT__', json.dumps(playoff_teams_count))
    js = js.replace('__CURRENT_WEEK__', json.dumps(current_week))
    return f"<script>{js}</script>"


def render_ai_overview_html(analysis_info, sections, faab_ledger, roster_to_manager, manager_names,
                             matchup_results=None, weeks_available=None, current_week=None,
                             playoff_teams_count=6):
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

    week_picker_html = """
    <div class="week-picker-row">
        <label for="weekPicker">Week:</label>
        <select id="weekPicker"></select>
    </div>
    """

    top_performers_card = _card(
        "Top Performers",
        week_picker_html + '<p class="section-caption">Head-to-head matchup winners, ranked by winning score</p>'
        + '<div id="topPerformersBody"><p class="empty">Loading...</p></div>'
    )

    bracket_card = _card(
        "Projected Playoff Bracket &amp; Standings",
        '<div id="standingsBody"><p class="empty">Loading...</p></div>'
        + '<div id="bracketBody" style="margin-top: 18px;"><p class="empty">Loading...</p></div>'
    )

    body = (
        top_performers_card
        + _card("Biggest Upsets", _render_upsets(sections['upsets']))
        + _card("Power Ranking Movers: Last Week vs This Week", _render_power_movers(sections['power_movers']))
        + _card("Matchups to Watch", _render_matchups_to_watch(sections['matchups_to_watch']))
        + bracket_card
        + _card("Median Standings", _render_median_standings(sections['median_standings']))
        + _card("Top Waiver Pickups", _render_waiver_pickups(sections['waiver_pickups']))
        + _render_faab_tracker(faab_ledger, roster_to_manager, manager_names)
    )

    script = _render_week_interactive_script(
        matchup_results or {}, manager_names, weeks_available or [], playoff_teams_count or 6,
        current_week=current_week,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>League Overview - {league_name} ({season})</title>
<style>
    /* Chicago Bears palette (navy + orange) on a light canvas - see index.html for the same
       token set. Kept in sync manually since this HTML is generated server-side, not shared
       CSS with the frontend. */
    :root {{
        --color-ink: #0B162A;
        --color-ink-secondary: #52607A;
        --color-canvas: #F2F4F8;
        --color-paper: #FFFFFF;
        --color-hairline: #DCE0E8;
        --color-accent: #C83803;
        --color-accent-soft: #FCE7DC;
        --color-success: #1B8A5A;
        --color-danger: #C0392B;
    }}
    * {{ box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Tahoma, Geneva, Verdana, sans-serif;
        background: var(--color-canvas);
        color: var(--color-ink);
        margin: 0;
        padding: 20px;
        min-height: 100vh;
    }}
    .container {{ max-width: 1100px; margin: 0 auto; }}
    .header {{
        text-align: center;
        margin-bottom: 30px;
        padding: 28px 25px;
        background: var(--color-ink);
        border-radius: 24px;
        color: white;
    }}
    .header h1 {{ font-weight: 700; letter-spacing: -0.02em; }}
    .header p {{ opacity: 0.75; margin: 4px 0 0; }}
    .section-card {{
        background: var(--color-paper);
        border-radius: 20px;
        padding: 22px 26px;
        margin-bottom: 22px;
        border: 1px solid var(--color-hairline);
    }}
    .section-card h2 {{ margin: 0 0 12px; color: var(--color-accent); font-size: 1.25rem; font-weight: 600; }}
    .section-caption {{ color: var(--color-ink-secondary); font-size: 0.9rem; margin: 0 0 10px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    /* Every generated table is wrapped in .table-scroll (see _render_* functions and the
       week-interactive JS) so a table wider than its card scrolls horizontally within its own
       card instead of being clipped by the page-level overflow-x: hidden safety net below. */
    .table-scroll {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
    th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--color-hairline); color: var(--color-ink); }}
    th {{ color: var(--color-ink-secondary); font-weight: 600; }}
    td.num, th.num {{ text-align: right; }}
    .positive {{ color: var(--color-success); }}
    .negative {{ color: var(--color-danger); }}
    .empty {{ color: var(--color-ink-secondary); font-style: italic; }}
    ul.upset-list, ul.matchup-list {{ list-style: none; padding: 0; margin: 0; }}
    ul.upset-list li, ul.matchup-list li {{
        padding: 10px 0; border-bottom: 1px solid var(--color-hairline);
    }}
    .badge {{
        display: inline-block; margin-left: 8px; padding: 2px 10px; border-radius: 10px;
        background: var(--color-accent-soft); color: var(--color-accent); font-size: 0.78rem; font-weight: 600;
    }}
    .notes {{ color: var(--color-ink-secondary); font-size: 0.85rem; margin-top: 4px; }}
    .faab-bar {{ background: var(--color-hairline); border-radius: 6px; height: 10px; width: 140px; }}
    .faab-bar-fill {{ background: var(--color-accent); height: 100%; border-radius: 6px; }}

    .week-picker-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }}
    .week-picker-row label {{ font-weight: 600; font-size: 0.9rem; }}
    .week-picker-row select {{
        padding: 8px 12px; border-radius: 999px; border: 1px solid var(--color-hairline);
        background: var(--color-paper); color: var(--color-ink); font-size: 0.9rem;
    }}

    .bracket {{
        display: flex; gap: 22px; overflow-x: auto; padding-bottom: 8px;
        -webkit-overflow-scrolling: touch;
    }}
    .bracket-round {{ display: flex; flex-direction: column; justify-content: space-around; min-width: 190px; flex: 0 0 auto; }}
    .bracket-round-title {{ text-align: center; font-weight: 600; color: var(--color-ink-secondary); font-size: 0.8rem; margin-bottom: 10px; }}
    .bracket-match {{
        background: var(--color-canvas); border: 1px solid var(--color-hairline); border-radius: 10px;
        padding: 8px 10px; margin-bottom: 24px; font-size: 0.85rem;
    }}
    .bracket-team {{ padding: 4px 0; }}
    .bracket-team:first-child {{ border-bottom: 1px solid var(--color-hairline); }}

    @media (max-width: 640px) {{
        .section-card {{ padding: 16px 18px; }}
        table {{ font-size: 0.82rem; }}
        th, td {{ padding: 5px 5px; }}
        .faab-bar {{ width: 70px; }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{league_name} - League Overview</h1>
        <p>Season {season} - Generated {generated_at}</p>
    </div>
    {body}
</div>
{script}
</body>
</html>"""
