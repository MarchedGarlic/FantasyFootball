# Netlify Deployment Guide 🚀

## Overview
Your Fantasy Football Analysis tool now supports **dual deployment**:
1. **Local Flask App**: Interactive analysis with Sleeper API integration
2. **Static Netlify Site**: Pre-generated reports for public sharing

## Netlify Deployment Steps

### 1. Build Static Site
```bash
npm run build
```
This copies all analysis files to the `dist/` directory with `_latest` suffix for consistent naming.

### 2. Deploy to Netlify
You have several options:

#### Option A: Drag & Drop (Easiest)
1. Go to [netlify.com](https://netlify.com)
2. Login to your account
3. Drag the entire `dist/` folder to the deploy area
4. Your site will be live instantly!

#### Option B: Git Integration
1. Push your repository to GitHub
2. Connect Netlify to your GitHub repo
3. Set build command: `npm run build`
4. Set publish directory: `dist`
5. Deploy automatically on every push

#### Option C: Netlify CLI
```bash
npm install -g netlify-cli
netlify deploy --dir=dist --prod
```

### 3. Custom Domain (Optional)
- In Netlify dashboard, go to Site settings > Domain management
- Add your custom domain
- Netlify will handle SSL certificates automatically

## File Structure for Netlify

```
dist/
├── index.html                              # Static dashboard
├── luck_analysis_latest.html              # Luck analysis report
├── manager_grades_latest.html             # Manager grades
├── power_ranking_leaderboard_latest.html  # Power rankings
├── power_rating_interactive_latest.html   # Interactive power charts
├── roster_grades_interactive_latest.html  # Roster analysis
├── trade_analysis_latest.html             # Trade analysis
├── waiver_analysis_latest.html            # Waiver wire report
└── worst_trades_report_latest.html        # Worst trades report
```

## Key Features of Netlify Version

✅ **Static HTML Reports**: All visualizations work without server  
✅ **Mobile Responsive**: Optimized for all devices  
✅ **Interactive Charts**: Bokeh visualizations fully functional  
✅ **Fast Loading**: CDN-powered global distribution  
✅ **No Server Costs**: Static hosting is free on Netlify  

## Important Notes

- **Analysis Generation**: Reports must be generated locally first using the Flask app
- **Data Updates**: To update Netlify site, re-run analysis locally, then redeploy
- **No Sleeper API**: Static site shows pre-generated reports, no live API calls
- **Perfect for Sharing**: Share your league analysis with a simple URL

## Workflow

1. **Local Development**: Use Flask app for interactive analysis and new league data
2. **Static Generation**: Run `npm run build` to create static files
3. **Deploy**: Upload `dist/` folder to Netlify for public access
4. **Share**: Send Netlify URL to league members

## Testing Static Site Locally

```bash
cd dist
python -m http.server 8001
```
Then visit http://localhost:8001

## Troubleshooting

**Charts not loading?** Ensure all JavaScript files are included in the build  
**Links broken?** Check that all file names use `_latest` suffix  
**Deploy fails?** Verify `dist/` folder contains all necessary files  

---

🎉 **You now have a complete dual-deployment fantasy football analysis tool!**