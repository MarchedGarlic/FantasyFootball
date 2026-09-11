#!/usr/bin/env python3
"""
Power Rating Analysis Module
Calculates and tracks team performance over time using power rating formula
"""

import statistics
import os
from datetime import datetime
from typing import Dict, List

from src.bokeh_mobile import make_bokeh_html_mobile_friendly
from src.utils import get_manager_name


def calculate_power_rating(scores, wins, losses, week_num, combined_wins=None, combined_losses=None):
    """Calculate power rating using enhanced formula with optional combined record"""
    if not scores:
        return 0.0
    
    avg_score = statistics.mean(scores)
    high_score = max(scores)
    low_score = min(scores)
    
    # Use combined record if available, otherwise fall back to regular record
    if combined_wins is not None and combined_losses is not None:
        total_games = combined_wins + combined_losses
        win_percentage = combined_wins / total_games if total_games > 0 else 0
    else:
        total_games = wins + losses
        win_percentage = wins / total_games if total_games > 0 else 0
    
    # Enhanced power rating formula:
    # (average × 6 + (high + low) × 2 + (win% × 200) × 2) ÷ 10
    # This weighs average performance heavily, considers both ceiling and floor,
    # and factors in wins (scaled to ~20 point impact for undefeated teams)
    power_rating = (
        (avg_score * 6) + 
        ((high_score + low_score) * 2) + 
        ((win_percentage * 200) * 2)
    ) / 10
    
    return round(power_rating, 1)


def calculate_weekly_power_ratings(all_weekly_matchups, rosters, user_lookup, output_dirs=None):
    """Calculate power ratings for each team week by week"""
    print("Calculating weekly power rating progression...")
    
    # Initialize team data structure
    team_power_data = {}
    
    for roster in rosters:
        user_id = roster.get('owner_id')
        if user_id and user_id in user_lookup:
            user_name = get_manager_name(user_lookup, user_id, prefix="User")
            team_power_data[user_id] = {
                'name': user_name,
                'weekly_scores': {},
                'weekly_wins': {},
                'weekly_losses': {},
                'weekly_power_ratings': {},
                'cumulative_scores': {},
                'cumulative_wins': {},
                'cumulative_losses': {}
            }

    # Built once, instead of linearly scanning `rosters` for every matchup pairing below
    # (previously O(teams) per matchup, every week).
    roster_to_owner = {roster.get('roster_id'): roster.get('owner_id') for roster in rosters}

    # Running totals, updated incrementally as weeks are processed below instead of being
    # rebuilt by re-filtering the full history on every single week.
    running = {user_id: {'scores': [], 'wins': 0, 'losses': 0} for user_id in team_power_data}

    # Process each week's matchups, in real chronological order - all_weekly_matchups comes
    # from a concurrent bulk fetch (src/api_clients.py), so dict insertion order isn't
    # guaranteed to be week order, and the incremental running totals above depend on it being.
    for week, matchups in sorted(all_weekly_matchups.items()):
        if not matchups:
            continue
            
        print(f"   Processing Week {week}: {len(matchups)} teams")
        
        # Record this week's scores and determine wins/losses
        week_results = {}
        
        # Group by matchup_id to determine head-to-head results
        matchup_groups = {}
        for team in matchups:
            matchup_id = team.get('matchup_id')
            if matchup_id:
                if matchup_id not in matchup_groups:
                    matchup_groups[matchup_id] = []
                matchup_groups[matchup_id].append(team)
        
        # Process each head-to-head matchup
        for matchup_id, teams in matchup_groups.items():
            if len(teams) == 2:
                team1, team2 = teams
                team1_id = team1.get('roster_id')
                team2_id = team2.get('roster_id')
                team1_points = team1.get('points', 0) or 0
                team2_points = team2.get('points', 0) or 0
                
                # Find user_ids for these roster_ids
                team1_user_id = roster_to_owner.get(team1_id)
                team2_user_id = roster_to_owner.get(team2_id)

                if team1_user_id and team2_user_id:
                    # Record scores
                    week_results[team1_user_id] = {
                        'score': team1_points,
                        'win': team1_points > team2_points,
                        'loss': team1_points < team2_points
                    }
                    week_results[team2_user_id] = {
                        'score': team2_points,
                        'win': team2_points > team1_points,
                        'loss': team2_points < team1_points
                    }
        
        # Update cumulative data and calculate power ratings
        for user_id in team_power_data.keys():
            if user_id in week_results:
                # Add this week's data
                team_power_data[user_id]['weekly_scores'][week] = week_results[user_id]['score']
                team_power_data[user_id]['weekly_wins'][week] = 1 if week_results[user_id]['win'] else 0
                team_power_data[user_id]['weekly_losses'][week] = 1 if week_results[user_id]['loss'] else 0
                
                # Cumulative stats through this week, carried forward incrementally rather than
                # re-filtering every prior week's data from scratch each time.
                running[user_id]['scores'].append(week_results[user_id]['score'])
                running[user_id]['wins'] += 1 if week_results[user_id]['win'] else 0
                running[user_id]['losses'] += 1 if week_results[user_id]['loss'] else 0

                cumulative_scores = list(running[user_id]['scores'])
                cumulative_wins = running[user_id]['wins']
                cumulative_losses = running[user_id]['losses']
                
                team_power_data[user_id]['cumulative_scores'][week] = cumulative_scores
                team_power_data[user_id]['cumulative_wins'][week] = cumulative_wins
                team_power_data[user_id]['cumulative_losses'][week] = cumulative_losses
                
                # Calculate power rating through this week using combined records if available
                combined_wins = team_power_data[user_id].get('combined_record', {}).get('wins')
                combined_losses = team_power_data[user_id].get('combined_record', {}).get('losses')
                
                if combined_wins is not None and combined_losses is not None:
                    # Use combined record for power rating
                    power_rating = calculate_power_rating(cumulative_scores, cumulative_wins, cumulative_losses, week, combined_wins, combined_losses)
                else:
                    # Fall back to regular record
                    power_rating = calculate_power_rating(cumulative_scores, cumulative_wins, cumulative_losses, week)
                    
                team_power_data[user_id]['weekly_power_ratings'][week] = power_rating
    
    # Add summary statistics
    for user_id, data in team_power_data.items():
        if data['weekly_power_ratings']:
            latest_week = max(data['weekly_power_ratings'].keys())
            latest_rating = data['weekly_power_ratings'][latest_week]
            
            all_ratings = list(data['weekly_power_ratings'].values())
            data['current_rating'] = latest_rating
            data['average_rating'] = round(statistics.mean(all_ratings), 1) if all_ratings else 0
            data['rating_trend'] = 'improving' if len(all_ratings) >= 2 and all_ratings[-1] > all_ratings[0] else 'declining'
            data['highest_rating'] = max(all_ratings) if all_ratings else 0
            data['lowest_rating'] = min(all_ratings) if all_ratings else 0
            data['total_weeks'] = len(all_ratings)
    
    return team_power_data


def compute_power_rank_history(team_power_data):
    """Per-week power ranking position for every team.

    This used to be computed ad hoc inside create_power_rating_plot() purely to feed a Bokeh
    hover tooltip, then thrown away - never persisted, so nothing could build a "last week vs
    this week" ranking comparison from it. Extracted here so it can be saved to JSON and reused
    by the AI Overview's power-ranking-movers section.

    Returns {week: [{'user_id', 'rank', 'rating'}, ...]} sorted best (rank 1) to worst.
    """
    weeks = sorted({
        week for data in team_power_data.values()
        for week in data.get('weekly_power_ratings', {}).keys()
    })

    history = {}
    for week in weeks:
        week_ratings = [
            (user_id, data['weekly_power_ratings'][week])
            for user_id, data in team_power_data.items()
            if week in data.get('weekly_power_ratings', {})
        ]
        week_ratings.sort(key=lambda item: item[1], reverse=True)
        history[week] = [
            {'user_id': user_id, 'rank': idx + 1, 'rating': rating}
            for idx, (user_id, rating) in enumerate(week_ratings)
        ]

    return history


def create_power_rating_plot(team_power_data, output_dirs=None):
    """Create interactive Power Rating progression plot with toggleable trend lines"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS, LabelSet
        from bokeh.layouts import column, row
        import numpy as np
        from src.bokeh_theme import (
            style_figure, style_legend, legend_toggle_button, button_stylesheet, dark_palette,
            SURFACE, SURFACE_RAISED, LINE, INK, INK_MUTED, ACCENT,
            PANEL_STYLE, HEADING_STYLE, DESCRIPTION_STYLE, collapsible_description_html,
        )
    except ImportError:
        print("\n⚠️  Bokeh not available - install with: pip install bokeh")
        print("   Falling back to text-only Power Rating analysis...")
        _create_power_rating_text_analysis(team_power_data)
        return
        
    try:
        # Try to import sklearn for trend lines, but make it optional
        try:
            from sklearn.linear_model import LinearRegression
            sklearn_available = True
        except ImportError:
            sklearn_available = False
            print("   Note: scikit-learn not available for trend lines")
        
        # Dark-optimized categorical palette (Bokeh's Category20 is tuned for a white
        # background - several of its hues are nearly invisible against this app's navy void)
        colors = dark_palette(len(team_power_data))
        
        # Prepare data for interactive plot
        team_data = []

        # Computed once for the whole league instead of being re-sorted/re-scanned per team per
        # week below - see compute_power_rank_history()'s own docstring for why this exists.
        rank_by_week = {
            week: {entry['user_id']: entry['rank'] for entry in entries}
            for week, entries in compute_power_rank_history(team_power_data).items()
        }

        for i, (user_id, data) in enumerate(team_power_data.items()):
            if not data['weekly_power_ratings']:
                continue
                
            weeks = sorted(data['weekly_power_ratings'].keys())
            ratings = [data['weekly_power_ratings'][week] for week in weeks]
            
            if len(ratings) < 3:  # Need at least 3 data points
                continue
            
            # Add small jitter to prevent overlapping points
            jitter_amount = 0.1
            jittered_weeks = [w + np.random.uniform(-jitter_amount, jitter_amount) for w in weeks]
            
            # Calculate additional hover data
            wins_data = []
            losses_data = []
            avg_scores = []
            high_scores = []
            low_scores = []
            regular_records = []
            median_records = []
            combined_records = []
            power_ranking_spots = []
            
            # Real per-week median result ('W'/'L' vs the league median score that week),
            # already computed correctly by median_record_calculator.py and merged into
            # team_power_data by main.py - used below instead of the fabricated
            # "median_wins = min(cumulative_wins + 1, week)" placeholder this chart's hover
            # data used to show, which had nothing to do with actually beating the median (a
            # leftover "rough estimate" that was never replaced once the real median calculation
            # existed - confirmed against real data: it doesn't move in step with the real
            # median_wins figure the AI Overview's Median Standings section reports for the same
            # manager/week).
            weekly_median_results = data.get('weekly_median_results', {})
            running_median_wins = 0
            running_median_losses = 0

            for week in weeks:
                cumulative_scores = data['cumulative_scores'].get(week, [])
                cumulative_wins = data['cumulative_wins'].get(week, 0)
                cumulative_losses = data['cumulative_losses'].get(week, 0)

                wins_data.append(cumulative_wins)
                losses_data.append(cumulative_losses)

                # Calculate regular record (just wins-losses)
                regular_records.append(f"{cumulative_wins}-{cumulative_losses}")

                if cumulative_scores:
                    avg_scores.append(round(sum(cumulative_scores) / len(cumulative_scores), 1))
                    high_scores.append(max(cumulative_scores))
                    low_scores.append(min(cumulative_scores))
                else:
                    avg_scores.append(0)
                    high_scores.append(0)
                    low_scores.append(0)

                # Cumulative median record, built from the real per-week result - not tied to
                # cumulative_scores being present, since a manager can have a real median result
                # for a week even if their score list for that exact week was empty upstream.
                median_result = weekly_median_results.get(week, weekly_median_results.get(str(week)))
                if median_result == 'W':
                    running_median_wins += 1
                elif median_result == 'L':
                    running_median_losses += 1
                median_records.append(f"{running_median_wins}-{running_median_losses}")

                combined_wins = cumulative_wins + running_median_wins
                combined_losses = cumulative_losses + running_median_losses
                combined_records.append(f"{combined_wins}-{combined_losses}")
            
            # This team's rank each week, looked up from the league-wide rank_by_week computed
            # once above instead of being re-derived per team.
            power_ranking_spots = [rank_by_week.get(week, {}).get(user_id, 0) for week in weeks]
            
            # Calculate trend line if sklearn available
            slope = 0
            trend_weeks = []
            trend_ratings = []
            
            if sklearn_available and len(weeks) >= 3:
                X = np.array(weeks).reshape(-1, 1)
                y = np.array(ratings)
                
                model = LinearRegression()
                model.fit(X, y)
                slope = model.coef_[0]
                
                # Generate trend line points
                trend_weeks = list(range(min(weeks), max(weeks) + 1))
                trend_ratings = model.predict(np.array(trend_weeks).reshape(-1, 1)).tolist()
            
            team_data.append({
                'name': data['name'],
                'color': colors[i % len(colors)],
                'slope': slope,
                'current_rating': ratings[-1] if ratings else 0,  # Latest rating
                'record': regular_records[-1] if regular_records else "0-0",  # Latest record
                'avg_score': avg_scores[-1] if avg_scores else 0,  # Latest average score
                'source': ColumnDataSource(data={
                    'week': jittered_weeks,
                    'rating': ratings,
                    'team': [data['name']] * len(ratings),
                    'original_week': weeks,
                    'original_rating': ratings,
                    'wins': wins_data,
                    'losses': losses_data,
                    'avg_points': avg_scores,
                    'high_score': high_scores,
                    'low_score': low_scores,
                    'regular_record': regular_records,
                    'median_record': median_records,
                    'combined_record': combined_records,
                    'power_ranking_spot': power_ranking_spots
                }),
                'trend_source': ColumnDataSource(data={
                    'trend_week': trend_weeks,
                    'trend_rating': trend_ratings,
                    'team_name': [data['name']] * len(trend_weeks),
                    'slope': [slope] * len(trend_weeks)
                }) if sklearn_available else None
            })
        
        # Only create plots if we have data
        if len(team_data) == 0:
            print("   • No power rating data available")
            return

        # Real per-league week range, not a hardcoded "assume 15 weeks" guess (the exact bug
        # class CLAUDE.md section 3.3 documents as fixed elsewhere in the pipeline).
        all_weeks_seen = sorted({
            week for data in team_power_data.values()
            for week in data.get('weekly_power_ratings', {})
        })
        last_week = all_weeks_seen[-1] if all_weeks_seen else 15

        # Create the interactive figure
        if output_dirs:
            plot_filename = os.path.join(output_dirs['html'], "power_rating_interactive.html")
        else:
            plot_filename = "power_rating_interactive.html"
        output_file(plot_filename)
        
        # Set up the figure with tools
        p = figure(
            width=1100,
            height=700,
            sizing_mode="stretch_width",
            title="Power Rating Progression",
            x_axis_label="Week",
            y_axis_label="Power Rating",
            tools="pan,wheel_zoom,box_zoom,reset,save",
            x_range=(0.5, last_week + 0.5)
        )
        style_figure(p)

        # Explanation panel: larger, higher-contrast description text sits directly under the
        # heading (explicit user request - "make the description larger, in a different place"),
        # dark-themed to match the rest of the app.
        from bokeh.models import Div
        explanation_text = f"""
        <div style="{PANEL_STYLE}">
            <h3 style="{HEADING_STYLE}">How Power Rating Works</h3>
            {collapsible_description_html(
                short_html=f'<p style="{DESCRIPTION_STYLE}">Blends scoring average, high/low range, and win percentage into one number - higher means a stronger overall team.</p>',
                full_extra_html=f'''
                <p style="{DESCRIPTION_STYLE} margin-top: 8px;">
                    The exact formula: <code style="color:{ACCENT};">(avg&times;6 + (high+low)&times;2 + (win%&times;200)&times;2) &divide; 10</code>.
                    Dashed lines are each team's trend (linear regression over the season). Click a
                    name in the legend to hide or show just that team, or use the buttons below to
                    toggle everyone at once.
                </p>
                <p style="{DESCRIPTION_STYLE} margin-top: 8px;">
                    <strong style="color:{ACCENT};">What this means:</strong> the team on top of this
                    chart is playing the best fantasy football overall - not just winning, but doing
                    it with a strong scoring average and floor. A team with a losing record but a
                    high power rating has been getting unlucky and is likely to turn it around; the
                    reverse (a winning record, low rating) is a team living on the edge.
                </p>
                ''',
                toggle_id="power-rating-expl",
            )}
        </div>
        """

        explanation_div = Div(text=explanation_text, sizing_mode="stretch_width", max_width=1100, height_policy="auto")
        
        # Add hover tool with detailed tooltips
        hover = HoverTool(tooltips=[
            ("Team", "@team"),
            ("Week", "@original_week"),
            ("Power Rating", "@original_rating{0.1f}"),
            ("Power Ranking Spot", "@power_ranking_spot"),
            ("Regular Record", "@regular_record"),
            ("Median Record", "@median_record"),
            ("Combined Record", "@combined_record"),
            ("Average Points", "@avg_points{0.1f}"),
            ("High Score", "@high_score{0.1f}"),
            ("Low Score", "@low_score{0.1f}")
        ])
        p.add_tools(hover)
        
        # Create separate hover for trend lines
        if sklearn_available:
            trend_hover = HoverTool(tooltips=[
                ("Team", "@team_name"),
                ("Trend Slope", "@slope{0.2f} pts/week"),
                ("Week", "@trend_week"),
                ("Projected Rating", "@trend_rating{0.1f}")
            ], renderers=[])
            p.add_tools(trend_hover)
        
        # Create legend items for both actual data and trend lines
        data_legend_items = []
        trend_legend_items = []
        
        # Add each team's data to the plot
        for i, team in enumerate(team_data):
            # Plot the data points
            scatter_renderer = p.scatter(
                x='week', y='rating',
                source=team['source'],
                color=team['color'],
                size=8,
                alpha=0.8,
                line_color='white',
                line_width=1
            )
            
            # Plot the connection lines between actual data points
            line_renderer = p.line(
                x='week', y='rating',
                source=team['source'],
                line_color=team['color'],
                line_width=2,
                line_alpha=0.7
            )
            
            # Plot the trend line if available
            trend_renderer = None
            if sklearn_available and team['trend_source']:
                trend_direction = "↗" if team['slope'] > 0.5 else "↘" if team['slope'] < -0.5 else "→"
                trend_renderer = p.line(
                    x='trend_week', y='trend_rating',
                    source=team['trend_source'],
                    line_color=team['color'],
                    line_width=3,
                    line_alpha=0.6,
                    line_dash='dashed'
                )
                
                # Add this renderer to the trend hover tool
                if 'trend_hover' in locals():
                    trend_hover.renderers.append(trend_renderer)
                
                # Add to trend legend
                trend_legend_items.append((f"{team['name']} Trend {trend_direction} ({team['slope']:+.1f}/wk)", [trend_renderer]))

            # Team name next to its most recent point only - labeling every week's point on an
            # 18-week, 12-team chart would be unreadable, but a name at the end of each line
            # gives an at-a-glance "current standings" read without relying on hover/legend.
            # Small fixed font size since Bokeh has no media-query equivalent to shrink it on
            # narrow screens - kept unobtrusive at any width instead. Always visible regardless
            # of legend toggle state - Bokeh's Legend only accepts GlyphRenderers in an item's
            # renderer list, so a LabelSet (an Annotation, not a GlyphRenderer) can't be wired
            # to hide/show together with its line via the native click-to-hide legend.
            last_point_source = ColumnDataSource(data={
                'week': [team['source'].data['week'][-1]],
                'rating': [team['source'].data['rating'][-1]],
                'name': [team['name']],
            })
            # Anchored to the right of the label (x_offset negative, text_align right) so the
            # text extends back toward the chart instead of off its right edge, where the
            # season's final week - and therefore every one of these labels - sits. y_offset
            # cycles per team since every label shares that same final week and would otherwise
            # stack on top of each other for teams with a similar current rating.
            p.add_layout(LabelSet(
                x='week', y='rating', text='name', source=last_point_source,
                x_offset=-8, y_offset=[8, -20, 18, -32][i % 4], text_align='right',
                text_font_size='9px', text_color=team['color'],
                background_fill_color=SURFACE, background_fill_alpha=0.65,
            ))

            # Add to data legend
            data_legend_items.append((f"{team['name']}", [scatter_renderer, line_renderer]))
        
        # Create two separate legends with click policies
        # Legends render *inside* the plot frame (not as an outside 'right' panel) - a side
        # panel adds its own fixed pixel width alongside the frame, which sizing_mode
        # "stretch_width" can't compensate for, so the whole figure ends up wider than a phone
        # viewport. Inside placement (with a translucent background from style_legend so it
        # doesn't fully hide data underneath) keeps the figure's real width capped at whatever
        # stretch_width actually gives it.
        data_legend = Legend(items=data_legend_items, location="top_left", title="Teams", click_policy="hide")
        data_legend.title_text_font_size = "10pt"
        data_legend.label_text_font_size = "9pt"
        style_legend(data_legend)
        p.add_layout(data_legend)

        if sklearn_available and trend_legend_items:
            trend_legend = Legend(items=trend_legend_items, location="bottom_right", title="Trends", click_policy="hide")
            trend_legend.title_text_font_size = "10pt"
            trend_legend.label_text_font_size = "9pt"
            style_legend(trend_legend)
            p.add_layout(trend_legend)
            show_legend_button = legend_toggle_button(data_legend, trend_legend)
        else:
            show_legend_button = legend_toggle_button(data_legend)

        # Create toggle buttons
        toggle_data_button = Button(label="Toggle All Teams", sizing_mode="stretch_width", height=44,
                                     stylesheets=[button_stylesheet("primary")])
        toggle_trends_button = Button(label="Toggle All Trends", sizing_mode="stretch_width", height=44,
                                       stylesheets=[button_stylesheet("ghost")])
        
        # JavaScript callbacks for toggle buttons
        toggle_data_callback = CustomJS(
            args=dict(data_legend=data_legend),
            code="""
            let any_visible = false;
            for (let i = 0; i < data_legend.items.length; i++) {
                for (let j = 0; j < data_legend.items[i].renderers.length; j++) {
                    if (data_legend.items[i].renderers[j].visible) {
                        any_visible = true;
                        break;
                    }
                }
                if (any_visible) break;
            }
            
            for (let i = 0; i < data_legend.items.length; i++) {
                let current_visible = data_legend.items[i].renderers[0].visible;
                let should_toggle = (any_visible && current_visible) || (!any_visible && !current_visible);
                
                if (should_toggle) {
                    data_legend.items[i].renderers.forEach(function(renderer) {
                        renderer.visible = !current_visible;
                    });
                }
            }
            """
        )
        
        if sklearn_available and trend_legend_items:
            toggle_trends_callback = CustomJS(
                args=dict(trend_legend=trend_legend),
                code="""
                let any_visible = false;
                for (let i = 0; i < trend_legend.items.length; i++) {
                    for (let j = 0; j < trend_legend.items[i].renderers.length; j++) {
                        if (trend_legend.items[i].renderers[j].visible) {
                            any_visible = true;
                            break;
                        }
                    }
                    if (any_visible) break;
                }
                
                for (let i = 0; i < trend_legend.items.length; i++) {
                    let current_visible = trend_legend.items[i].renderers[0].visible;
                    let should_toggle = (any_visible && current_visible) || (!any_visible && !current_visible);
                    
                    if (should_toggle) {
                        trend_legend.items[i].renderers.forEach(function(renderer) {
                            renderer.visible = !current_visible;
                        });
                    }
                }
                """
            )
            
            toggle_trends_button.js_on_event('button_click', toggle_trends_callback)
        
        toggle_data_button.js_on_event('button_click', toggle_data_callback)
        
        # Style the plot title (grid/axis colors already set by style_figure())
        p.title.text_font_size = "15pt"
        p.xaxis.axis_label_text_font_size = "12pt"
        p.yaxis.axis_label_text_font_size = "12pt"

        # Create leaderboard HTML
        leaderboard_html = f"<h3 style='{HEADING_STYLE}'>Power Rankings Leaderboard</h3>"
        leaderboard_html += f"<table style='border-collapse: collapse; width: 100%; font-size: 13px; color: {INK};'>"
        leaderboard_html += f"<tr style='background-color: {SURFACE_RAISED};'>"
        leaderboard_html += f"<th style='border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};'>Rank</th>"
        leaderboard_html += f"<th style='border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};'>Team</th>"
        leaderboard_html += f"<th style='border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};'>Current Rating</th>"
        leaderboard_html += f"<th style='border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};'>Record</th>"
        leaderboard_html += f"<th style='border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};'>Avg Score</th>"
        leaderboard_html += f"<th style='border-bottom: 1px solid {LINE}; padding: 9px 8px; text-align: left; color: {INK_MUTED};'>Trend</th>"
        leaderboard_html += "</tr>"

        # Sort teams by current power rating for leaderboard
        sorted_for_leaderboard = sorted(team_data, key=lambda x: x['current_rating'], reverse=True)

        for i, team in enumerate(sorted_for_leaderboard):
            rank_display = f"#{i+1}"
            row_bg = SURFACE if i % 2 == 0 else "transparent"
            trend_color = "#34D399" if team['slope'] > 0.5 else "#F87171" if team['slope'] < -0.5 else INK_MUTED
            trend_text = f"{team['slope']:+.1f}/wk"

            leaderboard_html += f"<tr style='background-color: {row_bg};'>"
            leaderboard_html += f"<td style='border-bottom: 1px solid {LINE}; padding: 9px 8px; font-weight: 700; color: {ACCENT if i < 3 else INK};'>{rank_display}</td>"
            leaderboard_html += f"<td style='border-bottom: 1px solid {LINE}; padding: 9px 8px;'>{team['name']}</td>"
            leaderboard_html += f"<td style='border-bottom: 1px solid {LINE}; padding: 9px 8px; font-weight: 700;'>{team['current_rating']:.1f}</td>"
            leaderboard_html += f"<td style='border-bottom: 1px solid {LINE}; padding: 9px 8px; color: {INK_MUTED};'>{team['record']}</td>"
            leaderboard_html += f"<td style='border-bottom: 1px solid {LINE}; padding: 9px 8px; color: {INK_MUTED};'>{team['avg_score']:.1f}</td>"
            leaderboard_html += f"<td style='border-bottom: 1px solid {LINE}; padding: 9px 8px; color: {trend_color}; font-weight: 600;'>{trend_text}</td>"
            leaderboard_html += "</tr>"

        leaderboard_html += "</table>"
        leaderboard_html += f"<p style='font-size: 11px; color: {INK_MUTED}; margin-top: 10px;'>"
        leaderboard_html += "Current Rating = latest week's power rating &middot; "
        leaderboard_html += "Trend = weekly rating change direction and slope"
        leaderboard_html += "</p>"
        
        # Wrapped in the leaderboard's own HTML (not an external stylesheet) because Bokeh 3.x
        # renders every Div inside a shadow root that external CSS can't reach - see
        # src/bokeh_mobile.py's module docstring for how this was confirmed empirically. Width is
        # `100vw`, not `100%`: the wrapper's real parent (Bokeh's own `.bk-clearfix`, also inside
        # the shadow root) is `display: inline-block` and shrinks to fit its content, so a
        # percentage width has no real containing block to resolve against and just falls back to
        # the table's own natural (too-wide) size - confirmed by measuring the actual rendered
        # boxes. Viewport units don't have that circularity, and since this Div always ends up
        # spanning the full stacked-column width (see the row-to-column fix above), the viewport
        # width is the right proxy for "however much horizontal room this report actually has".
        leaderboard_div = Div(
            text=f'<div style="display:block;width:100vw;overflow-x:auto;-webkit-overflow-scrolling:touch;background-color:{SURFACE};border:1px solid {LINE};border-radius:16px;padding:16px 18px;box-sizing:border-box;">{leaderboard_html}</div>',
            sizing_mode="stretch_width", max_width=450, height=500
        )

        # Create layout with controls. 2-per-row grid, not one long row - Bokeh's row() has no
        # flex-wrap, so 3 buttons in one stretch_width row overlap rather than wrap on a narrow
        # phone screen (see the button-overlap fix elsewhere in this codebase for the same issue).
        if sklearn_available and trend_legend_items:
            controls = column(
                row(toggle_data_button, toggle_trends_button, sizing_mode="stretch_width"),
                row(show_legend_button, sizing_mode="stretch_width"),
                sizing_mode="stretch_width",
            )
        else:
            controls = row(toggle_data_button, show_legend_button, sizing_mode="stretch_width")

        # Chart and leaderboard stack vertically rather than sitting side by side - a fixed-width
        # row of a 1100px chart + 450px leaderboard has no way to fit a 375-414px phone screen,
        # and Bokeh has no CSS-media-query-driven "become a column below this width" behavior to
        # lean on instead (confirmed: Bokeh's internal grid/flex layout classes differ across
        # versions, so overriding them from outside is fragile - stacking unconditionally is the
        # version-independent fix). See src/bokeh_mobile.py's docstring for the same reasoning
        # applied to trade_analysis.py/visualizations.py. Controls now sit right under the
        # description, above the chart - explicit user request to relocate the built-in buttons
        # instead of leaving them buried at the very bottom of the page.
        main_content = column(p, leaderboard_div, sizing_mode="stretch_width")
        layout = column(explanation_div, controls, main_content, sizing_mode="stretch_width")

        # Show the interactive plot
        show(layout)
        make_bokeh_html_mobile_friendly(plot_filename)

        print(f"\nInteractive Power Rating plot saved as: {plot_filename}")
        print("\nInteractive Features:")
        print("   • 'All Teams' button: Show/hide all team power rating lines")
        if sklearn_available and trend_legend_items:
            print("   • 'All Trends' button: Show/hide all trend lines")
        print("   • Left Legend: Click team names to hide/show individual lines")
        if sklearn_available and trend_legend_items:
            print("   • Right Legend: Click trend items to hide/show individual trends")
        print("   • Hover over points for detailed information")
        print("   • Pan and zoom to explore the data")
        
        print("\nPower Rating Analysis:")
        print("   • Formula: (avg×6 + (high+low)×2 + (win%×200)×2) ÷ 10")
        print("   • Emphasizes consistent performance with win bonus")
        print("   • Points show cumulative performance through each week")
        if sklearn_available:
            print("   • Trend lines show overall trajectory direction")
        print("   • Higher ratings indicate stronger overall team performance")
        
    except Exception as e:
        print(f"\n❌ Error creating Power Rating plot: {e}")
        print("   Falling back to text-only analysis...")
        _create_power_rating_text_analysis(team_power_data)


def _create_power_rating_text_analysis(team_power_data):
    """Fallback text analysis for power ratings"""
    print("\nPower Rating Analysis (Text Format):")
    print(f"{'Team':<18} {'Current':<8} {'Average':<8} {'Trend':<10} {'High':<6} {'Low':<6}")
    print("-" * 65)
    
    # Sort teams by current rating
    sorted_teams = sorted(team_power_data.items(), 
                         key=lambda x: x[1].get('current_rating', 0), reverse=True)
    
    for user_id, data in sorted_teams:
        if not data.get('weekly_power_ratings'):
            continue
            
        current = data.get('current_rating', 0)
        average = data.get('average_rating', 0)
        trend = data.get('rating_trend', 'stable')
        high = data.get('highest_rating', 0)
        low = data.get('lowest_rating', 0)
        
        trend_icon = "📈" if trend == 'improving' else "📉" if trend == 'declining' else "➡️"
        
        print(f"{data['name'][:17]:<18} {current:<8.1f} {average:<8.1f} {trend_icon} {trend:<7} {high:<6.1f} {low:<6.1f}")