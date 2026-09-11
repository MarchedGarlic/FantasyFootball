#!/usr/bin/env python3
"""
Weekly Digest export: a clean Markdown summary of this week's league activity, meant to be
copied and pasted into a separate Claude conversation to write a newsletter - explicit user
request, and explicitly *not* wired to any LLM API itself ("I don't want you to use Claude API
calls or anything, I plan on doing that manually"). This module only reformats data this app
already computes into Markdown; it makes no outbound calls of its own, unlike every other module
in this codebase that talks to Sleeper/ESPN.

Reuses src/ai_overview.py's compute_overview_context() for "what happened this week" instead of
re-deriving a second copy of upsets/power-movers/standings - the digest can never disagree with
the Overview page about what this week's story was.
"""

import html
from datetime import datetime

from src.ai_overview import compute_overview_context, _page_shell
from src.injury_severity import injury_severity_tier

_USAGE_NOTE = (
    "> Copy everything below this line and paste it into a new Claude conversation, along with "
    "something like: **\"Write this week's fantasy football newsletter for my league from this "
    "data - make it fun and engaging for my leaguemates.\"** Nothing on this page is sent "
    "anywhere automatically."
)


def _format_matchups_md(matchup_results, week):
    matchups = (matchup_results or {}).get(week) or []
    played = [m for m in matchups if m.get('winner_user_id') is not None]
    if not played:
        return "_No completed matchups this week._"
    played.sort(key=lambda m: max(m['scores']), reverse=True)
    lines = []
    for m in played:
        w_idx = 0 if m['user_ids'][0] == m['winner_user_id'] else 1
        l_idx = 1 - w_idx
        lines.append(
            f"- **{m['manager_names'][w_idx]}** def. {m['manager_names'][l_idx]}, "
            f"{m['scores'][w_idx]:.1f}-{m['scores'][l_idx]:.1f} (margin {m['margin']:.1f})"
        )
    return "\n".join(lines)


def _format_upsets_md(upsets, week):
    this_week = [u for u in (upsets or []) if u['week'] == week]
    if not this_week:
        return "_No upsets this week - results mostly went as the power rankings expected._"
    lines = []
    for u in this_week:
        lines.append(
            f"- **{u['winner']}** (ranked #{u['winner_rank_entering']}) upset "
            f"**{u['loser']}** (ranked #{u['loser_rank_entering']}) by {u['margin']:.1f} points"
        )
    return "\n".join(lines)


def _format_power_movers_md(power_movers):
    movers = (power_movers or {}).get('movers') or []
    if not movers:
        return "_Not enough data yet to compare weeks._"
    lines = [f"_Week {power_movers['last_week']} → Week {power_movers['this_week']}_"]
    for m in sorted(movers, key=lambda x: x['delta'], reverse=True):
        sign = '+' if m['delta'] > 0 else ''
        lines.append(f"- {m['manager_name']}: #{m['last_week_rank']} → #{m['this_week_rank']} ({sign}{m['delta']})")
    return "\n".join(lines)


def _format_standings_md(median_standings):
    if not median_standings:
        return "_No standings available yet._"
    lines = ["| Rank | Manager | Record | vs. Median | Combined | Combined % |", "|---|---|---|---|---|---|"]
    for r in median_standings:
        lines.append(
            f"| {r['rank']} | {r['name']} | {r['regular_wins']}-{r['regular_losses']} "
            f"| {r['median_wins']}-{r['median_losses']} | {r['combined_wins']}-{r['combined_losses']} "
            f"| {r['combined_pct'] * 100:.1f}% |"
        )
    return "\n".join(lines)


def _format_trades_md(trade_impacts, week):
    this_week = [t for t in (trade_impacts or []) if t.get('week') == week]
    if not this_week:
        return "_No trades this week._"
    lines = []
    for t in this_week:
        sign = '+' if t['combined_impact'] > 0 else ''
        faab = f" (also sent {t['faab_spent']:.0f} FAAB)" if t.get('faab_spent') else ""
        lines.append(
            f"- **{t['manager_name']}** got {', '.join(t['acquired_players']) or 'nothing'} "
            f"from {t['other_manager']}, gave up {', '.join(t['gave_up_players']) or 'nothing'}{faab} "
            f"(net player value {sign}{t['combined_impact']:.1f})"
        )
    return "\n".join(lines)


def _format_waivers_md(waiver_pickups):
    this_week = (waiver_pickups or {}).get('this_week') or []
    if not this_week:
        return "_No notable waiver activity this week._"
    lines = []
    for w in this_week:
        faab = f" - ${w['faab_spent']:.0f} FAAB" if w.get('faab_spent') else ""
        lines.append(f"- **{w['manager_name']}** added {w.get('player_added', 'a player')} (impact {w['combined_impact']:+.1f}{faab})")
    return "\n".join(lines)


def _format_matchups_to_watch_md(matchups_to_watch):
    if not matchups_to_watch:
        return "_No standings-relevant matchups flagged for next week._"
    lines = []
    for m in matchups_to_watch:
        lines.append(
            f"- **{m['manager_names'][0]}** (#{m['ranks'][0]}, {m['records'][0]}) vs "
            f"**{m['manager_names'][1]}** (#{m['ranks'][1]}, {m['records'][1]}) - {' / '.join(m['notes'])}"
        )
    return "\n".join(lines)


def _format_injury_notes_md(start_sit_players):
    """Pulls straight from the Start/Sit Analyzer's already-generated reasoning text (see
    src/start_sit.py) instead of re-deriving injury commentary a second time."""
    if not start_sit_players:
        return "_Start/Sit data not available for this run._"

    notable = [
        p for p in start_sit_players.values()
        if injury_severity_tier(p.get('injury_status')) in ('out', 'doubtful')
    ]
    boosted = [
        p for p in start_sit_players.values()
        if any('banged up' in r for r in (p.get('reasoning') or []))
    ]
    if not notable and not boosted:
        return "_No significant injuries flagged this week._"

    lines = []
    if notable:
        lines.append("**Banged up:**")
        for p in sorted(notable, key=lambda x: x['manager_name']):
            lines.append(f"- {p['name']} ({p['position']}, {p['manager_name']}'s team) - {p['injury_status']}")
    if boosted:
        lines.append("\n**Increased opportunity:**")
        for p in boosted:
            boost_reason = next(r for r in p['reasoning'] if 'banged up' in r)
            lines.append(f"- {p['name']} ({p['position']}, {p['manager_name']}'s team) - {boost_reason}")
    return "\n".join(lines)


def _format_faab_tracker_md(faab_ledger, roster_to_manager, manager_names):
    if not faab_ledger or not faab_ledger.get('enabled'):
        return None
    lookup_by_str = {str(k): v for k, v in roster_to_manager.items()}
    total = faab_ledger['total_budget']
    lines = ["| Manager | Remaining |", "|---|---|"]
    for roster_id, balance in sorted(faab_ledger['balances'].items(), key=lambda kv: kv[1], reverse=True):
        user_id = roster_to_manager.get(roster_id, lookup_by_str.get(str(roster_id)))
        name = manager_names.get(user_id, f'Roster {roster_id}')
        lines.append(f"| {name} | ${balance:.0f} / ${total:.0f} |")
    return "\n".join(lines)


def build_weekly_digest_markdown(output_data, detailed_data, roster_data, league_settings,
                                  faab_ledger, start_sit_data):
    """The actual Markdown text - everything else in this module is UI chrome around this."""
    ctx = compute_overview_context(output_data, detailed_data, roster_data, league_settings)
    analysis_info = ctx['analysis_info']
    week = ctx['current_week']
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y')

    faab_section = _format_faab_tracker_md(faab_ledger, ctx['roster_to_manager'], ctx['manager_names'])

    parts = [
        f"# {league_name} — Week {week} Digest",
        f"*Season {season} · Generated {generated_at}*",
        "",
        _USAGE_NOTE,
        "",
        "---",
        "",
        f"## Week {week} Results" if week is not None else "## Results",
        _format_matchups_md(ctx['matchup_results'], week),
        "",
        "## Biggest Upset",
        _format_upsets_md(ctx['sections']['upsets'], week),
        "",
        "## Power Ranking Movers",
        _format_power_movers_md(ctx['sections']['power_movers']),
        "",
        "## Standings (Real Record vs. Median Record)",
        _format_standings_md(ctx['sections']['median_standings']),
        "",
        "## Trades This Week",
        _format_trades_md((output_data.get('trade_analysis') or {}).get('trade_impacts'), week),
        "",
        "## Waiver Wire This Week",
        _format_waivers_md(ctx['sections']['waiver_pickups']),
        "",
        "## Injury Report & Opportunity Watch",
        _format_injury_notes_md((start_sit_data or {}).get('players')),
        "",
        "## Matchups to Watch Next Week",
        _format_matchups_to_watch_md(ctx['sections']['matchups_to_watch']),
    ]

    if faab_section:
        parts += ["", "## FAAB Tracker", faab_section]

    return "\n".join(parts) + "\n"


# ---- rendering: a copy/download UI around the raw Markdown ----

_DIGEST_STYLE = """<style>
    .digest-toolbar { display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
    .digest-btn {
        border-radius: 980px; padding: 10px 20px; font-weight: 600; font-size: 0.88rem;
        cursor: pointer; border: 1px solid var(--accent); background: var(--accent-soft); color: var(--accent);
    }
    .digest-btn.secondary { border-color: var(--line); background: transparent; color: var(--ink-muted); }
    .digest-text {
        width: 100%; min-height: 60vh; padding: 16px; border-radius: 14px; border: 1px solid var(--line);
        background: var(--void); color: var(--ink); font-family: 'SFMono-Regular', Consolas, monospace;
        font-size: 0.82rem; line-height: 1.5; white-space: pre-wrap; resize: vertical;
    }
    @media (max-width: 640px) {
        .digest-btn { flex: 1; text-align: center; }
    }
</style>"""


def render_weekly_digest_html(markdown_text, analysis_info, filename):
    league_name = analysis_info.get('league_name', 'Fantasy League')
    season = analysis_info.get('season', '')
    generated_at = datetime.now().strftime('%B %d, %Y at %I:%M %p')

    # Manager/player display names are arbitrary user-chosen strings that could contain
    # '<', '>', or '&' - escaped before landing inside the raw <textarea> content so they
    # can't be misread as markup (this app generates the text, but it embeds real Sleeper
    # display names it doesn't control).
    escaped_text = html.escape(markdown_text)
    body = f"""
    {_DIGEST_STYLE}
    <div class="section-card">
        <h2>Weekly Digest Export</h2>
        <p class="section-caption">
            A plain-text summary of this week's league activity, formatted to paste into a
            Claude conversation so you can write your own newsletter from it. Nothing here is
            sent anywhere automatically - copy it, download it, or select it manually.
        </p>
        <!-- Download builds the file client-side from a Blob rather than linking to a server
             path: /results/<filename> (server.py) only knows how to serve html_reports/ and
             json_data/, not a third text_reports/ location, and this way works identically on
             the static Netlify build too, with no server involved at all either way. -->
        <div class="digest-toolbar">
            <button class="digest-btn" type="button" onclick="
                const btn = this;
                const textarea = document.getElementById('digestText');
                navigator.clipboard.writeText(textarea.value).then(() => {{
                    btn.textContent = 'Copied!';
                    setTimeout(() => {{ btn.textContent = 'Copy to Clipboard'; }}, 2000);
                }}).catch(() => {{
                    // Clipboard API can refuse for reasons outside this page's control (focus,
                    // browser permissions, embedding context) - fall back to selecting the text
                    // so a manual Ctrl+C/Cmd+C still works instead of the button doing nothing.
                    textarea.focus();
                    textarea.select();
                    btn.textContent = 'Selected - press Ctrl+C';
                    setTimeout(() => {{ btn.textContent = 'Copy to Clipboard'; }}, 2500);
                }});
            ">Copy to Clipboard</button>
            <button class="digest-btn secondary" type="button" onclick="
                const blob = new Blob([document.getElementById('digestText').value], {{ type: 'text/markdown' }});
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = '{filename}';
                document.body.appendChild(a); a.click(); document.body.removeChild(a);
                URL.revokeObjectURL(url);
            ">Download .md</button>
        </div>
        <textarea id="digestText" class="digest-text" readonly>{escaped_text}</textarea>
    </div>
    """

    return _page_shell(
        title=f"Weekly Digest - {league_name} ({season})",
        header_title=f"{league_name} &mdash; Weekly Digest",
        header_subtitle=f"Season {season} &middot; Generated {generated_at}",
        body_html=body,
    )


def build_weekly_digest_report(output_data, detailed_data, roster_data, league_settings,
                                faab_ledger, start_sit_data):
    """Entry point mirroring build_trade_analyzer()/build_start_sit_report() - called from
    main.py. Returns (markdown_text, html_page) so main.py can write both a raw .md file (for
    direct download / feeding to another tool) and the copy/download UI page.
    """
    markdown_text = build_weekly_digest_markdown(
        output_data, detailed_data, roster_data, league_settings, faab_ledger, start_sit_data
    )
    html_page = render_weekly_digest_html(
        markdown_text, output_data.get('analysis_info') or {}, filename="weekly_digest.md"
    )
    return markdown_text, html_page
