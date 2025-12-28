# 🏈 Fantasy Football League Analysis - Interactive Web App

A comprehensive fantasy football analysis tool that provides interactive dashboards, trade analysis, power rankings, and detailed league insights. Now with a **dynamic web interface** for easy league selection and analysis!

## 🆕 New Features (v2.0)

### Interactive Web Interface
- **Username Input**: Simply enter your Sleeper username
- **League Selection**: View all your leagues and select which one to analyze
- **Real-time Analysis**: Watch the analysis progress in real-time
- **Dynamic Results**: View results immediately when analysis completes

### Multi-League Support
- Analyze any of your Sleeper leagues for the 2025 season
- Switch between different leagues without manual configuration
- Automatic league data fetching and validation

## 🚀 Quick Start

### Option 1: Use the Startup Scripts (Recommended)
**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
./start.sh
```

### Option 2: Manual Setup
1. Install dependencies:
```bash
pip install -r requirements.txt
npm install
```

2. Start the web server:
```bash
python server.py
```

3. Open your browser to: `http://localhost:5000`

## 🎯 How to Use

1. **Enter Username**: Type your Sleeper username on the homepage
2. **Select League**: Choose from your available 2025 leagues
3. **Start Analysis**: Click "Analyze Selected League" and watch the progress
4. **View Results**: Access your interactive reports when complete

## 📊 Analysis Features

### Power Rankings
- **Interactive Charts**: Track team performance over time
- **Strength Ratings**: See how each team's power has evolved
- **Performance Trends**: Identify rising and falling teams

### Roster Grades
- **Team Comparisons**: Compare roster quality across all teams
- **Player Values**: Analyze talent distribution and roster construction
- **Position Analysis**: Deep dive into positional strengths and weaknesses

### Luck Analysis
- **Fairness Metrics**: Compare actual record vs expected performance
- **Median Records**: See who's been lucky vs unlucky
- **Performance vs Expectation**: Find teams outperforming their talent

### Trade Analysis
- **Impact Scoring**: Detailed winner/loser analysis for every trade
- **Trade Timeline**: Track all league transactions chronologically
- **Manager Performance**: Grade managers on their trading decisions

### Waiver Wire Analysis
- **Pickup Tracking**: Monitor all waiver wire and free agent moves
- **Value Added**: Identify the best and worst waiver claims
- **Manager Activity**: See who's most active on waivers

### Manager Report Cards
- **Overall Grades**: Comprehensive performance scoring
- **Category Breakdown**: Grades for trades, waivers, and strategy
- **Comparative Analysis**: See how managers stack up against each other

## 🛠️ Technical Features

### Backend (Python Flask)
- **RESTful API**: Clean endpoints for league data and analysis
- **Real-time Status**: Live progress tracking during analysis
- **Background Processing**: Non-blocking analysis execution
- **Sleeper API Integration**: Direct connection to Sleeper's API

### Frontend (Modern Web)
- **Responsive Design**: Works on desktop and mobile
- **Progressive Interface**: Step-by-step workflow
- **Real-time Updates**: Live progress bars and status updates
- **Interactive Results**: Dynamic report loading and viewing

### Data Processing
- **Comprehensive Analysis**: All existing analysis features retained
- **Optimized Performance**: Faster processing with better error handling
- **Data Validation**: Robust error checking and user feedback

## 📂 Project Structure

```
fantasy-football/
├── server.py              # Flask web server
├── main.py                # Core analysis engine
├── index.html             # Interactive web interface
├── results_template.html  # Results dashboard template
├── build.js               # Build system for static assets
├── start.bat/.sh          # Easy startup scripts
├── requirements.txt       # Python dependencies
├── package.json           # Node.js dependencies
├── src/                   # Analysis modules
│   ├── api_clients.py     # Sleeper & ESPN API clients
│   ├── roster_grading.py  # Team roster analysis
│   ├── power_rankings.py  # Power rating calculations
│   ├── trade_analysis.py  # Trade impact analysis
│   ├── visualizations.py  # Chart generation
│   └── ...
└── fantasy_analysis_output/  # Generated reports
    ├── html_reports/      # Interactive HTML dashboards
    ├── json_data/         # Raw data for API access
    └── text_reports/      # Text summaries
```

## 🔧 Configuration

### Automatic Configuration
The web interface automatically creates and manages the `league_config.json` file based on your selections.

### Manual Configuration (Advanced)
You can still manually create a `league_config.json` file:

```json
{
  "sleeper_username": "your_username",
  "target_season": 2025,
  "league_name": "Your League Name",
  "league_id": "your_league_id",
  "auto_select": true
}
```

## 🌐 API Endpoints

- `GET /api/user/<username>` - Get user leagues
- `POST /api/analyze` - Start analysis for selected league
- `GET /api/status/<analysis_id>` - Get analysis progress
- `GET /api/results` - Get available reports
- `GET /results/<filename>` - Serve analysis files

## 🔍 Troubleshooting

### Common Issues

**Can't find leagues:**
- Verify your Sleeper username is correct
- Make sure you have leagues in the 2025 season
- Check that your leagues are not private/hidden

**Analysis fails:**
- Ensure you have sufficient league data (games played)
- Check your internet connection for API access
- Verify Python dependencies are installed

**Web server won't start:**
- Make sure port 5000 is available
- Install Flask dependencies: `pip install flask flask-cors`
- Check Python version (3.8+ required)

### Getting Help

1. Check the browser console for error messages
2. Look at the terminal output for detailed logs
3. Verify all dependencies are installed correctly
4. Ensure your Sleeper league has sufficient data

## 📈 What's New in v2.0

- ✅ **Web Interface**: No more command-line configuration
- ✅ **Multi-League Support**: Analyze any of your leagues
- ✅ **Real-time Progress**: Watch analysis happen live
- ✅ **Dynamic Results**: Immediate access to completed reports
- ✅ **Better UX**: Intuitive step-by-step workflow
- ✅ **Mobile Friendly**: Works great on all devices
- ✅ **Error Handling**: Better feedback and error messages

## 🎯 Future Enhancements

- [ ] Season comparison across multiple years
- [ ] League-to-league comparison features
- [ ] Advanced filtering and sorting options
- [ ] Export capabilities for reports
- [ ] Mobile app companion
- [ ] Discord/Slack integration for automated reports

---

Built with ❤️ for fantasy football enthusiasts who love data-driven insights!