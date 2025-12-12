"""
Fantasy Football Analysis Package
Comprehensive fantasy football analysis tools including:
- ESPN API integration for player rankings
- Sleeper API for league data
- Power rankings and roster grading
- Trade and waiver analysis
- Interactive visualizations
"""

__version__ = "1.0.0"
__author__ = "Fantasy Football Analysis Team"

# Core modules
from .api_clients import ESPNAPI, SleeperAPI
from .roster_grading import FantasyAnalyzer
from .power_rankings import calculate_weekly_power_ratings, create_power_rating_plot
from .median_record_calculator import calculate_median_records
from .trade_analysis import (
    analyze_real_trades_only,
    analyze_waiver_pickups,
    calculate_manager_grades,
    create_trade_visualization,
    create_waiver_visualization,
    create_manager_grade_visualization,
    print_trade_analysis_results
)
from .visualizations import (
    create_roster_grade_plot,
    create_trade_impact_visualization,
    create_luck_analysis_plot,
    create_power_ranking_leaderboard
)

__all__ = [
    'ESPNAPI', 'SleeperAPI', 'FantasyAnalyzer',
    'calculate_weekly_power_ratings', 'create_power_rating_plot',
    'calculate_median_records',
    'analyze_real_trades_only', 'analyze_waiver_pickups', 'calculate_manager_grades',
    'create_trade_visualization', 'create_waiver_visualization', 'create_manager_grade_visualization',
    'print_trade_analysis_results',
    'create_roster_grade_plot', 'create_trade_impact_visualization', 
    'create_luck_analysis_plot', 'create_power_ranking_leaderboard'
]