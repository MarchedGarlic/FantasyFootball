#!/usr/bin/env python3
"""
Fantasy Football Analysis Main Orchestrator
Coordinates all modules to provide comprehensive fantasy football analysis for one league and
one season at a time. Every output is keyed by (league_id, season) via src.storage.AnalysisStorage
- see CLAUDE.md sections 1 and 3 for why that matters and what used to go wrong without it.
"""

import sys
import os
import json
import math
from datetime import datetime

# Several modules print emoji status markers (data unicode, not decoration you'd want to strip
# module-by-module). Windows' default console/pipe encoding (cp1252) can't encode them, which
# crashed the whole analysis mid-run with an UnicodeEncodeError as soon as the first emoji print
# happened - reconfigure stdout/stderr to UTF-8 once, here, rather than hunting down every print.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        _stream.reconfigure(encoding='utf-8', errors='replace')

from src.api_clients import ESPNAPI, SleeperAPI
from src.roster_grading import FantasyAnalyzer
from src.power_rankings import calculate_weekly_power_ratings, create_power_rating_plot, compute_power_rank_history
from src.median_record_calculator import calculate_median_records
from src.faab_analysis import build_faab_ledger, is_faab_league
from src.storage import AnalysisStorage
from src.trade_analysis import (
    analyze_real_trades_only,
    analyze_waiver_pickups,
    calculate_manager_grades,
    create_trade_visualization,
    create_waiver_visualization,
    create_manager_grade_visualization,
    print_trade_analysis_results
)
from src.visualizations import (
    create_roster_grade_plot,
    create_luck_analysis_plot,
    create_power_ranking_leaderboard
)
from src.ai_overview import build_ai_overview, build_draft_info, _most_recent_completed_week
from src.trade_value import build_trade_analyzer
from src.start_sit import build_start_sit_report
from src.draft_analysis import (
    get_primary_draft,
    reconstruct_draft_results,
    calculate_biggest_steals,
    calculate_draft_ratings,
)


def load_league_config():
    """Load league configuration from file or environment variables (CLI/offline path only -
    the web server passes username/season/league_id to run_analysis() directly, see below)."""
    try:
        with open('league_config.json', 'r') as f:
            config = json.load(f)
            print(f"Loaded config for league: {config.get('league_name', 'Unknown')}")
            return config
    except FileNotFoundError:
        print("No league_config.json found, using interactive mode")
    except Exception as e:
        print(f"[WARNING] Error loading config: {e}")

    sleeper_username = os.getenv('SLEEPER_USERNAME')
    league_id = os.getenv('LEAGUE_ID')

    if sleeper_username and league_id:
        return {
            'sleeper_username': sleeper_username,
            'league_id': league_id,
            'target_season': int(os.getenv('TARGET_SEASON', str(datetime.now().year))),
            'auto_select': True
        }

    return None


def get_current_season(sleeper_api):
    """Current NFL season from Sleeper's own /state/nfl endpoint, instead of a hardcoded year
    that would need a code change every offseason."""
    state = sleeper_api.get_nfl_state()
    if state and state.get('league_season'):
        try:
            return int(state['league_season'])
        except (TypeError, ValueError):
            pass
    return datetime.now().year


def get_user_input_interactive(sleeper_api):
    """Get user input interactively when no config is available (CLI only)."""
    username = input("\n[*] Enter your Sleeper username: ").strip()
    if not username:
        print("[ERROR] Username cannot be empty")
        return None, None

    current_season = get_current_season(sleeper_api)

    print("\nSeason Options:")
    print(f"   1. {current_season} leagues only")
    print(f"   2. {current_season - 1} leagues only")
    print(f"   3. All available leagues ({current_season - 3}-{current_season})")

    while True:
        try:
            season_choice = input("\n[*] Select season option (1-3): ").strip()

            if season_choice == "1":
                return username, current_season
            elif season_choice == "2":
                return username, current_season - 1
            elif season_choice == "3":
                return username, None  # Show all seasons
            else:
                print("[ERROR] Please enter 1, 2, or 3")

        except KeyboardInterrupt:
            print("\n[*] Goodbye!")
            return None, None


def get_user_leagues(sleeper_api, username, target_season=None):
    """Get all leagues for a user, across one season or the last few seasons."""
    print(f"\n[*] Finding leagues for user: {username}")

    user_data = sleeper_api.get_user_by_username(username)
    if not user_data:
        print(f"   [ERROR] User '{username}' not found")
        return None, []

    user_id = user_data.get('user_id')
    display_name = user_data.get('display_name', username)
    print(f"   [OK] Found user: {display_name} (ID: {user_id})")

    if target_season:
        seasons_to_check = [target_season]
        print(f"   - Checking {target_season} leagues only...")
    else:
        current_season = get_current_season(sleeper_api)
        seasons_to_check = list(range(current_season, current_season - 4, -1))
        print(f"   - Checking multiple seasons: {seasons_to_check}")

    all_leagues = []
    for season in seasons_to_check:
        print(f"   - Checking {season} leagues...")
        leagues = sleeper_api.get_user_leagues(user_id, season)
        if leagues:
            for league in leagues:
                league['season'] = season
                all_leagues.append(league)
            print(f"     Found {len(leagues)} leagues")
        else:
            print("     No leagues found")

    return user_id, all_leagues


def select_league_interactive(leagues):
    """Let user select a league interactively"""
    if not leagues:
        print("\n[ERROR] No leagues found")
        return None

    print(f"\nFound {len(leagues)} leagues:")
    print("-" * 80)
    print(f"{'#':<3} {'League Name':<30} {'Season':<8} {'Teams':<6} {'League ID':<20}")
    print("-" * 80)

    for i, league in enumerate(leagues, 1):
        name = league.get('name', 'Unknown League')[:29]
        season = league.get('season', 'Unknown')
        total_rosters = league.get('total_rosters', 'Unknown')
        league_id = league.get('league_id', 'Unknown')[:19]
        print(f"{i:<3} {name:<30} {season:<8} {total_rosters:<6} {league_id:<20}")

    print("-" * 80)

    while True:
        try:
            choice = input(f"\n[*] Select league (1-{len(leagues)}) or 'q' to quit: ").strip()

            if choice.lower() == 'q':
                print("[*] Goodbye!")
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(leagues):
                selected_league = leagues[choice_num - 1]
                print(f"\nSelected: {selected_league.get('name', 'Unknown')} ({selected_league.get('season', 'Unknown')})")
                return selected_league
            else:
                print(f"[ERROR] Please enter a number between 1 and {len(leagues)}")

        except ValueError:
            print("[ERROR] Please enter a valid number or 'q' to quit")
        except KeyboardInterrupt:
            print("\n[*] Goodbye!")
            return None


def resolve_league(sleeper_api, username, season, league_id):
    """Validate a (username, season, league_id) combination against Sleeper.

    Raises ValueError with a clear message if the user doesn't exist or the league isn't one
    of theirs for that season - this is the single source of truth for "is this a real league
    for this user in this season", used by both the CLI and the web server so they can never
    disagree about which league got analyzed.
    """
    user_data = sleeper_api.get_user_by_username(username)
    if not user_data:
        raise ValueError(f"Sleeper user '{username}' not found")

    user_id = user_data.get('user_id')
    leagues = sleeper_api.get_user_leagues(user_id, season) or []
    selected_league = next((l for l in leagues if l.get('league_id') == league_id), None)

    if not selected_league:
        available = ", ".join(l.get('name', 'Unknown') for l in leagues) or "none"
        raise ValueError(
            f"League {league_id} not found for '{username}' in {season}. "
            f"Available leagues that season: {available}"
        )

    return user_id, selected_league


def _num_playoff_rounds(playoff_teams):
    """Rough single-elimination bracket depth for a given playoff field size."""
    if not playoff_teams or playoff_teams < 2:
        return 2
    return max(1, math.ceil(math.log2(playoff_teams)))


def _determine_analysis_weeks(league_settings):
    """Real week range for this league's schedule, from its own settings, instead of a
    hardcoded 'assume 15 weeks unless season < 2021' guess that silently dropped the last 1-2
    weeks of data for leagues with a longer schedule."""
    playoff_week_start = league_settings.get('playoff_week_start')
    if playoff_week_start:
        rounds = _num_playoff_rounds(league_settings.get('playoff_teams', 6))
        last_week = min(18, playoff_week_start + rounds)
        return list(range(1, last_week + 1))
    return list(range(1, 18))  # generous fallback; weeks with no data are simply omitted


def reconstruct_roster_history(current_players, transactions_by_week, roster_id, weeks_desc):
    """Roster composition for a roster_id at the end of each week, reconstructed by walking the
    season's real transactions backward from the current roster. This replaces the old
    random.uniform()-seeded 'weekly variation' with the manager's actual historical roster, so
    roster grades - and the trade impact scores that depend on them - reflect what was really on
    the roster that week instead of noise. `weeks_desc` must be sorted descending.
    """
    history = {}
    roster = set(current_players or [])

    for week in weeks_desc:
        history[week] = set(roster)
        for transaction in transactions_by_week.get(f"Week {week}", []) or []:
            if not transaction or transaction.get('status') not in (None, 'complete'):
                continue
            for player_id, rid in (transaction.get('adds') or {}).items():
                if rid == roster_id:
                    roster.discard(player_id)
            for player_id, rid in (transaction.get('drops') or {}).items():
                if rid == roster_id:
                    roster.add(player_id)

    return history


def _players_to_gradeable(player_ids, all_players):
    players = []
    for player_id in player_ids:
        info = all_players.get(player_id)
        if not info:
            continue
        name = info.get('full_name') or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
        position = info.get('position', 'Unknown')
        if name and position != 'Unknown':
            players.append({'name': name, 'position': position})
    return players


def _collect_weekly_top_players(all_weekly_matchups, roster_to_manager, user_lookup, all_players, top_n=25):
    """Every rostered player's points for each week, trimmed to the league-wide top N and
    enriched with name/position/manager. Feeds the AI Overview's 'top players of the week'
    section - this data used to be fetched from Sleeper and discarded before it ever reached a
    JSON file (see CLAUDE.md section 5).
    """
    weekly_top_players = {}

    for week, matchups in all_weekly_matchups.items():
        scored = []
        for team in matchups or []:
            roster_id = team.get('roster_id')
            manager_id = roster_to_manager.get(roster_id)
            manager_name = user_lookup.get(manager_id, {}).get('display_name', 'Unknown') if manager_id else 'Unknown'
            starters = set(team.get('starters') or [])

            for player_id, points in (team.get('players_points') or {}).items():
                if points is None:
                    continue
                info = all_players.get(player_id, {})
                name = (info.get('full_name')
                        or f"{info.get('first_name', '')} {info.get('last_name', '')}".strip()
                        or f"Player_{player_id}")
                scored.append({
                    'player_id': player_id,
                    'name': name,
                    'position': info.get('position', 'Unknown'),
                    'team': info.get('team') or 'FA',
                    'points': round(points, 2),
                    'roster_id': roster_id,
                    'manager_name': manager_name,
                    'started': player_id in starters,
                })

        scored.sort(key=lambda p: p['points'], reverse=True)
        weekly_top_players[week] = scored[:top_n]

    return weekly_top_players


def _collect_matchup_results(all_weekly_matchups, roster_to_manager, user_lookup):
    """Head-to-head result (winner/loser/margin) for every matchup in every week, kept around
    instead of being discarded right after tallying win/loss counts - needed for upset
    detection in the AI Overview.
    """
    matchup_results = {}

    for week, matchups in all_weekly_matchups.items():
        groups = {}
        for team in matchups or []:
            matchup_id = team.get('matchup_id')
            if matchup_id is None:
                continue
            groups.setdefault(matchup_id, []).append(team)

        results = []
        for matchup_id, teams in groups.items():
            if len(teams) != 2:
                continue
            t1, t2 = teams
            r1, r2 = t1.get('roster_id'), t2.get('roster_id')
            s1, s2 = t1.get('points', 0) or 0, t2.get('points', 0) or 0
            m1, m2 = roster_to_manager.get(r1), roster_to_manager.get(r2)

            results.append({
                'matchup_id': matchup_id,
                'roster_ids': [r1, r2],
                'user_ids': [m1, m2],
                'manager_names': [
                    user_lookup.get(m1, {}).get('display_name', 'Unknown'),
                    user_lookup.get(m2, {}).get('display_name', 'Unknown'),
                ],
                'scores': [s1, s2],
                'winner_roster_id': r1 if s1 > s2 else (r2 if s2 > s1 else None),
                'winner_user_id': m1 if s1 > s2 else (m2 if s2 > s1 else None),
                'margin': round(abs(s1 - s2), 2),
            })

        matchup_results[week] = results

    return matchup_results


def run_analysis(username, season, league_id, storage=None, progress_cb=None):
    """Run the full analysis pipeline for one league+season and persist results via `storage`.

    This is what server.py calls directly with an explicit (username, season, league_id) - it
    never depends on the shared league_config.json file, so two analyses for different
    leagues/seasons can never race on a shared config side-channel (see CLAUDE.md section 3.2).
    `main()` below is the CLI entry point that resolves those three values from a config
    file/env vars/interactive prompts and then calls this. Raises on failure instead of
    swallowing every exception and returning None, so callers (and process exit codes) can
    tell success from failure.
    """
    storage = storage or AnalysisStorage()
    season = int(season)

    def progress(message):
        print(message)
        if progress_cb:
            progress_cb(message)

    progress("Initializing API connections...")
    espn_api = ESPNAPI()
    sleeper_api = SleeperAPI()

    progress(f"Resolving league {league_id} for {username} ({season})...")
    user_id, selected_league = resolve_league(sleeper_api, username, season, league_id)
    progress(f"League: {selected_league.get('name', 'Unknown')} | Season: {season} | League ID: {league_id}")

    analyzer = FantasyAnalyzer(espn_api)

    progress("Fetching ESPN stat leaders...")
    analyzer.initialize_rankings(str(season), storage=storage)

    progress("Fetching NFL player database...")
    all_players = sleeper_api.get_all_players(storage=storage)
    progress(f"Loaded {len(all_players)} NFL players")

    progress("Getting league information...")
    league_info = sleeper_api.get_league_info(league_id)
    if not league_info:
        raise RuntimeError("Failed to get league information from Sleeper")
    league_settings = league_info.get('settings') or {}

    progress("Getting rosters and user data...")
    rosters = sleeper_api.get_league_rosters(league_id)
    users = sleeper_api.get_league_users(league_id)
    if not rosters or not users:
        raise RuntimeError("Failed to get rosters or users from Sleeper")

    user_lookup = {user['user_id']: user for user in users}
    roster_to_manager = {
        roster.get('roster_id'): roster.get('owner_id')
        for roster in rosters if roster.get('roster_id') and roster.get('owner_id')
    }
    print(f"   Created roster mapping for {len(roster_to_manager)} teams")

    progress("Fetching draft results and preseason rankings...")
    drafts = sleeper_api.get_league_drafts(league_id)
    primary_draft = get_primary_draft(drafts)
    draft_picks = sleeper_api.get_draft_picks(primary_draft['draft_id']) if primary_draft else []
    espn_draft_ranks = espn_api.get_preseason_draft_ranks(season, storage=storage)
    draft_results = reconstruct_draft_results(draft_picks, roster_to_manager, user_lookup, all_players)
    # PPR vs standard changes which preseason rank list (pass-catching backs/slot receivers
    # move the most between the two) is the fairer "expected draft slot" baseline.
    draft_scoring_type = 'ppr' if (league_info.get('scoring_settings') or {}).get('rec', 0) > 0 else 'standard'
    biggest_steals = calculate_biggest_steals(draft_results, espn_draft_ranks, draft_scoring_type)
    draft_ratings = calculate_draft_ratings(draft_results, espn_draft_ranks, analyzer, draft_scoring_type)
    print(f"   Draft: {len(draft_results)} picks reconstructed, {len(draft_ratings)} managers rated")

    weeks_to_fetch = _determine_analysis_weeks(league_settings)
    progress(f"Fetching weekly matchups (weeks 1-{weeks_to_fetch[-1]}, in parallel)...")
    all_weekly_matchups = sleeper_api.get_league_matchups_bulk(league_id, weeks_to_fetch)

    progress("Fetching NFL schedule (in parallel)...")
    schedule_by_week = espn_api.get_weekly_schedule_bulk(weeks_to_fetch, season, storage=storage)

    progress("Fetching league transactions (in parallel)...")
    raw_transactions_by_week = sleeper_api.get_league_transactions_bulk(league_id, weeks_to_fetch)
    transactions_by_week = {f"Week {week}": txns for week, txns in raw_transactions_by_week.items()}
    all_trades = [t for txns in transactions_by_week.values() for t in txns if t.get('type') == 'trade']
    progress(f"Total trades found: {len(all_trades)}")

    progress("Reconstructing FAAB ledger...")
    faab_ledger = build_faab_ledger(transactions_by_week, rosters, league_settings)
    for warning in faab_ledger.get('warnings', []):
        progress(f"[WARNING] {warning}")

    output_dirs = storage.paths_for(league_id, season, clear=True)
    progress(f"Output directory ready: {output_dirs['base']}")

    progress("Calculating Power Ratings...")
    team_power_data = calculate_weekly_power_ratings(all_weekly_matchups, rosters, user_lookup)

    progress("Calculating Median-Based Combined Records...")
    median_records = calculate_median_records(all_weekly_matchups, rosters, user_lookup)
    for uid, median_data in median_records.items():
        if uid in team_power_data:
            team_power_data[uid]['combined_record'] = median_data['combined_record']
            team_power_data[uid]['median_record'] = median_data['median_record']
            team_power_data[uid]['weekly_median_results'] = median_data['weekly_median_results']

    power_rank_history = compute_power_rank_history(team_power_data)

    progress("Calculating weekly roster grades from actual historical rosters...")
    roster_grade_data = {}
    weeks_sorted = sorted(all_weekly_matchups.keys())
    weeks_desc = sorted(weeks_sorted, reverse=True)

    for uid, power_data in team_power_data.items():
        user_name = power_data['name']
        user_roster = next((r for r in rosters if r.get('owner_id') == uid), None)
        if not user_roster or not user_roster.get('players'):
            continue

        roster_id = user_roster.get('roster_id')
        history = reconstruct_roster_history(
            user_roster.get('players', []), transactions_by_week, roster_id, weeks_desc
        )

        weekly_grades = {}
        for week in weeks_sorted:
            week_players = _players_to_gradeable(history.get(week, set()), all_players)
            week_analysis = analyzer.grade_roster(week_players) if week_players else None
            weekly_grades[week] = week_analysis.get('overall_grade', 0.0) if week_analysis else 0.0

        if weekly_grades:
            all_grades = list(weekly_grades.values())
            roster_grade_data[uid] = {
                'name': user_name,
                'weekly_roster_grades': weekly_grades,
                'current_grade': all_grades[-1],
                'average_grade': sum(all_grades) / len(all_grades),
                'highest_grade': max(all_grades),
                'lowest_grade': min(all_grades),
                'grade_trend': 'improving' if len(all_grades) >= 2 and all_grades[-1] > all_grades[0] else 'declining',
            }

    progress("Starting Comprehensive Analysis...")
    trade_impacts = analyze_real_trades_only(
        transactions_by_week, team_power_data, roster_grade_data,
        user_lookup, roster_to_manager, all_players, output_dirs,
        faab_ledger=faab_ledger, analyzer=analyzer,
    )
    waiver_impacts = analyze_waiver_pickups(
        transactions_by_week, user_lookup, roster_to_manager,
        all_weekly_matchups, all_players, output_dirs,
        faab_ledger=faab_ledger,
    )
    manager_grades = calculate_manager_grades(
        trade_impacts, waiver_impacts, team_power_data, roster_grade_data, user_lookup,
        weeks=weeks_to_fetch,
    )
    print_trade_analysis_results(trade_impacts, waiver_impacts)

    progress("Creating interactive visualizations...")
    create_power_rating_plot(team_power_data, output_dirs)
    create_power_ranking_leaderboard(team_power_data, output_dirs)
    create_roster_grade_plot(roster_grade_data, output_dirs, team_power_data)
    create_luck_analysis_plot(team_power_data, output_dirs)

    if trade_impacts:
        create_trade_visualization(trade_impacts, transactions_by_week, output_dirs)
    if waiver_impacts:
        create_waiver_visualization(waiver_impacts, output_dirs)
    if manager_grades:
        valid_managers = {mid: d for mid, d in manager_grades.items() if d.get('weekly_grades')}
        if valid_managers:
            create_manager_grade_visualization(valid_managers, output_dirs)

    progress("Collecting weekly player/matchup data for the AI overview...")
    weekly_top_players = _collect_weekly_top_players(all_weekly_matchups, roster_to_manager, user_lookup, all_players)
    matchup_results = _collect_matchup_results(all_weekly_matchups, roster_to_manager, user_lookup)

    progress("Generating JSON output files...")
    output_data = {
        'analysis_info': {
            'timestamp': datetime.now().isoformat(),
            'league_name': selected_league.get('name', 'Unknown'),
            'season': season,
            'league_id': league_id,
            'total_managers': len(users),
            'total_weeks_analyzed': len(all_weekly_matchups),
            'total_trades_found': len(all_trades),
            'playoff_teams': league_settings.get('playoff_teams'),
            'faab_enabled': is_faab_league(league_settings),
        },
        'power_ratings': {
            uid: {
                'manager_name': data['name'],
                'weekly_ratings': data['weekly_power_ratings'],
                'current_rating': data.get('current_rating', 0),
                'average_rating': data.get('average_rating', 0),
                'highest_rating': data.get('highest_rating', 0),
                'lowest_rating': data.get('lowest_rating', 0),
                'rating_trend': data.get('rating_trend', 'stable'),
                'total_weeks': data.get('total_weeks', 0),
            } for uid, data in team_power_data.items()
        },
        'roster_grades': {
            uid: {
                'manager_name': data['name'],
                'weekly_grades': data['weekly_roster_grades'],
                'current_grade': data.get('current_grade', 0),
                'average_grade': data.get('average_grade', 0),
                'highest_grade': data.get('highest_grade', 0),
                'lowest_grade': data.get('lowest_grade', 0),
                'grade_trend': data.get('grade_trend', 'stable'),
            } for uid, data in roster_grade_data.items()
        },
        'trade_analysis': {
            'trade_impacts': trade_impacts,
            'waiver_impacts': waiver_impacts,
            'manager_grades': manager_grades,
        },
        'faab_ledger': faab_ledger,
        'power_rank_history': power_rank_history,
        'draft_ratings': draft_ratings,
        'biggest_steals': biggest_steals,
        'median_standings': {
            uid: {
                'name': data['name'],
                'regular_record': data['regular_record'],
                'median_record': data['median_record'],
                'combined_record': data['combined_record'],
            } for uid, data in median_records.items()
        },
        'summary_statistics': {
            'comprehensive_analysis': {
                'total_trades': len(all_trades),
                'trade_impacts_count': len(trade_impacts),
                'waiver_impacts_count': len(waiver_impacts),
                'manager_grades_count': len(manager_grades),
            }
        },
    }

    if team_power_data:
        ranked = sorted(
            ((d['name'], d.get('current_rating', 0)) for d in team_power_data.values()),
            key=lambda x: x[1], reverse=True
        )
        output_data['summary_statistics']['power_ratings'] = {
            'highest': {'manager': ranked[0][0], 'rating': ranked[0][1]},
            'lowest': {'manager': ranked[-1][0], 'rating': ranked[-1][1]},
        }

    if roster_grade_data:
        ranked = sorted(
            ((d['name'], d.get('current_grade', 0)) for d in roster_grade_data.values()),
            key=lambda x: x[1], reverse=True
        )
        output_data['summary_statistics']['roster_grades'] = {
            'highest': {'manager': ranked[0][0], 'grade': ranked[0][1]},
            'lowest': {'manager': ranked[-1][0], 'grade': ranked[-1][1]},
        }

    storage.write_json(league_id, season, "fantasy_analysis.json", output_data)

    detailed_data = {
        'analysis_info': output_data['analysis_info'],
        'raw_trades': all_trades,
        'weekly_top_players': weekly_top_players,
        'matchup_results': matchup_results,
        'comprehensive_analysis': {
            'trade_impacts': trade_impacts,
            'waiver_impacts': waiver_impacts,
            'manager_grades': manager_grades,
        },
    }
    storage.write_json(league_id, season, "detailed_analysis.json", detailed_data)

    roster_data = {
        'analysis_info': output_data['analysis_info'],
        'managers': {
            user['user_id']: {
                'username': user.get('username', 'Unknown'),
                'display_name': user.get('display_name', 'Unknown'),
                'user_id': user['user_id'],
            } for user in users
        },
        'rosters': rosters,
        'roster_to_manager_mapping': roster_to_manager,
    }
    storage.write_json(league_id, season, "roster_data.json", roster_data)

    storage.write_meta(league_id, season, {
        'league_name': selected_league.get('name', 'Unknown'),
        'generated_at': datetime.now().isoformat(),
        'weeks_analyzed': sorted(all_weekly_matchups.keys()),
    })

    progress("Building AI overview...")
    try:
        ai_overview_html = build_ai_overview(
            output_data=output_data,
            detailed_data=detailed_data,
            roster_data=roster_data,
            league_settings=league_settings,
            faab_ledger=faab_ledger,
        )
        storage.write_html(league_id, season, "ai_overview.html", ai_overview_html)
    except Exception as e:
        progress(f"[WARNING] AI overview generation failed: {e}")

    try:
        draft_info_html = build_draft_info(output_data)
        storage.write_html(league_id, season, "draft_info.html", draft_info_html)
    except Exception as e:
        progress(f"[WARNING] Draft info generation failed: {e}")

    progress("Building hypothetical trade analyzer...")
    try:
        trade_analyzer_html = build_trade_analyzer(
            output_data, rosters, all_players, all_weekly_matchups, analyzer,
            roster_to_manager, user_lookup, faab_ledger, waiver_impacts,
        )
        storage.write_html(league_id, season, "trade_analyzer.html", trade_analyzer_html)
    except Exception as e:
        progress(f"[WARNING] Trade analyzer generation failed: {e}")

    progress("Building start/sit analyzer...")
    try:
        completed_week = _most_recent_completed_week(matchup_results)
        this_week = (completed_week + 1) if completed_week is not None else weeks_to_fetch[0]
        start_sit_html = build_start_sit_report(
            output_data, rosters, all_players, all_weekly_matchups, analyzer,
            roster_to_manager, user_lookup, schedule_by_week, this_week,
        )
        storage.write_html(league_id, season, "start_sit.html", start_sit_html)
    except Exception as e:
        progress(f"[WARNING] Start/sit analyzer generation failed: {e}")

    progress("Analysis complete!")
    return output_data


def main():
    """CLI entry point: resolve (username, season, league_id) from config file, env vars, or
    interactive prompts, then run the shared pipeline. Exits non-zero on failure so a
    scheduler/cron invocation can actually detect a failed run (the old version always
    exited 0, even on error).
    """
    print("Fantasy Football Comprehensive Analysis")
    print("=" * 50)

    sleeper_api = SleeperAPI()

    try:
        config = load_league_config()

        if config and config.get('auto_select'):
            username = config['sleeper_username']
            target_season = config.get('target_season')
            predetermined_league_id = config.get('league_id')
            print(f"Auto-mode: Using {username}'s league (ID: {predetermined_league_id})")
        else:
            username, target_season = get_user_input_interactive(sleeper_api)
            if not username:
                return
            predetermined_league_id = None

        if predetermined_league_id and target_season:
            league_id = predetermined_league_id
            season = int(target_season)
        else:
            user_id, leagues = get_user_leagues(sleeper_api, username, target_season)
            if not leagues:
                print("[ERROR] No leagues found")
                sys.exit(1)

            if predetermined_league_id:
                selected_league = next(
                    (l for l in leagues if l.get('league_id') == predetermined_league_id), None
                )
                if not selected_league:
                    print(f"[ERROR] League ID {predetermined_league_id} not found in your leagues!")
                    for i, league in enumerate(leagues, 1):
                        print(f"   {i}. {league.get('name', 'Unknown')} (ID: {league.get('league_id')})")
                    sys.exit(1)
            else:
                selected_league = select_league_interactive(leagues)
                if not selected_league:
                    return

            league_id = selected_league.get('league_id')
            season = selected_league.get('season')

        storage = AnalysisStorage()
        run_analysis(username, season, league_id, storage=storage)

        print("\n" + "=" * 60)
        print("Analysis complete! Check the generated HTML files for interactive visualizations.")

    except KeyboardInterrupt:
        print("\n[WARNING] Analysis interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        print("   Please check your league ID and network connection")
        sys.exit(1)


if __name__ == "__main__":
    main()
