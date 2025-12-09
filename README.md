# Fantasy Football Analysis Dashboard

This repository contains automated fantasy football analysis tools and a web dashboard for sharing results with leaguemates.

## 🏈 Features

- **Power Rankings**: Interactive progression charts showing team strength over time
- **Roster Analysis**: Grade and compare roster quality across all teams  
- **Trade Impact**: Detailed analysis of all trades with winner/loser scoring
- **Waiver Wire**: Track and analyze waiver pickups and free agent moves
- **Manager Grades**: Performance report cards for all league managers

## 🚀 Quick Start

### For League Managers

1. Run the analysis:
   ```bash
   python main.py
   ```

2. Build the web dashboard:
   ```bash
   npm install
   npm run build
   ```

3. Deploy to Netlify (see deployment guide below)

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