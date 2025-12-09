# 🚀 Netlify Deployment Guide

## Quick Setup (5 minutes)

### Step 1: Configure Your League

The system supports two ways to specify which league to analyze:

#### Option A: Configuration File (Recommended)
1. Copy `league_config.template.json` to `league_config.json`
2. Edit the file with your details:
```json
{
  "sleeper_username": "your_sleeper_username",
  "target_season": 2025,
  "league_name": "Your League Name",
  "league_id": "your_league_id_here",
  "auto_select": true
}
```

To find your league ID:
- Run `python main.py` without config first
- Choose your league interactively
- Copy the League ID from the output

#### Option B: Environment Variables (For Netlify)
Set these in your Netlify dashboard under Site Settings → Environment Variables:
- `SLEEPER_USERNAME`: Your Sleeper username
- `LEAGUE_ID`: Your league ID
- `TARGET_SEASON`: 2025 (or desired season)

### Step 2: Prepare Your Repository
```bash
# Test the configuration
python main.py  # Should auto-select your league

# Build the dashboard
npm run build

# Commit everything to GitHub
git add .
git commit -m "Add Netlify deployment setup with league config"
git push
```

### Step 3: Deploy to Netlify

#### Option A: Automatic Deployment (Recommended)
1. Go to [netlify.com](https://netlify.com) and sign up/login
2. Click **"New site from Git"**
3. Choose **GitHub** and authorize Netlify
4. Select your **FantasyFootball** repository
5. Configure build settings:
   - **Build command**: `npm run deploy` (runs analysis + build)
   - **Publish directory**: `dist`
   - **Environment variables** (if not using config file):
     - `SLEEPER_USERNAME`: your_username
     - `LEAGUE_ID`: your_league_id  
     - `TARGET_SEASON`: 2025
6. Click **"Deploy site"**

**Note**: First deployment may take 2-3 minutes as it runs the full analysis.

#### Option B: Manual Deployment
1. Run `npm run build` locally
2. Go to [netlify.com](https://netlify.com)
3. Drag the `dist` folder to the deploy area
4. Your site is live!

### Step 3: Customize Your Site
- **Site Name**: Click "Site settings" → "Change site name"
- **Custom Domain**: Add your own domain if desired
- **Environment Variables**: Not needed for this setup

## 🔄 Updating Your Dashboard

Every time you want to update with new analysis:

```bash
# 1. Run new analysis
python main.py

# 2. Build for web
npm run build

# 3. Deploy (if using automatic deployment)
git add .
git commit -m "Update analysis data"
git push

# OR for manual deployment: drag new dist folder to Netlify
```

## 📱 Sharing with League

Once deployed, you'll get a URL like: `https://your-site-name.netlify.app`

Share this with your leaguemates! The dashboard includes:

- **📊 Power Rankings** - Team strength over time  
- **📈 Roster Grades** - Talent analysis
- **🔄 Trade Analysis** - Winners and losers
- **📋 Waiver Wire** - Best/worst pickups
- **🏆 Manager Grades** - Performance report cards
- **📝 Trade Report** - Detailed text analysis

## 🛠️ Advanced Setup

### Custom Domain
1. In Netlify: Site Settings → Domain Management
2. Add custom domain
3. Update DNS records as instructed

### Auto-Deploy Branch Protection
- Set up branch protection in GitHub
- Only deploy from `main` branch
- Require PR reviews for extra safety

### Analytics
- Enable Netlify Analytics to see who's viewing
- Track which reports are most popular

## 🎉 Pro Tips

- **Update Weekly**: Run analysis after each week's games
- **Mobile First**: All dashboards work great on phones
- **Interactive**: Encourage leaguemates to explore the charts
- **Roast Material**: The worst trades report is 🔥 for league chat
- **Bookmark Friendly**: Each report has its own URL

## 🚨 Troubleshooting

**Build Failed?**
- Make sure you ran `python main.py` first
- Check that `fantasy_analysis_output_*` folder exists
- Run `npm install` if dependencies are missing

**Links Broken?**
- Files are renamed to `*_latest.html` for consistent URLs
- Make sure build process completed successfully

**Site Won't Load?**
- Check Netlify deploy logs for errors
- Ensure `dist` directory was properly published

## 🏈 Ready to Dominate?

Your leaguemates will be impressed by the professional analysis dashboard. Time to show them who really understands fantasy football! 📊🏆