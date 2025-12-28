# Render Deployment Guide 🚀

## Quick Deploy to Render

### 1. Push to GitHub
```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin main
```

### 2. Deploy to Render
1. Go to [render.com](https://render.com)
2. Sign in with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Select your `FantasyFootball` repository
6. Render will automatically detect Python and deploy!

### 3. Configuration (Auto-detected)
Render automatically detects:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn server:app`
- **Python Version**: 3.11
- **Environment**: Production

### 4. Environment Variables (Optional)
In Render dashboard, you can set:
- `FLASK_ENV=production` (already configured)
- Any other environment variables you need

### 5. Custom Domain (Optional)
- In Render service dashboard
- Go to Settings → Custom Domains
- Add your custom domain

## What Render Provides

✅ **Automatic Python Detection**: Render auto-configures Python environment  
✅ **Zero-Config Deployment**: Uses render.yaml configuration  
✅ **Automatic HTTPS**: SSL certificates included  
✅ **Continuous Deployment**: Auto-deploys on GitHub pushes  
✅ **Free Tier**: 750 hours/month free  
✅ **Fast Cold Starts**: Quicker than many competitors  
✅ **Built-in DDoS Protection**: Enterprise-grade security  

## Your App Will Be Live At
`https://your-service-name.onrender.com`

## Features Available Online

🌐 **Sleeper Username Input**: Users enter their Sleeper username  
🏈 **League Selection**: Shows all user's 2025 leagues  
📊 **Real-time Analysis**: Generates complete fantasy analysis  
📱 **Mobile Responsive**: Works on all devices  
⚡ **Fast Results**: Analysis runs on Render's servers  

## Files Created for Render

- `render.yaml`: Render service configuration
- `Procfile`: Web server startup command  
- `runtime.txt`: Python version specification
- `requirements.txt`: Dependencies with gunicorn web server

## Architecture

```
User Browser → Render.com → Flask Server → Sleeper API
                   ↓
             Fantasy Analysis Engine
                   ↓
             Generated HTML Reports
```

## No Local Setup Required!

Users simply visit your Render URL and can:
1. Enter their Sleeper username
2. Select their fantasy league
3. Get complete analysis generated in real-time
4. View interactive reports directly in browser

Perfect for sharing with your entire league! 🏆

## Render vs Railway

✅ **More Generous Free Tier**: 750 hours vs $5 credit  
✅ **Faster Deployments**: Optimized build process  
✅ **Better Cold Start Performance**: Faster app wake-up  
✅ **Simpler Configuration**: Less setup required

### 1. Push to GitHub
```bash
git add .
git commit -m "Prepare for Railway deployment"
git push origin main
```

### 2. Deploy to Railway
1. Go to [railway.app](https://railway.app)
2. Sign in with GitHub
3. Click "New Project"
4. Select "Deploy from GitHub repo"
5. Choose your `FantasyFootball` repository
6. Railway will automatically detect Python and deploy!

### 3. Environment Variables (Optional)
In Railway dashboard, you can set:
- `FLASK_ENV=production` (for production mode)
- Any other environment variables you need

### 4. Custom Domain (Optional)
- In Railway project dashboard
- Go to Settings → Domains
- Add your custom domain

## What Railway Provides

✅ **Automatic Python Detection**: Railway auto-configures Python environment  
✅ **Zero-Config Deployment**: Uses Procfile and railway.json  
✅ **Automatic HTTPS**: SSL certificates included  
✅ **Continuous Deployment**: Auto-deploys on GitHub pushes  
✅ **Generous Free Tier**: $5/month free credits  
✅ **Scalable**: Automatically handles traffic spikes  

## Your App Will Be Live At
`https://your-app-name.up.railway.app`

## Features Available Online

🌐 **Sleeper Username Input**: Users enter their Sleeper username  
🏈 **League Selection**: Shows all user's 2025 leagues  
📊 **Real-time Analysis**: Generates complete fantasy analysis  
📱 **Mobile Responsive**: Works on all devices  
⚡ **Fast Results**: Analysis runs on Railway's servers  

## Files Created for Railway

- `Procfile`: Tells Railway how to start the web server
- `railway.json`: Railway configuration
- `runtime.txt`: Python version specification
- `requirements.txt`: Updated with gunicorn web server

## Architecture

```
User Browser → Railway.app → Flask Server → Sleeper API
                     ↓
               Fantasy Analysis Engine
                     ↓
               Generated HTML Reports
```

## No Local Setup Required!

Users simply visit your Railway URL and can:
1. Enter their Sleeper username
2. Select their fantasy league
3. Get complete analysis generated in real-time
4. View interactive reports directly in browser

Perfect for sharing with your entire league! 🏆