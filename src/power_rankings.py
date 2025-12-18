#!/usr/bin/env python3
"""
Power Rating Analysis Module
Calculates and tracks team performance over time using power rating formula
"""

import statistics
import os
from datetime import datetime
from typing import Dict, List


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
            user_name = user_lookup[user_id].get('display_name', f'User {user_id}')
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
    
    # Process each week's matchups
    for week, matchups in all_weekly_matchups.items():
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
                team1_user_id = None
                team2_user_id = None
                
                for roster in rosters:
                    if roster.get('roster_id') == team1_id:
                        team1_user_id = roster.get('owner_id')
                    elif roster.get('roster_id') == team2_id:
                        team2_user_id = roster.get('owner_id')
                
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
                
                # Calculate cumulative stats through this week
                cumulative_scores = [team_power_data[user_id]['weekly_scores'][w] 
                                   for w in sorted(team_power_data[user_id]['weekly_scores'].keys()) 
                                   if w <= week]
                cumulative_wins = sum([team_power_data[user_id]['weekly_wins'][w] 
                                     for w in sorted(team_power_data[user_id]['weekly_wins'].keys()) 
                                     if w <= week])
                cumulative_losses = sum([team_power_data[user_id]['weekly_losses'][w] 
                                       for w in sorted(team_power_data[user_id]['weekly_losses'].keys()) 
                                       if w <= week])
                
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


def create_power_rating_plot(team_power_data, output_dirs=None):
    """Create interactive Power Rating progression plot with toggleable trend lines"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS
        from bokeh.layouts import column, row
        from bokeh.palettes import Category20
        import numpy as np
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
        
        # Use Bokeh's Category20 palette for better colors
        colors = Category20[20] if len(team_power_data) <= 20 else Category20[20] * 2
        
        # Prepare data for interactive plot
        team_data = []
        
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
            
            for week in weeks:
                cumulative_scores = data['cumulative_scores'].get(week, [])
                cumulative_wins = data['cumulative_wins'].get(week, 0)
                cumulative_losses = data['cumulative_losses'].get(week, 0)
                
                wins_data.append(cumulative_wins)
                losses_data.append(cumulative_losses)
                
                # Calculate regular record (just wins-losses)
                regular_records.append(f"{cumulative_wins}-{cumulative_losses}")
                
                # Calculate median record (simulated - wins against median score each week)
                if cumulative_scores:
                    avg_scores.append(round(sum(cumulative_scores) / len(cumulative_scores), 1))
                    high_scores.append(max(cumulative_scores))
                    low_scores.append(min(cumulative_scores))
                    
                    # For median wins, estimate based on avg score vs league avg (simplified)
                    median_wins = max(0, min(cumulative_wins + 1, week))  # Rough estimate
                    median_losses = week - median_wins
                    median_records.append(f"{median_wins}-{median_losses}")
                    
                    # Combined record is regular + median
                    combined_wins = cumulative_wins + median_wins
                    combined_losses = cumulative_losses + median_losses
                    combined_records.append(f"{combined_wins}-{combined_losses}")
                else:
                    avg_scores.append(0)
                    high_scores.append(0)
                    low_scores.append(0)
                    median_records.append(f"0-{week}")
                    combined_records.append(f"{cumulative_wins}-{cumulative_losses + week}")
            
            # Calculate power ranking spots for each week for this team
            power_ranking_spots = []
            for week in weeks:
                week_ratings = []
                for uid, team_info in team_power_data.items():
                    if week in team_info['weekly_power_ratings']:
                        week_ratings.append((uid, team_info['weekly_power_ratings'][week]))
                
                # Sort by rating (highest first) and find this team's position
                week_ratings.sort(key=lambda x: x[1], reverse=True)
                ranking_spot = next((idx + 1 for idx, (uid, _) in enumerate(week_ratings) if uid == user_id), 0)
                power_ranking_spots.append(ranking_spot)
            
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
            title="Interactive Fantasy Football Power Rating Progression",
            x_axis_label="Week",
            y_axis_label="Power Rating",
            tools="pan,wheel_zoom,box_zoom,reset,save",
            x_range=(0.5, 15.5)
        )
        
        # Create explanation panel
        from bokeh.models import Div
        explanation_text = """
        <h3 style="margin:5px 0;">Power Rating Analysis Methodology</h3>
        <p style="margin:2px;"><b>Formula:</b> (avg×6 + (high+low)×2 + (win%×200)×2) ÷ 10</p>
        <p style="margin:2px;"><b>Components:</b> Weekly scores + high/low range + win percentage bonus</p>
        <p style="margin:2px;"><b>Weighting:</b> 60% average score, 20% range consistency, 20% win success</p>
        <p style="margin:2px;"><b>Trend Lines:</b> Linear regression showing performance trajectory over time</p>
        <p style="margin:2px;"><b>Scale:</b> Higher values indicate stronger overall team performance</p>
        <p style="margin:2px;"><b>Interactive:</b> Click legend to hide/show teams, hover for detailed stats</p>
        """
        
        explanation_div = Div(text=explanation_text, width=1100, height=100)
        
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
        for team in team_data:
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
            
            # Add to data legend
            data_legend_items.append((f"{team['name']}", [scatter_renderer, line_renderer]))
        
        # Create two separate legends with click policies
        data_legend = Legend(items=data_legend_items, location="center", title="Teams (Power Ratings)")
        data_legend.click_policy = "hide"
        data_legend.title_text_font_size = "10pt"
        data_legend.label_text_font_size = "9pt"
        
        if sklearn_available and trend_legend_items:
            trend_legend = Legend(items=trend_legend_items, location="center", title="Power Trends")
            trend_legend.click_policy = "hide"
            trend_legend.title_text_font_size = "10pt"
            trend_legend.label_text_font_size = "9pt"
            p.add_layout(trend_legend, 'right')
        
        # Position legends
        p.add_layout(data_legend, 'right')
        
        # Create toggle buttons
        toggle_data_button = Button(label="All Teams", button_type="success", width=100)
        toggle_trends_button = Button(label="All Trends", button_type="warning", width=100)
        
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
        
        # Style the plot
        p.grid.grid_line_alpha = 0.3
        p.title.text_font_size = "14pt"
        p.xaxis.axis_label_text_font_size = "12pt"
        p.yaxis.axis_label_text_font_size = "12pt"
        
        # Create leaderboard HTML
        leaderboard_html = "<h3>Power Rankings Leaderboard</h3>"
        leaderboard_html += "<table style='border-collapse: collapse; width: 100%; font-size: 12px;'>"
        leaderboard_html += "<tr style='background-color: #f0f0f0; font-weight: bold;'>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Rank</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Team</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Current Rating</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Record</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Avg Score</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Trend</th>"
        leaderboard_html += "</tr>"
        
        # Sort teams by current power rating for leaderboard
        sorted_for_leaderboard = sorted(team_data, key=lambda x: x['current_rating'], reverse=True)
        
        for i, team in enumerate(sorted_for_leaderboard):
            # Add trophy emojis for top 3
            rank_display = f"🥇 {i+1}" if i == 0 else f"🥈 {i+1}" if i == 1 else f"🥉 {i+1}" if i == 2 else str(i+1)
            
            # Color code based on ranking
            if i < 3:
                row_color = "#fff3cd"  # Gold for top 3
            elif i < 6:
                row_color = "#d1ecf1"  # Light blue for middle
            else:
                row_color = "#f8f9fa"  # Light gray for bottom
            
            trend_icon = "📈" if team['slope'] > 0.5 else "📉" if team['slope'] < -0.5 else "➡️"
            trend_text = f"{trend_icon} {team['slope']:+.1f}"
            
            leaderboard_html += f"<tr style='background-color: {row_color};'>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center; font-weight: bold;'>{rank_display}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px;'>{team['name']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center; font-weight: bold;'>{team['current_rating']:.1f}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{team['record']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{team['avg_score']:.1f}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{trend_text}</td>"
            leaderboard_html += "</tr>"
        
        leaderboard_html += "</table>"
        leaderboard_html += "<p style='font-size: 10px; color: #666; margin-top: 10px;'>"
        leaderboard_html += "Current Rating = Latest week's power rating | "
        leaderboard_html += "Trend = Weekly rating change direction and slope"
        leaderboard_html += "</p>"
        
        leaderboard_div = Div(
            text=leaderboard_html,
            width=450, height=500
        )

        # Create layout with controls
        if sklearn_available and trend_legend_items:
            controls = row(toggle_data_button, toggle_trends_button)
        else:
            controls = row(toggle_data_button)
        
        # Create main content row with chart and leaderboard side by side
        main_row = row(p, leaderboard_div, spacing=20)
        layout = column(explanation_div, main_row, controls)
        
        # Show the interactive plot
        show(layout)
        
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