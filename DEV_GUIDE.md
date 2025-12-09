# 🔧 Local Development Guide

## Running Your Dashboard Locally

### Quick Start
```bash
# 1. Build the latest dashboard
npm run build

# 2. Start local server
npm run serve
```

Your dashboard will open automatically at: **http://localhost:3000**

### Development Workflow

#### Option A: Quick Preview (Use existing data)
```bash
npm run serve
```
- Uses your latest analysis data
- Fast startup (~2 seconds)
- Perfect for testing UI changes

#### Option B: Full Refresh (New analysis + preview)
```bash
npm run start
```
- Runs `python main.py` to get fresh data
- Builds dashboard with latest analysis
- Starts local server
- Takes 1-2 minutes but always current

#### Option C: Manual Steps
```bash
# 1. Generate new analysis (optional)
python main.py

# 2. Build dashboard
npm run build

# 3. Start server
npm run serve
```

### Available Commands

| Command | Description | Use When |
|---------|-------------|----------|
| `npm run serve` | Start local server only | Quick UI preview |
| `npm run start` | Build + serve | Want fresh data |
| `npm run build` | Build dashboard only | Just building |
| `npm run analysis` | Run Python analysis only | Just need data |
| `npm run deploy` | Full analysis + build | Preparing for deploy |

### Development Tips

**🔄 Live Changes**: 
- HTML/CSS changes: Just refresh browser
- Analysis changes: Run `npm run build` then refresh

**📱 Mobile Testing**:
- Use your phone on same network
- Visit: `http://YOUR_COMPUTER_IP:3000`
- IP shown in terminal when server starts

**🐛 Troubleshooting**:
- **Port busy**: Server will try port 3001, 3002, etc.
- **No data**: Run `python main.py` first
- **Build errors**: Check for latest analysis output folder

**⚡ Quick Edits**:
- Edit `index.html` for homepage changes
- Edit `build.js` for file processing
- Config in `league_config.json`

### Stopping the Server
Press `Ctrl+C` in the terminal to stop the local server.

---

**Happy developing! 🚀** Your leaguemates are going to love this dashboard!