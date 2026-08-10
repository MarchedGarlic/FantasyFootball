#!/usr/bin/env python3
"""
AI Overview - fully deterministic, no LLM call (see CLAUDE.md sections 1 and 5 for why).

The old version imported `openai`, read OPENAI_API_KEY, and then a hardcoded line always called
a mock generator instead of ever actually calling OpenAI. This module replaces that entirely:
every section below is computed from real per-week data that main.py now persists (previously
fetched from Sleeper and discarded before it reached a JSON file).

Six sections: top players of the week, biggest upsets, power ranking movers (last week vs this
week), matchups to watch, projected playoff teams, and top waiver pickups.
"""

from datetime import datetime


def top_players_of_week(weekly_top_players, week=None, limit=10):
    """Highest-scoring rostered players for a given week (defaults to the most recent week
    with data). Sourced from Sleeper matchups' players_points, which used to be discarded."""
    if not weekly_top_players:
        return {'week': None, 'players': []}

    weeks = sorted(int(w) for w in weekly_top_players.keys())
    if week is None:
        week = weeks[-1]

    players = weekly_top_players.get(week, weekly_top_players.get(str(week), []))
    return {'week': week, 'players': players[:limit]}


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
    """Real standings (wins, then points-for as tiebreak) from Sleeper's own roster settings -
    not power rating, which is a talent/performance metric, not the official standings."""
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


def projected_playoff_teams(standings, playoff_teams_count):
    """'If the season ended today' standings snapshot against the league's real playoff_teams
    count - explicitly a snapshot, not a playoff-odds simulation."""
    playoff_teams_count = playoff_teams_count or 6
    in_teams = standings[:playoff_teams_count]
    bubble = standings[playoff_teams_count:playoff_teams_count + 2]
    out_teams = standings[playoff_teams_count + 2:]

    cutoff_wins = in_teams[-1]['wins'] if in_teams else 0
    for team in bubble:
        team['games_back'] = round(cutoff_wins - team['wins'], 1)

    return {
        'in': in_teams, 'bubble': bubble, 'out': out_teams,
        'playoff_teams_count': playoff_teams_count,
    }


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
    """Compute all six sections and render them as one HTML page."""
    manager_names = {
        uid: data.get('manager_name', 'Unknown')
        for uid, data in (output_data.get('power_ratings') or {}).items()
    }
    power_rank_history = output_data.get('power_rank_history') or {}
    power_rank_history = {int(k): v for k, v in power_rank_history.items()}

    weekly_top_players = detailed_data.get('weekly_top_players') or {}
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

    standings = standings_from_rosters(rosters, roster_to_manager, manager_names)

    sections = {
        'top_players': top_players_of_week(weekly_top_players, week=current_week),
        'upsets': biggest_upsets(matchup_results, power_rank_history, manager_names),
        'power_movers': power_rank_movers(power_rank_history, manager_names),
        'matchups_to_watch': matchups_to_watch(next_week_matchups, standings, playoff_teams_count),
        'playoff_picture': projected_playoff_teams(standings, playoff_teams_count),
        'waiver_pickups': top_waiver_pickups(
            (output_data.get('trade_analysis') or {}).get('waiver_impacts') or [], faab_enabled
        ),
    }

    return render_ai_overview_html(analysis_info, sections, faab_ledger, roster_to_manager, manager_names)


# ---- rendering ----

def _card(title, body_html):
    return f"""
    <div class="section-card">
        <h2>{title}</h2>
        {body_html}
    </div>
    """


def _render_top_players(section):
    if not section['players']:
        return "<p class='empty'>No player scoring data available yet.</p>"
    rows = "".join(
        f"""<tr>
            <td>{i + 1}</td>
            <td>{p['name']}</td>
            <td>{p['position']} - {p['team']}</td>
            <td>{p['manager_name']}</td>
            <td class="num">{p['points']:.1f}</td>
        </tr>"""
        for i, p in enumerate(section['players'][:10])
    )
    return f"""
    <p class="section-caption">Week {section['week']}</p>
    <table>
        <tr><th>#</th><th>Player</th><th>Pos / Team</th><th>Manager</th><th>Points</th></tr>
        {rows}
    </table>
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
    <table>
        <tr><th>Manager</th><th>Last Week</th><th>This Week</th><th>Change</th></tr>
        {rows}
    </table>
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


def _render_playoff_picture(picture):
    def team_row(t, extra=""):
        return f"""<tr>
            <td>#{t['rank']}</td><td>{t['manager_name']}</td>
            <td class="num">{t['wins']}-{t['losses']}{'-' + str(t['ties']) if t['ties'] else ''}</td>
            <td class="num">{t['points_for']:.1f}</td>
            <td>{extra}</td>
        </tr>"""

    in_rows = "".join(team_row(t) for t in picture['in'])
    bubble_rows = "".join(team_row(t, f"{t.get('games_back', 0):.1f} GB") for t in picture['bubble'])

    return f"""
    <p class="section-caption">If the season ended today - top {picture['playoff_teams_count']} make the playoffs</p>
    <table>
        <tr><th>Rank</th><th>Manager</th><th>Record</th><th>Points For</th><th></th></tr>
        {in_rows}
        {bubble_rows}
    </table>
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
        <table>{header}{this_week_rows}</table>
        """

    return f"""
    {this_week_html}
    <p class="section-caption">Season-best pickups</p>
    <table>{header}{season_rows}</table>
    """


def _render_faab_tracker(faab_ledger, roster_to_manager, manager_names):
    if not faab_ledger or not faab_ledger.get('enabled'):
        return ""

    rows = []
    for roster_id, balance in sorted(faab_ledger['balances'].items(), key=lambda kv: kv[1], reverse=True):
        user_id = roster_to_manager.get(roster_id)
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
    <table><tr><th>Manager</th><th>Remaining</th><th></th></tr>{''.join(rows)}</table>
    """)


def render_ai_overview_html(analysis_info, sections, faab_ledger, roster_to_manager, manager_names):
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

    body = (
        _card("Top Players of the Week", _render_top_players(sections['top_players']))
        + _card("Biggest Upsets", _render_upsets(sections['upsets']))
        + _card("Power Ranking Movers: Last Week vs This Week", _render_power_movers(sections['power_movers']))
        + _card("Matchups to Watch", _render_matchups_to_watch(sections['matchups_to_watch']))
        + _card("Projected Playoff Picture", _render_playoff_picture(sections['playoff_picture']))
        + _card("Top Waiver Pickups", _render_waiver_pickups(sections['waiver_pickups']))
        + _render_faab_tracker(faab_ledger, roster_to_manager, manager_names)
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
</body>
</html>"""
