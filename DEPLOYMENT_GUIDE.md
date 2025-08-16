# 🚀 HANU-FEEDBOT RAILWAY DEPLOYMENT GUIDE

## ✅ Status: READY FOR DEPLOYMENT

Your bot workflow is now working correctly! All tests passed:
- ✅ Environment Variables
- ✅ Cron Worker (bot execution)
- ✅ Flask App & Job Endpoint

## 📋 What We Fixed

### 1. **Unicode Character Issues**
- Removed emoji characters that caused encoding errors on Windows
- Replaced with ASCII text equivalents (e.g., ✅ → [OK], ❌ → [ERROR])

### 2. **Job Endpoint Implementation**
- Added missing Railway cron job endpoint at `/job` (or your custom `JOB_ENDPOINT`)
- Subprocess execution with proper timeout handling (10 minutes)
- Clean exit strategy - app shuts down after job completion

### 3. **Error Handling & Debugging**
- Added comprehensive logging and error reporting
- Timeout protection (bot won't run forever)
- Lock file mechanism prevents overlapping runs
- Better error messages with stdout/stderr capture

### 4. **Simplified Architecture**
- Removed complex Celery dependencies for Railway
- Direct subprocess execution for reliability
- Clean shutdown signals to Railway

## 🚂 Railway Deployment Steps

### 1. **Prepare Repository**
```bash
git add .
git commit -m "Ready for Railway: Fixed Unicode issues, added job endpoint, improved error handling"
git push
```

### 2. **Deploy to Railway**
1. Go to [Railway.app](https://railway.app)
2. Create new project from GitHub repo
3. Set environment variables:
   ```
   JOB_ENDPOINT=/your-secret-path
   DISCORD_BOT_TOKEN=your_token
   CHANNEL_ID=your_channel_id
   GEMINI_API_KEY=your_key
   DISCORD_WEBHOOK_URL=your_webhook
   ADMIN_PASS=your_admin_password
   MAX_AGE_HOURS=3000
   ```

### 3. **Set Up Railway Cron**
Railway will call your job endpoint every hour:
```
POST https://your-app.up.railway.app/your-secret-path
```

The workflow:
1. Railway calls your job endpoint
2. Flask app spawns cron_worker.py subprocess
3. Bot processes feeds, posts to Discord
4. App exits cleanly (Railway shuts down container)
5. Repeat hourly

## 🧪 Local Testing

You can test locally using:
```bash
# Test the full workflow
python test_workflow.py

# Test just the cron worker
python cron_worker.py

# Test the Flask app
python app.py
# Then visit: http://localhost:5000/api/health
```

## 📁 Key Files

- **`app.py`** - Flask web app with job endpoint
- **`cron_worker.py`** - Standalone bot execution
- **`bot/main.py`** - Core bot logic
- **`test_workflow.py`** - Validation tests
- **`Procfile`** - Railway configuration

## 🔧 Configuration

Your `.env` file should contain:
```bash
JOB_ENDPOINT=/job
DISCORD_BOT_TOKEN=your_token
CHANNEL_ID=your_channel_id
GEMINI_API_KEY=your_key
DISCORD_WEBHOOK_URL=your_webhook
ADMIN_PASS=your_password
MAX_AGE_HOURS=3000
```

## 🎯 Next Steps

1. **Deploy to Railway** following the steps above
2. **Set up Railway cron** to call your job endpoint hourly
3. **Monitor the logs** to ensure everything works
4. **Configure your feeds** through the dashboard
5. **Test with a manual cron trigger**

## 🚨 Troubleshooting

If something goes wrong:

1. **Check Railway logs** for errors
2. **Verify environment variables** are set correctly
3. **Test locally first** using `python test_workflow.py`
4. **Check Discord permissions** for your bot
5. **Validate feed URLs** are accessible

## 📊 Success Metrics

When working correctly, you should see:
- Bot connects to Discord ✅
- Feeds parsed successfully ✅ 
- Posts sent to Discord channels ✅
- Clean shutdown after completion ✅
- No hanging processes ✅

The bot will run for ~1-2 minutes, process feeds, post updates, then exit cleanly until the next hourly trigger.

---

**Your bot is ready for production! 🎉**
