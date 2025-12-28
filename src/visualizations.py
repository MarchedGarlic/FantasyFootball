#!/usr/bin/env python3
"""
Visualization Module
Creates interactive Bokeh plots for fantasy football analysis
"""

import statistics
import os
from datetime import datetime
from typing import Dict, List


def create_roster_grade_plot(roster_grade_data, output_dirs=None, team_power_data=None):
    """Create enhanced interactive Roster Grade progression plot with leaderboard and working toggles"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS, CheckboxGroup
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from bokeh.palettes import Category20, Category10
        from bokeh.models import Div
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh not available - install with: pip install bokeh")
        print("   Falling back to text-only Roster Grade analysis...")
        _create_roster_grade_text_analysis(roster_grade_data)
        return
    
    try:
        # Try to import sklearn for trend lines, but make it optional
        try:
            from sklearn.linear_model import LinearRegression
            sklearn_available = True
        except ImportError:
            sklearn_available = False
            print("   Note: scikit-learn not available for trend lines")
            
        # Use Bokeh's Category20 palette for consistent colors
        colors = Category20[20] if len(roster_grade_data) <= 20 else Category20[20] * 2
        
        # Prepare data for interactive plot and calculate current standings
        team_data = []
        leaderboard_data = []
        
        for i, (user_id, data) in enumerate(roster_grade_data.items()):
            weekly_data = data.get('weekly_roster_grades') or data.get('weekly_grades')
            if not weekly_data:
                continue
                
            weeks = sorted([int(w) for w in weekly_data.keys()])
            grades = [weekly_data.get(str(week), weekly_data.get(week, 0)) for week in weeks]
            
            if len(grades) < 2:  # Need at least 2 data points
                continue
            
            # Calculate current roster grade (latest week)
            current_grade = data.get('current_grade', grades[-1] if grades else 0)
            average_grade = data.get('average_grade', sum(grades) / len(grades) if grades else 0)
            high_grade = data.get('highest_grade', max(grades) if grades else 0)
            low_grade = data.get('lowest_grade', min(grades) if grades else 0)
            
            # Add small jitter to prevent overlapping points
            jitter_amount = 0.1
            jittered_weeks = [w + np.random.uniform(-jitter_amount, jitter_amount) for w in weeks]
            
            # Calculate trend line if sklearn available
            slope = 0
            trend_weeks = []
            trend_grades = []
            
            if sklearn_available and len(weeks) >= 3:
                X = np.array(weeks).reshape(-1, 1)
                y = np.array(grades)
                
                model = LinearRegression()
                model.fit(X, y)
                slope = model.coef_[0]
                
                # Generate trend line points extending to week 15
                trend_weeks = list(range(min(weeks), 16))
                trend_grades = model.predict(np.array(trend_weeks).reshape(-1, 1)).tolist()
            
            # Get real record data from team_power_data if available
            regular_records = []
            combined_records = []
            
            if team_power_data and user_id in team_power_data:
                power_data = team_power_data[user_id]
                for week in weeks:
                    cumulative_wins = power_data.get('cumulative_wins', {}).get(week, 0)
                    cumulative_losses = power_data.get('cumulative_losses', {}).get(week, 0)
                    regular_records.append(f"{cumulative_wins}-{cumulative_losses}")
                    
                    # Use combined record if available, otherwise fall back to regular
                    combined_record = power_data.get('combined_record', {})
                    if combined_record:
                        combined_wins = combined_record.get('wins', cumulative_wins)
                        combined_losses = combined_record.get('losses', cumulative_losses)
                        combined_records.append(f"{combined_wins}-{combined_losses}")
                    else:
                        combined_records.append(f"{cumulative_wins}-{cumulative_losses}")
            else:
                # Fallback to placeholder records
                for j, week in enumerate(weeks):
                    regular_records.append(f"{j+1}-0")
                    combined_records.append(f"{j+1}-0")
            
            team_data.append({
                'name': data.get('name', data.get('manager_name', f'Manager {i+1}')),
                'color': colors[i % len(colors)],
                'slope': slope,
                'current_grade': current_grade,
                'average_grade': average_grade,
                'source': ColumnDataSource(data={
                    'week': jittered_weeks,
                    'grade': grades,
                    'team': [data.get('name', data.get('manager_name', f'Manager {i+1}'))] * len(grades),
                    'original_week': weeks,
                    'original_grade': grades,
                    'avg_grade': [average_grade] * len(grades),
                    'high_grade': [high_grade] * len(grades),
                    'low_grade': [low_grade] * len(grades),
                    'regular_record': regular_records,
                    'combined_record': combined_records
                }),
                'trend_source': ColumnDataSource(data={
                    'trend_week': trend_weeks,
                    'trend_grade': trend_grades,
                    'team_name': [data.get('name', data.get('manager_name', f'Manager {i+1}'))] * len(trend_weeks),
                    'slope': [slope] * len(trend_weeks),
                    'slope_display': [f"{slope:+.2f}" if slope != 0 else "0.00"] * len(trend_weeks)
                }) if sklearn_available and trend_weeks else None
            })
            
            # Add to leaderboard data
            trend_icon = "📈" if slope > 0.1 else "📉" if slope < -0.1 else "➡️"
            leaderboard_data.append([
                data.get('name', data.get('manager_name', f'Manager {i+1}')),
                f"{current_grade:.2f}",
                f"{average_grade:.2f}",
                f"{slope:+.2f}" if sklearn_available else "N/A",
                trend_icon
            ])
        
        # Only create plots if we have data
        if len(team_data) == 0:
            print("   • No roster grade data available")
            return
        
        # Sort leaderboard by current grade
        leaderboard_data.sort(key=lambda x: float(x[1]), reverse=True)
        for i, row in enumerate(leaderboard_data):
            row.insert(0, str(i + 1))  # Add ranking
        
        # Create the interactive figure
        if output_dirs:
            plot_filename = os.path.join(output_dirs['html'], "roster_grades_interactive.html")
        else:
            plot_filename = "roster_grades_interactive.html"
        output_file(plot_filename)
        
        # Set up the figure with tools (mobile-responsive)
        p = figure(
            width=1200, 
            height=700,
            title="Interactive Fantasy Football Roster Grade Progression",
            x_axis_label="Week",
            y_axis_label="Roster Grade",
            tools="pan,wheel_zoom,box_zoom,reset,save",
            x_range=(0.5, 15.5),
            sizing_mode="scale_width",
            max_width=1200,
            min_width=300
        )
        
        # Create collapsible explanation panel
        explanation_text = """
        <h3 style="margin:10px 0 5px 0;">📊 Roster Grade Calculation Methodology</h3>
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 5px 0;">
            <h4 style="margin: 0 0 10px 0; color: #2c3e50;">📈 Data Sources & Collection</h4>
            <p style="margin: 3px 0;"><strong>Player Rankings:</strong> ESPN weekly statistical leaders by position</p>
            <p style="margin: 3px 0;"><strong>Position Tiers:</strong> QB top 30, RB top 60, WR/TE top 80 performers</p>
            <p style="margin: 3px 0;"><strong>Update Frequency:</strong> Weekly analysis based on current statistical performance</p>
            
            <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">🎯 Scoring System</h4>
            <p style="margin: 3px 0;"><strong>Starter Scoring:</strong> Full points based on tier ranking (higher tiers = more points)</p>
            <p style="margin: 3px 0;"><strong>Bench Scoring:</strong> 50% value for depth analysis and injury protection</p>
            <p style="margin: 3px 0;"><strong>Position Bonuses:</strong> Additional points for top-tier performers (top 10 in position)</p>
            <p style="margin: 3px 0;"><strong>Roster Balance:</strong> Weighted scoring accounts for positional scarcity</p>
            
            <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">🔢 Grade Calculation</h4>
            <p style="margin: 3px 0;"><strong>Raw Score:</strong> Sum of all player tier values + position bonuses</p>
            <p style="margin: 3px 0;"><strong>Normalization:</strong> Scaled to league-relative performance metrics</p>
            <p style="margin: 3px 0;"><strong>Final Grade:</strong> Composite score representing overall roster strength</p>
            <p style="margin: 3px 0;"><strong>Scale Range:</strong> Typically 15-35 points, higher = stronger roster talent</p>
            
            <h4 style="margin: 15px 0 10px 0; color: #2c3e50;">📊 Analysis Features</h4>
            <p style="margin: 3px 0;"><strong>Trend Lines:</strong> Week-over-week progression showing roster improvement/decline</p>
            <p style="margin: 3px 0;"><strong>Comparative Analysis:</strong> Performance relative to league average and competitors</p>
            <p style="margin: 3px 0;"><strong>Interactive Elements:</strong> Hover for detailed breakdowns, toggle visibility controls</p>
        </div>
        """
        
        explanation_div = Div(text=explanation_text, width=1200, height=0, visible=False, sizing_mode="scale_width", max_width=1200)
        
        # Create leaderboard
        leaderboard_html = """
        <h3 style="margin:10px 0 5px 0;">🏆 Current Roster Grade Leaderboard</h3>
        <table style="border-collapse: collapse; width: 100%; font-size: 12px; margin: 5px 0;">
        <tr style="background-color: #f0f0f0; font-weight: bold;">
            <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">#</th>
            <th style="border: 1px solid #ddd; padding: 8px;">Manager</th>
            <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Current Grade</th>
            <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Season Avg</th>
            <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Trend</th>
            <th style="border: 1px solid #ddd; padding: 8px; text-align: center;">Direction</th>
        </tr>
        """
        
        for row in leaderboard_data:
            rank = int(row[0])
            color = "#e8f5e8" if rank <= 3 else "#fff5e6" if rank <= 6 else "#ffeaea"
            leaderboard_html += f"""
            <tr style="background-color: {color};">
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[0]}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{row[1]}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[2]}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[3]}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[4]}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{row[5]}</td>
            </tr>"""
        
        leaderboard_html += "</table>"
        leaderboard_div = Div(text=leaderboard_html, width=500, height=200, sizing_mode="scale_width", max_width=500)
        
        # Add hover tool with detailed tooltips including combined record
        hover = HoverTool(tooltips=[
            ("Team", "@team"),
            ("Week", "@original_week"),
            ("Roster Grade", "@original_grade{0.1f}"),
            ("Regular Record", "@regular_record"),
            ("Combined Record", "@combined_record"),
            ("vs Median", "@median_result"),
            ("Season Average", "@avg_grade{0.1f}"),
            ("Season High", "@high_grade{0.1f}"),
            ("Season Low", "@low_grade{0.1f}")
        ])
        p.add_tools(hover)
        
        # Create separate hover for trend lines
        trend_hover = None
        if sklearn_available:
            trend_hover = HoverTool(tooltips=[
                ("Team", "@team_name"),
                ("Week", "@trend_week"),
                ("Projected Grade", "@trend_grade{0.1f}"),
                ("Trend Slope", "@slope_display grade/week")
            ], renderers=[])
            p.add_tools(trend_hover)
        
        # Create legend items for both data and trends
        data_legend_items = []
        trend_legend_items = []
        data_renderers = []
        trend_renderers = []
        
        # Add each team's data to the plot
        for team in team_data:
            # Plot the data points
            scatter_renderer = p.scatter(
                x='week', y='grade',
                source=team['source'],
                color=team['color'],
                size=8,
                alpha=0.8,
                line_color='white',
                line_width=1
            )
            
            # Plot the connection lines between data points
            line_renderer = p.line(
                x='week', y='grade',
                source=team['source'],
                line_color=team['color'],
                line_width=2,
                line_alpha=0.7
            )
            
            data_renderers.extend([scatter_renderer, line_renderer])
            
            # Plot the trend line if available
            if sklearn_available and team['trend_source']:
                trend_direction = "↗" if team['slope'] > 0.1 else "↘" if team['slope'] < -0.1 else "→"
                trend_renderer = p.line(
                    x='trend_week', y='trend_grade',
                    source=team['trend_source'],
                    line_color=team['color'],
                    line_width=3,
                    line_alpha=0.6,
                    line_dash='dashed'
                )
                
                trend_renderers.append(trend_renderer)
                
                # Add this renderer to the trend hover tool
                if trend_hover:
                    trend_hover.renderers.append(trend_renderer)
                
                # Add to trend legend
                trend_legend_items.append((f"{team['name']} {trend_direction} ({team['slope']:+.1f}/wk)", [trend_renderer]))
            
            # Add to data legend
            data_legend_items.append((f"{team['name']} ({team['current_grade']:.1f})", [scatter_renderer, line_renderer]))
        
        # Create legends with click policy
        data_legend = Legend(items=data_legend_items, location="center", title="Teams (Current Grade)")
        data_legend.click_policy = "hide"
        data_legend.title_text_font_size = "10pt"
        data_legend.label_text_font_size = "9pt"
        p.add_layout(data_legend, 'right')
        
        if trend_legend_items:
            trend_legend = Legend(items=trend_legend_items, location="center", title="Trend Analysis")
            trend_legend.click_policy = "hide"
            trend_legend.title_text_font_size = "10pt" 
            trend_legend.label_text_font_size = "9pt"
            p.add_layout(trend_legend, 'left')
        
        # Create working toggle buttons
        toggle_data_button = Button(label="Toggle All Teams", button_type="success", width=120)
        toggle_trends_button = Button(label="Toggle All Trends", button_type="primary", width=120) if sklearn_available else None
        show_explanation_button = Button(label="Show Calculation Details", button_type="warning", width=180)
        reset_button = Button(label="Reset Zoom", button_type="danger", width=100)
        
        # JavaScript callback for data toggle
        toggle_data_callback = CustomJS(args=dict(renderers=data_renderers), code="""
            let any_visible = false;
            for (let i = 0; i < renderers.length; i++) {
                if (renderers[i].visible) {
                    any_visible = true;
                    break;
                }
            }
            
            for (let i = 0; i < renderers.length; i++) {
                renderers[i].visible = !any_visible;
            }
            
            cb_obj.label = any_visible ? "Show All Teams" : "Hide All Teams";
        """)
        
        toggle_data_button.js_on_event('button_click', toggle_data_callback)
        
        # JavaScript callback for trends toggle
        if toggle_trends_button and trend_renderers:
            toggle_trends_callback = CustomJS(args=dict(renderers=trend_renderers), code="""
                let any_visible = false;
                for (let i = 0; i < renderers.length; i++) {
                    if (renderers[i].visible) {
                        any_visible = true;
                        break;
                    }
                }
                
                for (let i = 0; i < renderers.length; i++) {
                    renderers[i].visible = !any_visible;
                }
                
                cb_obj.label = any_visible ? "Show All Trends" : "Hide All Trends";
            """)
            
            toggle_trends_button.js_on_event('button_click', toggle_trends_callback)
        
        # JavaScript callback for explanation toggle
        explanation_callback = CustomJS(args=dict(explanation_div=explanation_div), code="""
            explanation_div.visible = !explanation_div.visible;
            if (explanation_div.visible) {
                explanation_div.height = 400;
                cb_obj.label = "Hide Calculation Details";
                cb_obj.button_type = "success";
            } else {
                explanation_div.height = 0;
                cb_obj.label = "Show Calculation Details";
                cb_obj.button_type = "warning";
            }
        """)
        
        show_explanation_button.js_on_event('button_click', explanation_callback)
        
        # Reset zoom callback
        reset_callback = CustomJS(args=dict(plot=p), code="plot.reset.emit();")
        reset_button.js_on_event('button_click', reset_callback)
        
        # Style the plot
        p.grid.grid_line_alpha = 0.3
        p.title.text_font_size = "14pt"
        p.xaxis.axis_label_text_font_size = "12pt"
        p.yaxis.axis_label_text_font_size = "12pt"
        
        # Create layout with controls and leaderboard
        if toggle_trends_button:
            controls = bokeh_row(toggle_data_button, toggle_trends_button, show_explanation_button, reset_button)
        else:
            controls = bokeh_row(toggle_data_button, show_explanation_button, reset_button)
        
        top_row = bokeh_row(leaderboard_div, p)
        layout = bokeh_column(explanation_div, top_row, controls)
        
        # Show the interactive plot
        show(layout)
        
        # Make the generated HTML mobile-friendly
        _make_html_mobile_friendly(plot_filename)
        
        print(f"\nInteractive Roster Grade plot saved as: {plot_filename}")
        print("\nInteractive Features:")
        print("   • 'Toggle All Teams' button: Show/hide all team roster grade lines")
        if sklearn_available:
            print("   • 'Toggle All Trends' button: Show/hide all trend lines")
        print("   • 'Show Calculation Details' button: Toggle detailed methodology explanation")
        print("   • Legend: Click team names to hide/show individual lines")
        print("   • Hover over points for detailed information")
        print("   • Pan and zoom to explore the data")
        
        print("\nRoster Grade Analysis:")
        print("   • Formula: Based on ESPN weekly stat leaders (QB top 30, RB top 60, WR/TE top 80)")
        print("   • Grades starters + bench with position tiers and bonus points")
        print("   • Points show roster talent level for each week")
        print("   • Higher grades indicate stronger overall roster construction")
        
    except Exception as e:
        import traceback
        print(f"\n❌ Error creating Roster Grade plot: {e}")
        print("Full traceback:")
        traceback.print_exc()
        print("   Falling back to text-only analysis...")
        _create_roster_grade_text_analysis(roster_grade_data)


def _create_roster_grade_text_analysis(roster_grade_data):
    """Fallback text analysis for roster grades"""
    print("\nRoster Grade Analysis (Text Format):")
    print(f"{'Team':<18} {'Current':<8} {'Average':<8} {'Trend':<10} {'High':<6} {'Low':<6}")
    print("-" * 65)
    
    # Sort teams by current grade
    sorted_teams = sorted(roster_grade_data.items(), 
                         key=lambda x: x[1].get('current_grade', 0), reverse=True)
    
    for user_id, data in sorted_teams:
        if not data.get('weekly_roster_grades'):
            continue
            
        current = data.get('current_grade', 0)
        average = data.get('average_grade', 0)
        trend = data.get('grade_trend', 'stable')
        high = data.get('highest_grade', 0)
        low = data.get('lowest_grade', 0)
        
        trend_icon = "📈" if trend == 'improving' else "📉" if trend == 'declining' else "➡️"
        
        print(f"{data['name'][:17]:<18} {current:<8.1f} {average:<8.1f} {trend_icon} {trend:<7} {high:<6.1f} {low:<6.1f}")


def create_combined_analysis_plot(team_power_data, roster_grade_data, output_dirs=None):
    """Create combined Power Rating and Roster Grade visualization"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS, Select
        from bokeh.layouts import column, row
        from bokeh.palettes import Category20
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh not available - install with: pip install bokeh")
        print("   Cannot create combined visualization without bokeh")
        return
    
    try:
        # Use consistent colors across both datasets
        colors = Category20[20] if len(team_power_data) <= 20 else Category20[20] * 2
        
        # Create the combined figure with two y-axes
        if output_dirs:
            plot_filename = os.path.join(output_dirs['html'], "combined_analysis.html")
        else:
            plot_filename = "combined_analysis.html"
        output_file(plot_filename)
        
        # Create comprehensive explanation panel
        from bokeh.models import Div
        explanation_text = """
        <h3 style="margin:5px 0;">Combined Fantasy Analysis: Power Rating vs Roster Grade Correlation</h3>
        <p style="margin:2px;"><b>Power Ratings (Left Axis):</b> Performance-based metric with win bonus (circles + solid lines)</p>
        <p style="margin:2px;"><b>Roster Grades (Right Axis):</b> Talent-based metric using ESPN rankings (squares + dashed lines)</p>
        <p style="margin:2px;"><b>Analysis Purpose:</b> Identify over/underperforming teams relative to roster talent</p>
        <p style="margin:2px;"><b>Correlation Patterns:</b> Strong correlation = performing to talent level, divergence = outliers</p>
        <p style="margin:2px;"><b>Interactive:</b> Click legends to toggle metric types, hover for cross-metric comparison</p>
        <p style="margin:2px;"><b>Scale:</b> Higher values on both axes indicate better performance and talent</p>
        """
        
        explanation_div = Div(text=explanation_text, width=1200, height=110, sizing_mode="scale_width", max_width=1200)
        
        # Set up main figure (mobile-responsive)
        p1 = figure(
            width=1200, 
            height=800,
            title="Combined Fantasy Analysis: Power Rating & Roster Grade Progression",
            x_axis_label="Week",
            y_axis_label="Power Rating",
            tools="pan,wheel_zoom,box_zoom,reset,save",
            x_range=(0.5, 15.5),
            sizing_mode="scale_width",
            max_width=1200,
            min_width=300
        )
        
        # Create second y-axis for roster grades
        from bokeh.models import LinearAxis
        p1.extra_y_ranges = {"roster_grade": p1.y_range}
        roster_axis = LinearAxis(y_range_name="roster_grade", axis_label="Roster Grade")
        p1.add_layout(roster_axis, 'right')
        
        # Prepare data for both metrics
        team_data = []
        
        for i, (user_id, power_data) in enumerate(team_power_data.items()):
            if user_id not in roster_grade_data:
                continue
                
            grade_data = roster_grade_data[user_id]
            
            # Find common weeks between both datasets
            power_weeks = set(power_data['weekly_power_ratings'].keys())
            grade_weeks = set(grade_data['weekly_roster_grades'].keys())
            common_weeks = sorted(power_weeks.intersection(grade_weeks))
            
            if len(common_weeks) < 2:
                continue
            
            # Extract data for common weeks
            power_ratings = [power_data['weekly_power_ratings'][w] for w in common_weeks]
            roster_grades = [grade_data['weekly_roster_grades'][w] for w in common_weeks]
            
            # Add jitter to prevent overlapping
            jitter = 0.05
            jittered_weeks = [w + np.random.uniform(-jitter, jitter) for w in common_weeks]
            
            team_data.append({
                'name': power_data['name'],
                'color': colors[i % len(colors)],
                'power_source': ColumnDataSource(data={
                    'week': jittered_weeks,
                    'rating': power_ratings,
                    'team': [power_data['name']] * len(power_ratings),
                    'original_week': common_weeks,
                    'metric': ['Power Rating'] * len(power_ratings)
                }),
                'grade_source': ColumnDataSource(data={
                    'week': [w + 0.1 for w in jittered_weeks],  # Slight offset
                    'grade': roster_grades,
                    'team': [power_data['name']] * len(roster_grades),
                    'original_week': common_weeks,
                    'metric': ['Roster Grade'] * len(roster_grades)
                })
            })
        
        if len(team_data) == 0:
            print("   • No overlapping data for combined visualization")
            return
        
        # Add enhanced hover tools with cross-metric information
        # We'll need to create a combined data source for proper cross-referencing
        combined_data = []
        for team in team_data:
            power_data = team['power_source'].data
            grade_data = team['grade_source'].data
            
            for i in range(len(power_data['week'])):
                week = power_data['original_week'][i]
                # Find matching grade data for same week
                matching_grade = "???"
                matching_power_rank = "???"
                if i < len(grade_data['grade']):
                    matching_grade = f"{grade_data['grade'][i]:.1f}"
                
                combined_data.append({
                    'week': power_data['week'][i],
                    'original_week': week,
                    'team': power_data['team'][i],
                    'rating': power_data['rating'][i],
                    'grade': matching_grade,
                    'metric_type': 'Power Rating'
                })
                
            for i in range(len(grade_data['week'])):
                week = grade_data['original_week'][i]
                # Find matching power data for same week
                matching_rating = "???"
                if i < len(power_data['rating']):
                    matching_rating = f"{power_data['rating'][i]:.1f}"
                    
                combined_data.append({
                    'week': grade_data['week'][i],
                    'original_week': week, 
                    'team': grade_data['team'][i],
                    'rating': matching_rating,
                    'grade': grade_data['grade'][i],
                    'metric_type': 'Roster Grade'
                })
        
        # Enhanced hover for power ratings
        power_hover = HoverTool(tooltips=[
            ("Team", "@team"),
            ("Week", "@original_week"),
            ("Power Rating", "@rating{0.1f}"),
            ("Roster Grade", "@grade")
        ])
        
        # Enhanced hover for roster grades  
        grade_hover = HoverTool(tooltips=[
            ("Team", "@team"),
            ("Week", "@original_week"),
            ("Roster Grade", "@grade{0.1f}"),
            ("Power Rating", "@rating")
        ])
        
        p1.add_tools(power_hover, grade_hover)
        
        # Create legend items
        power_legend_items = []
        grade_legend_items = []
        combined_legend_items = []
        
        # Add each team's data to the plot
        for team in team_data:
            # Power Rating lines (left y-axis)
            power_scatter = p1.scatter(
                x='week', y='rating',
                source=team['power_source'],
                color=team['color'],
                size=8,
                alpha=0.8,
                line_color='white',
                line_width=1
            )
            
            power_line = p1.line(
                x='week', y='rating',
                source=team['power_source'],
                line_color=team['color'],
                line_width=2,
                line_alpha=0.7
            )
            
            # Roster Grade lines (right y-axis) 
            grade_scatter = p1.scatter(
                x='week', y='grade',
                source=team['grade_source'],
                color=team['color'],
                size=6,
                alpha=0.6,
                marker='square',
                y_range_name="roster_grade"
            )
            
            grade_line = p1.line(
                x='week', y='grade',
                source=team['grade_source'],
                line_color=team['color'],
                line_width=2,
                line_alpha=0.5,
                line_dash='dashed',
                y_range_name="roster_grade"
            )
            
            # Calculate and plot combined metric (normalized average)
            # Normalize both metrics to 0-1 scale, then average them
            power_vals = team['power_source'].data['rating']
            grade_vals = team['grade_source'].data['grade']
            
            # Simple normalization (this could be improved with league-wide min/max)
            power_normalized = [(p - min(power_vals)) / (max(power_vals) - min(power_vals)) if max(power_vals) != min(power_vals) else 0.5 for p in power_vals]
            grade_normalized = [(g - min(grade_vals)) / (max(grade_vals) - min(grade_vals)) if max(grade_vals) != min(grade_vals) else 0.5 for g in grade_vals]
            
            combined_metric = [(p + g) / 2 for p, g in zip(power_normalized, grade_normalized)]
            
            combined_source = ColumnDataSource(data={
                'week': team['power_source'].data['week'],
                'combined': combined_metric,
                'team': team['power_source'].data['team'],
                'original_week': team['power_source'].data['original_week']
            })
            
            # Plot combined metric as stars on a separate y-axis
            p1.extra_y_ranges["combined"] = p1.y_range
            combined_scatter = p1.scatter(
                x='week', y='combined',
                source=combined_source,
                color=team['color'],
                size=10,
                alpha=0.6,
                marker='star',
                y_range_name="combined"
            )
            
            # Add to legends
            power_legend_items.append((f"{team['name']} (Power)", [power_scatter, power_line]))
            grade_legend_items.append((f"{team['name']} (Grade)", [grade_scatter, grade_line]))
            combined_legend_items.append((f"{team['name']} (Combined)", [combined_scatter]))
        
        # Create toggle buttons
        toggle_power_button = Button(label="Toggle All Power Ratings", button_type="success")
        toggle_grades_button = Button(label="Toggle All Roster Grades", button_type="primary")
        
        # Create separate legends
        power_legend = Legend(items=power_legend_items, location="center", title="Power Ratings (○—)")
        power_legend.click_policy = "hide"
        p1.add_layout(power_legend, 'left')
        
        grade_legend = Legend(items=grade_legend_items, location="center", title="Roster Grades (□‥)")
        grade_legend.click_policy = "hide"
        p1.add_layout(grade_legend, 'right')
        
        # JavaScript callbacks for toggle buttons
        power_toggle_code = """
        var legend = cb_obj.plot.left[1]; // Power legend
        var renderers = [];
        
        for (var item of legend.items) {
            for (var r of item.renderers) {
                renderers.push(r);
            }
        }
        
        var all_visible = renderers.every(r => r.visible);
        
        for (var r of renderers) {
            r.visible = !all_visible;
        }
        
        cb_obj.label = all_visible ? "Show Power Ratings" : "Hide Power Ratings";
        """
        
        grades_toggle_code = """
        var legend = cb_obj.plot.right[1]; // Grades legend
        var renderers = [];
        
        for (var item of legend.items) {
            for (var r of item.renderers) {
                renderers.push(r);
            }
        }
        
        var all_visible = renderers.every(r => r.visible);
        
        for (var r of renderers) {
            r.visible = !all_visible;
        }
        
        cb_obj.label = all_visible ? "Show Roster Grades" : "Hide Roster Grades";
        """
        
        toggle_power_button.js_on_click(CustomJS(code=power_toggle_code))
        toggle_grades_button.js_on_click(CustomJS(code=grades_toggle_code))
        
        # Style the plot
        p1.grid.grid_line_alpha = 0.3
        p1.title.text_font_size = "14pt"
        p1.xaxis.axis_label_text_font_size = "12pt"
        p1.yaxis.axis_label_text_font_size = "12pt"
        
        # Create layout with buttons and explanation
        button_row = row(toggle_power_button, toggle_grades_button)
        layout = column(explanation_div, p1, button_row)
        show(layout)
        
        # Make the generated HTML mobile-friendly
        _make_html_mobile_friendly(plot_filename)
        
        print(f"\nCombined analysis plot saved as: {plot_filename}")
        print("\nInteractive Features:")
        print("   • Left Legend: Click to toggle Power Rating lines (circles + solid)")
        print("   • Right Legend: Click to toggle Roster Grade lines (squares + dashed)")
        print("   • Hover over points for detailed information")
        print("   • Pan and zoom to explore correlations")
        
        print("\nAnalysis Notes:")
        print("   • Power Ratings (left axis): Performance-based with win bonus")
        print("   • Roster Grades (right axis): Talent-based using ESPN rankings")
        print("   • Look for correlation patterns between the two metrics")
        print("   • Divergence may indicate over/underperformance relative to talent")
        
    except Exception as e:
        print(f"\n❌ Error creating combined plot: {e}")
        print("   Combined visualization not available")


def create_trade_impact_visualization(combined_impacts, transactions_data=None, output_dirs=None):
    """Create enhanced trade impact visualization with toggleable filters and roster grouping"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool
        from bokeh.palettes import Set3, Category20
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh not available for trade impact visualization")
        return
    
    if not combined_impacts:
        print("\n⚠️  No trade impact data for visualization")
        return
    
    try:
        # Debug: Check transactions_data structure
        print(f"\n🔍 Debug: transactions_data type: {type(transactions_data)}")
        if transactions_data and isinstance(transactions_data, dict):
            print(f"🔍 Debug: transactions_data keys: {list(transactions_data.keys())[:5]}")
        
        if output_dirs:
            plot_filename = os.path.join(output_dirs['html'], "trade_impacts.html")
        else:
            plot_filename = "trade_impacts.html"
        output_file(plot_filename)
        
        # Prepare enhanced data with transaction categorization
        weeks = []
        managers = []
        impacts = []
        power_shifts = []
        grade_shifts = []
        transaction_types = []
        players_info = []
        roster_colors = []
        
        # Create unique roster color mapping
        unique_managers = list(set([impact['manager_name'] for impact in combined_impacts]))
        try:
            if len(unique_managers) <= 12:
                color_palette = Set3[max(3, len(unique_managers))]
            else:
                color_palette = Category20[min(20, len(unique_managers))]
        except (KeyError, ValueError):
            # Fallback colors
            color_palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", 
                           "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
                           "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5"][:len(unique_managers)]
        
        roster_color_map = {manager: color_palette[i % len(color_palette)] for i, manager in enumerate(unique_managers)}
        
        for impact in combined_impacts:
            weeks.append(impact['trade_week'])
            managers.append(impact['manager_name'])
            impacts.append(impact['combined_impact_score'])
            power_shifts.append(impact['power_rating_shift'])
            grade_shifts.append(impact['roster_grade_shift'])
            roster_colors.append(roster_color_map[impact['manager_name']])
            
            # Simplified transaction type determination
            transaction_type = "Trade"
            player_movement = "Trade participants"
            
            # Check if this looks like waiver activity (simplified heuristic)
            if transactions_data and isinstance(transactions_data, dict):
                trade_week = impact['trade_week']
                week_transactions = transactions_data.get(f"Week {trade_week}", [])
                if len(week_transactions) > 5:  # Many transactions suggest waiver activity
                    transaction_type = "Waiver/FA Activity"
                    player_movement = "Waiver wire/Free agent moves"
            
            transaction_types.append(transaction_type)
            players_info.append(player_movement)
        
        # Add significance categorization
        significances = []
        for impact_val in impacts:
            if abs(impact_val) >= 15:
                significances.append("Critical")
            elif abs(impact_val) >= 8:
                significances.append("Major")
            elif abs(impact_val) >= 3:
                significances.append("Moderate")
            else:
                significances.append("Minor")
        
        # Create data source
        source = ColumnDataSource(data={
            'week': weeks,
            'manager': managers,
            'impact': impacts,
            'power_shift': power_shifts,
            'grade_shift': grade_shifts,
            'color': roster_colors,
            'significance': significances,
            'transaction_type': transaction_types,
            'players_info': players_info
        })
        
        # Create plot (mobile-responsive)
        p = figure(
            width=1200,
            height=700,
            title="Enhanced Trade Impact Analysis: Combined Score by Week (Color = Roster)",
            x_axis_label="Trade Week",
            y_axis_label="Combined Impact Score",
            tools="pan,wheel_zoom,box_zoom,reset,save",
            sizing_mode="scale_width",
            max_width=1200,
            min_width=300
        )
        
        # Add zero line
        if weeks:
            p.line([min(weeks)-0.5, max(weeks)+0.5], [0, 0], 
                   line_color='black', line_width=1, line_dash='dashed', alpha=0.5)
        
        # Create different markers for different transaction types
        trade_mask = [t == "Trade" for t in transaction_types]
        waiver_mask = [t != "Trade" for t in transaction_types]
        
        # Plot trades as circles
        if any(trade_mask):
            trade_source = ColumnDataSource(data={
                key: [value for i, value in enumerate(source.data[key]) if trade_mask[i]]
                for key in source.data.keys()
            })
            trade_scatter = p.circle(
                x='week', y='impact',
                source=trade_source,
                size=12,
                color='color',
                alpha=0.8,
                line_color='black',
                line_width=1,
                legend_label="Trades"
            )
        
        # Plot waivers as triangles
        if any(waiver_mask):
            waiver_source = ColumnDataSource(data={
                key: [value for i, value in enumerate(source.data[key]) if waiver_mask[i]]
                for key in source.data.keys()
            })
            waiver_scatter = p.triangle(
                x='week', y='impact',
                source=waiver_source,
                size=10,
                color='color',
                alpha=0.6,
                line_color='darkgray',
                line_width=1,
                legend_label="Waivers/FA"
            )
        
        # Add enhanced hover tool
        hover = HoverTool(tooltips=[
            ("Manager", "@manager"),
            ("Transaction Type", "@transaction_type"),
            ("Week", "@week"),
            ("Combined Impact", "@impact{0.2f}"),
            ("Power Rating Shift", "@power_shift{+0.2f}"),
            ("Roster Grade Shift", "@grade_shift{+0.2f}"),
            ("Trade Significance", "@significance"),
            ("Player Movement", "@players_info")
        ])
        
        p.add_tools(hover)
        p.grid.grid_line_alpha = 0.3
        
        # Configure legend
        if hasattr(p, 'legend'):
            p.legend.location = "top_right"
            p.legend.click_policy = "hide"
        
        show(p)
        
        # Make the generated HTML mobile-friendly
        _make_html_mobile_friendly(plot_filename)
        
        print(f"\nEnhanced Trade Impact plot saved as: {plot_filename}")
        print("Interactive Features:")
        print("   • Legend: Click 'Trades' or 'Waivers/FA' to toggle visibility")
        print("   • Hover over points for detailed transaction information")
        print("   • Pan and zoom to explore the data")
        print("   • Color coding by roster/manager")
        print("   • Circles = Trades, Triangles = Waivers/Free Agents")
        
        return plot_filename
        
    except Exception as e:
        print(f"\n❌ Error creating trade impact visualization: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_luck_analysis_plot(team_power_data, output_dirs=None):
    """Create a luck analysis plot showing regular wins vs median wins with line of fairness (y=x)"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Legend, Button, CustomJS
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from bokeh.palettes import Category20
        from bokeh.models import Div, Line, Slope
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh not available - install with: pip install bokeh")
        return None
    
    try:
        # Setup output file
        if output_dirs and 'html' in output_dirs:
            plot_filename = os.path.join(output_dirs['html'], "luck_analysis.html")
        else:
            plot_filename = "luck_analysis.html"
        
        output_file(plot_filename)
        
        # Prepare data for luck analysis
        luck_data = []
        
        for user_id, data in team_power_data.items():
            # Get final regular record (cumulative wins/losses for week 15)
            cumulative_wins = data.get('cumulative_wins', {})
            cumulative_losses = data.get('cumulative_losses', {})
            
            # Get week 15 record (latest week)
            final_week = max(cumulative_wins.keys()) if cumulative_wins else 15
            regular_wins = cumulative_wins.get(final_week, 0)
            regular_losses = cumulative_losses.get(final_week, 0)
            
            # Get median record data
            median_record = data.get('median_record', {})
            median_wins = median_record.get('wins', 0)
            
            # Calculate luck metrics
            total_games = regular_wins + regular_losses
            expected_wins = median_wins  # How many wins they "deserved" vs median
            luck_factor = regular_wins - expected_wins if expected_wins > 0 else 0
            
            # Determine team name
            team_name = data.get('name', f'Team {user_id}')
            
            # Calculate luck category
            if luck_factor > 2:
                luck_category = "Very Lucky"
                luck_color = "#2ca02c"  # Green
            elif luck_factor > 0:
                luck_category = "Lucky" 
                luck_color = "#9fc852"  # Light green
            elif luck_factor < -2:
                luck_category = "Very Unlucky"
                luck_color = "#d62728"  # Red
            elif luck_factor < 0:
                luck_category = "Unlucky"
                luck_color = "#ff7f0e"  # Orange
            else:
                luck_category = "Fair"
                luck_color = "#1f77b4"  # Blue
                
            # Calculate win percentage
            regular_win_pct = (regular_wins / total_games * 100) if total_games > 0 else 0
            expected_win_pct = (expected_wins / total_games * 100) if total_games > 0 else 0
            
            luck_data.append({
                'team_name': team_name,
                'regular_wins': regular_wins,
                'median_wins': median_wins,
                'regular_losses': regular_losses,
                'luck_factor': luck_factor,
                'luck_category': luck_category,
                'luck_color': luck_color,
                'regular_win_pct': regular_win_pct,
                'expected_win_pct': expected_win_pct,
                'total_games': total_games,
                'record_display': f"{regular_wins}-{regular_losses}"
            })
        
        # Sort by luck factor for display
        luck_data.sort(key=lambda x: x['luck_factor'], reverse=True)
        
        # Create Bokeh data source
        source = ColumnDataSource(data={
            'team_name': [d['team_name'] for d in luck_data],
            'regular_wins': [d['regular_wins'] for d in luck_data],
            'median_wins': [d['median_wins'] for d in luck_data],
            'regular_losses': [d['regular_losses'] for d in luck_data],
            'luck_factor': [d['luck_factor'] for d in luck_data],
            'luck_category': [d['luck_category'] for d in luck_data],
            'luck_color': [d['luck_color'] for d in luck_data],
            'regular_win_pct': [d['regular_win_pct'] for d in luck_data],
            'expected_win_pct': [d['expected_win_pct'] for d in luck_data],
            'total_games': [d['total_games'] for d in luck_data],
            'record_display': [d['record_display'] for d in luck_data]
        })
        
        # Calculate axis ranges
        max_wins = max(max([d['regular_wins'] for d in luck_data]), max([d['median_wins'] for d in luck_data]))
        axis_max = max_wins + 1
        
        # Create figure (mobile-responsive)
        p = figure(
            title="Fantasy Football Luck Analysis: Regular Wins vs Median Wins",
            x_axis_label="Median Wins (Skill-Based Performance)", 
            y_axis_label="Regular Wins (Head-to-Head Record)",
            width=900, height=700,
            x_range=(0, axis_max),
            y_range=(0, axis_max),
            sizing_mode="scale_width",
            max_width=900,
            min_width=300
        )
        
        # Add line of fairness (y = x)
        p.line([0, axis_max], [0, axis_max], 
               line_width=3, line_color="black", line_dash="dashed",
               legend_label="Line of Fairness (y=x)", alpha=0.7)
        
        # Add scatter plot points
        scatter = p.scatter('median_wins', 'regular_wins', source=source,
                          size=15, color='luck_color', alpha=0.8,
                          line_color='white', line_width=2)
        
        # Add hover tool
        hover = HoverTool(tooltips=[
            ("Team", "@team_name"),
            ("Regular Record", "@record_display"),
            ("Regular Wins", "@regular_wins"),
            ("Median Wins", "@median_wins"),
            ("Luck Factor", "@luck_factor wins"),
            ("Luck Category", "@luck_category"),
            ("Regular Win %", "@regular_win_pct{0.1f}%"),
            ("Expected Win %", "@expected_win_pct{0.1f}%")
        ])
        p.add_tools(hover)
        
        # Create explanation div
        explanation_div = Div(
            text="""
            <h3 style="margin:5px 0;">Luck Analysis Explanation</h3>
            <p style="margin:2px;"><b>Line of Fairness (y=x):</b> Where teams should be if wins were purely skill-based</p>
            <p style="margin:2px;"><b>Above the Line:</b> Teams with more regular wins than expected (lucky)</p>
            <p style="margin:2px;"><b>Below the Line:</b> Teams with fewer regular wins than expected (unlucky)</p>
            <p style="margin:2px;"><b>Median Wins:</b> Theoretical wins if you played against the weekly league median</p>
            <p style="margin:2px;"><b>Regular Wins:</b> Actual head-to-head wins from your schedule</p>
            <p style="margin:2px;"><b>Color Coding:</b> Green (Lucky), Blue (Fair), Orange (Unlucky), Red (Very Unlucky)</p>
            <p style="margin:10px 0px 2px 0px; font-style: italic; color: #666;"><b>Note:</b> This analysis focuses on luck related to matchups and scheduling. It does not factor in injuries or other external circumstances that may affect team performance.</p>
            """,
            width=900, height=170,
            visible=False,
            sizing_mode="scale_width",
            max_width=900
        )
        
        # Create leaderboard
        leaderboard_html = "<h3>Luck Leaderboard</h3><table style='border-collapse: collapse; width: 100%; font-size: 12px;'>"
        leaderboard_html += "<tr style='background-color: #f0f0f0; font-weight: bold;'>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>#</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Team</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Record</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Median Wins</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Luck Factor</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 8px;'>Category</th>"
        leaderboard_html += "</tr>"
        
        for i, data in enumerate(luck_data):
            row_color = "#e8f5e8" if data['luck_factor'] > 0 else "#ffeaea" if data['luck_factor'] < 0 else "#f8f8f8"
            leaderboard_html += f"<tr style='background-color: {row_color};'>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{i+1}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px;'>{data['team_name']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{data['record_display']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{data['median_wins']}</td>"
            luck_sign = "+" if data['luck_factor'] > 0 else ""
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{luck_sign}{data['luck_factor']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 8px; text-align: center;'>{data['luck_category']}</td>"
            leaderboard_html += "</tr>"
        
        leaderboard_html += "</table>"
        
        leaderboard_div = Div(
            text=leaderboard_html,
            width=450, height=400,
            sizing_mode="scale_width",
            max_width=450
        )
        
        # Create buttons
        explanation_button = Button(label="Show/Hide Explanation", button_type="light", width=200)
        explanation_button.js_on_event("button_click", CustomJS(
            args=dict(explanation=explanation_div),
            code="explanation.visible = !explanation.visible;"
        ))
        
        reset_button = Button(label="Reset Zoom", button_type="warning", width=120)
        reset_button.js_on_event("button_click", CustomJS(
            args=dict(plot=p),
            code=f"""
            plot.x_range.start = 0;
            plot.x_range.end = {axis_max};
            plot.y_range.start = 0;
            plot.y_range.end = {axis_max};
            """
        ))
        
        # Layout
        buttons_row = bokeh_row(explanation_button, reset_button, spacing=10)
        main_row = bokeh_row(p, leaderboard_div, spacing=20)
        layout = bokeh_column(
            buttons_row,
            explanation_div,
            main_row,
            spacing=10
        )
        
        show(layout)
        
        # Make the generated HTML mobile-friendly
        _make_html_mobile_friendly(plot_filename)
        
        print(f"\nLuck Analysis plot saved as: {plot_filename}")
        print("Interactive Features:")
        print("   • Hover over points for detailed luck metrics")
        print("   • Points above line = Lucky teams")
        print("   • Points below line = Unlucky teams") 
        print("   • Leaderboard shows luck ranking")
        print("   • Show/Hide explanation for methodology")
        
        return plot_filename
        
    except Exception as e:
        print(f"\n❌ Error creating luck analysis: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_power_ranking_leaderboard(team_power_data, output_dirs=None):
    """Create a power ranking leaderboard showing current standings"""
    try:
        from bokeh.plotting import figure, show, output_file
        from bokeh.models import ColumnDataSource, HoverTool, Div
        from bokeh.layouts import column as bokeh_column, row as bokeh_row
        from bokeh.palettes import Category20
        import numpy as np
    except ImportError:
        print("\n⚠️  Bokeh not available - install with: pip install bokeh")
        return None
    
    try:
        # Setup output file
        if output_dirs and 'html' in output_dirs:
            plot_filename = os.path.join(output_dirs['html'], "power_ranking_leaderboard.html")
        else:
            plot_filename = "power_ranking_leaderboard.html"
        
        output_file(plot_filename)
        
        # Get current power rankings (latest week data)
        ranking_data = []
        
        for user_id, data in team_power_data.items():
            weekly_ratings = data.get('weekly_power_ratings', {})
            if not weekly_ratings:
                continue
            
            # Get latest week's data
            latest_week = max(weekly_ratings.keys())
            current_rating = weekly_ratings[latest_week]
            
            # Get record data
            cumulative_wins = data.get('cumulative_wins', {})
            cumulative_losses = data.get('cumulative_losses', {})
            regular_wins = cumulative_wins.get(latest_week, 0)
            regular_losses = cumulative_losses.get(latest_week, 0)
            
            # Get median record
            median_record = data.get('median_record', {})
            median_wins = median_record.get('wins', 0)
            median_losses = median_record.get('losses', 0)
            
            # Calculate combined record
            combined_wins = regular_wins + median_wins
            combined_losses = regular_losses + median_losses
            
            # Get scoring data
            cumulative_scores = data.get('cumulative_scores', {}).get(latest_week, [])
            avg_score = sum(cumulative_scores) / len(cumulative_scores) if cumulative_scores else 0
            high_score = max(cumulative_scores) if cumulative_scores else 0
            low_score = min(cumulative_scores) if cumulative_scores else 0
            
            # Determine team name
            team_name = data.get('name', f'Team {user_id}')
            
            ranking_data.append({
                'team_name': team_name,
                'power_rating': current_rating,
                'regular_record': f"{regular_wins}-{regular_losses}",
                'median_record': f"{median_wins}-{median_losses}",
                'combined_record': f"{combined_wins}-{combined_losses}",
                'avg_score': round(avg_score, 1),
                'high_score': high_score,
                'low_score': low_score,
                'regular_wins': regular_wins,
                'regular_losses': regular_losses,
                'total_points': round(sum(cumulative_scores), 1) if cumulative_scores else 0
            })
        
        # Sort by power rating (highest first)
        ranking_data.sort(key=lambda x: x['power_rating'], reverse=True)
        
        # Create main leaderboard table
        leaderboard_html = "<h2 style='text-align: center; color: #333; margin-bottom: 20px;'>🏆 Power Ranking Leaderboard</h2>"
        leaderboard_html += "<table style='border-collapse: collapse; width: 100%; margin: 0 auto; font-family: Arial, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.1);'>"
        
        # Header row
        leaderboard_html += "<tr style='background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; font-weight: bold;'>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: center;'>Rank</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: left;'>Team</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: center;'>Power Rating</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: center;'>H2H Record</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: center;'>Combined Record</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: center;'>Avg Score</th>"
        leaderboard_html += "<th style='border: 1px solid #ddd; padding: 12px; text-align: center;'>Total Points</th>"
        leaderboard_html += "</tr>"
        
        # Data rows
        for i, team in enumerate(ranking_data):
            # Color coding based on rank
            if i == 0:
                row_style = "background-color: #ffd700; color: #333;"  # Gold for 1st
            elif i == 1:
                row_style = "background-color: #c0c0c0; color: #333;"  # Silver for 2nd
            elif i == 2:
                row_style = "background-color: #cd7f32; color: white;"  # Bronze for 3rd
            elif i < len(ranking_data) // 2:
                row_style = "background-color: #e8f5e8; color: #333;"  # Light green for top half
            else:
                row_style = "background-color: #ffeaea; color: #333;"  # Light red for bottom half
            
            leaderboard_html += f"<tr style='{row_style}'>"
            
            # Rank with trophy emojis
            rank_display = f"#{i+1}"
            if i == 0:
                rank_display = "🏆 #1"
            elif i == 1:
                rank_display = "🥈 #2"
            elif i == 2:
                rank_display = "🥉 #3"
            
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; text-align: center; font-weight: bold;'>{rank_display}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; font-weight: bold;'>{team['team_name']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; text-align: center; font-weight: bold; font-size: 16px;'>{team['power_rating']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; text-align: center;'>{team['regular_record']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; text-align: center;'>{team['combined_record']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; text-align: center;'>{team['avg_score']}</td>"
            leaderboard_html += f"<td style='border: 1px solid #ddd; padding: 12px; text-align: center;'>{team['total_points']}</td>"
            leaderboard_html += "</tr>"
        
        leaderboard_html += "</table>"
        
        # Create explanation
        explanation_html = """
        <div style='margin-top: 30px; padding: 20px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea;'>
            <h3 style='margin-top: 0; color: #333;'>📋 Power Rating Explanation</h3>
            <p style='margin: 5px 0; color: #666;'><strong>Power Rating Formula:</strong> (Average Score × 6 + (High + Low) × 2 + (Win% × 200) × 2) ÷ 10</p>
            <p style='margin: 5px 0; color: #666;'><strong>H2H Record:</strong> Head-to-head wins/losses from your actual schedule</p>
            <p style='margin: 5px 0; color: #666;'><strong>Combined Record:</strong> H2H record + theoretical median record</p>
            <p style='margin: 5px 0; color: #666;'><strong>Ranking Colors:</strong> 🏆 Gold (1st), 🥈 Silver (2nd), 🥉 Bronze (3rd), Green (Top Half), Red (Bottom Half)</p>
        </div>
        """
        
        # Create main content div
        main_content = Div(
            text=leaderboard_html + explanation_html,
            width=1000,
            height=700,
            sizing_mode="scale_width",
            max_width=1000
        )
        
        # Layout
        layout = bokeh_column(main_content, spacing=20)
        
        show(layout)
        
        # Make the generated HTML mobile-friendly
        _make_html_mobile_friendly(plot_filename)
        
        print(f"\nPower Ranking Leaderboard saved as: {plot_filename}")
        print("Features:")
        print("   • Current power ratings with color-coded rankings")
        print("   • Trophy emojis for top 3 positions")
        print("   • Head-to-head and combined records")
        print("   • Average scores and total points")
        print("   • Methodology explanation")
        
        return plot_filename
        
    except Exception as e:
        print(f"\n❌ Error creating power ranking leaderboard: {e}")


def _make_html_mobile_friendly(filename):
    """Add mobile viewport and responsive CSS to Bokeh-generated HTML files"""
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Check if viewport is already present
        if 'name="viewport"' in content:
            return
            
        # Add viewport meta tag after charset
        content = content.replace(
            '<meta charset="utf-8">',
            '<meta charset="utf-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">'
        )
        
        # Add mobile-friendly CSS
        mobile_css = """
    <style>
        /* Mobile responsive improvements */
        @media (max-width: 768px) {
            .bk-root .bk {
                font-size: 12px !important;
            }
            
            .bk-root .bk-toolbar {
                display: flex !important;
                flex-wrap: wrap !important;
                justify-content: center !important;
            }
            
            .bk-root .bk-toolbar-button {
                margin: 2px !important;
                padding: 4px !important;
            }
            
            /* Make legends more compact on mobile */
            .bk-root .bk-legend {
                font-size: 10px !important;
            }
            
            /* Ensure plots scale properly */
            .bk-root .bk-canvas-wrapper {
                width: 100% !important;
                max-width: 100% !important;
            }
            
            /* Make buttons responsive */
            .bk-root .bk-btn {
                font-size: 11px !important;
                padding: 6px 10px !important;
                margin: 2px !important;
                min-width: auto !important;
                width: auto !important;
                max-width: 140px !important;
            }
            
            /* Button containers */
            .bk-root .bk-layout-grid-item {
                margin: 2px !important;
            }
            
            /* Make tables responsive */
            .bk-root table {
                font-size: 10px !important;
                width: 100% !important;
            }
            
            .bk-root th, .bk-root td {
                padding: 4px !important;
                font-size: 10px !important;
            }
            
            /* Div content responsive */
            .bk-root .bk-markup {
                width: 100% !important;
                max-width: 100% !important;
                overflow-x: auto !important;
            }
        }
        
        @media (max-width: 480px) {
            .bk-root .bk {
                font-size: 10px !important;
            }
            
            .bk-root .bk-legend {
                font-size: 8px !important;
                max-width: 150px !important;
                overflow: hidden !important;
            }
            
            .bk-root .bk-btn {
                font-size: 9px !important;
                padding: 4px 6px !important;
                margin: 1px !important;
                max-width: 100px !important;
            }
            
            .bk-root table {
                font-size: 8px !important;
            }
            
            .bk-root th, .bk-root td {
                padding: 2px !important;
                font-size: 8px !important;
            }
            
            /* Hide some elements that take too much space */
            .bk-root .bk-toolbar .bk-button-bar {
                flex-wrap: wrap !important;
            }
        }
        
        /* Improve touch targets */
        .bk-root .bk-toolbar-button {
            min-height: 44px !important;
            min-width: 44px !important;
        }
        
        .bk-root .bk-btn {
            min-height: 44px !important;
            min-width: 44px !important;
        }
        
        /* Better spacing for mobile */
        .bk-root {
            padding: 5px !important;
        }
        
        /* Ensure content fits */
        html, body {
            overflow-x: auto !important;
            width: 100% !important;
        }
        
        /* Responsive tables */
        .bk-root table {
            table-layout: auto !important;
            word-wrap: break-word !important;
        }
    </style>"""
        
        # Insert CSS before closing head tag
        content = content.replace('</head>', mobile_css + '\n</head>')
        
        # Save the modified content
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
            
        print(f"   ✓ Added mobile responsiveness to {filename}")
        
    except Exception as e:
        print(f"   ⚠️  Warning: Could not add mobile responsiveness to {filename}: {e}")
        import traceback
        traceback.print_exc()
        return None