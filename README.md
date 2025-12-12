# Fantasy Football Analysis Dashboard

This repository contains automated fantasy football analysis tools and a web dashboard for sharing results with leaguemates.

## 📁 Project Structure

```
FantasyFootball/
├── main.py                     # Main orchestrator script
├── league_config.json          # League configuration (auto-generated)
├── requirements.txt            # Python dependencies
├── package.json                # Node.js dependencies for web interface
├── netlify.toml               # Netlify deployment configuration
├── build.js                   # Web interface build script
├── index.html                 # Main dashboard
├── src/                       # Source code modules
│   ├── __init__.py           # Package initialization
│   ├── api_clients.py        # ESPN and Sleeper API clients
│   ├── roster_grading.py     # Player ranking and roster analysis
│   ├── power_rankings.py     # Team power rating calculations
│   ├── median_record_calculator.py # Median-based record analysis
│   ├── trade_analysis.py     # Trade and waiver impact analysis
│   ├── visualizations.py     # Interactive Bokeh visualizations
│   └── tests/                # Test suite
├── data/                     # Data storage
│   ├── league_config.template.json # Configuration template
│   └── *.json               # Generated analysis data files
├── dist/                     # Built web interface (auto-generated)
└── fantasy_analysis_output_*/ # Analysis results (auto-generated)
    ├── html_reports/         # Interactive HTML visualizations
    ├── json_data/            # Structured data exports
    └── text_reports/         # Text-based analysis summaries
```

## 🏈 Features

- **Power Rankings**: Interactive progression charts showing team strength over time
- **Roster Analysis**: Grade and compare roster quality across all teams  
- **Trade Impact**: Detailed analysis of all trades with winner/loser scoring
- **Waiver Wire**: Track and analyze waiver pickups and free agent moves
- **Manager Grades**: Performance report cards for all league managers

## 🚀 Quick Start

### For League Managers

1. **Configure your league** (one-time setup):
   ```bash
   # Copy the template and edit with your details
   cp league_config.template.json league_config.json
   # Edit league_config.json with your username and league ID
   ```

2. **Run the analysis**:
   ```bash
   python main.py  # Will auto-use your configured league
   ```

3. **Build the web dashboard**:
   ```bash
   npm install
   npm run build
   ```

4. **Deploy to Netlify** (see deployment guide below)

### For League Members

Just visit the shared Netlify URL to access all interactive dashboards!

## 🌐 Netlify Deployment

### One-Time Setup

1. **Create Netlify Account**: Sign up at [netlify.com](https://netlify.com)

2. **Connect GitHub**: Link your GitHub account in Netlify settings

3. **Create New Site**: 
   - Click "New site from Git"
   - Choose this repository
   - Set build command: `npm run build`
   - Set publish directory: `dist`

### Updating Your Dashboard

Every time you run a new analysis:

1. Run `python main.py` to generate new data
2. Run `npm run build` to prepare files
3. Push changes to GitHub
4. Netlify will automatically rebuild and deploy!

### Manual Deploy (Alternative)

If you prefer manual deployment:

1. Run `npm run build`
2. Drag the `dist` folder to Netlify's deploy area
3. Share the generated URL with your league

## 📱 Mobile Friendly

All dashboards are optimized for mobile viewing, so your leaguemates can check their shame on the go!

## 🔄 Auto-Updates

The system automatically:
- Uses the latest analysis data
- Updates file timestamps
- Creates clean URLs for sharing
- Maintains organized file structure

## 💡 Tips

- Run analysis weekly for best results
- Share the Netlify URL in your league chat
- All visualizations are interactive - encourage exploration!
- The "worst trades" report is perfect for league roasting 🔥

## 🛠️ Technical Details

- **Backend**: Python (Sleeper API, ESPN data, Bokeh visualizations)
- **Frontend**: HTML/CSS/JS dashboard
- **Deployment**: Netlify with automated builds
- **Data**: JSON exports for API integration