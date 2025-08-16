# 🚀 HANU-FEEDBOT PRODUCTION DEPLOYMENT GUIDE

## 🎯 **DEPLOYMENT ARCHITECTURE**

```
GitHub Pages (Dashboard) ←→ Railway (API/Cron Jobs)
     ↓                           ↓
[Static Dashboard]         [Serverless Bot]
- Analytics                - Cron endpoints  
- Feed management          - Health checks
- Stats display            - Job processing
- Prompt editor            - R2 integration
```

**Why this setup?**
- ✅ **Cost-effective**: GitHub Pages is free, Railway serverless is cheap
- ✅ **Reliable**: No 24/7 runtime costs on Railway
- ✅ **Scalable**: Dashboard scales infinitely, API scales on demand
- ✅ **Maintainable**: Separate concerns, easier debugging

---

## 🔧 **STEP 1: FIX RAILWAY DEPLOYMENT**

### **1.1 Railway Environment Variables**
Set these in your Railway dashboard:
```bash
# Required
DISCORD_BOT_TOKEN=your_bot_token_here
CHANNEL_ID=your_discord_channel_id
GEMINI_API_KEY=your_gemini_api_key
JOB_ENDPOINT=/your-secret-cron-path

# R2 Storage (for videos >10MB)
R2_BUCKET=your-r2-bucket-name
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_ACCOUNT_ID=your-cloudflare-account-id

# Optional
MAX_AGE_HOURS=24
ADMIN_PASS=your-admin-password
```

### **1.2 Deploy to Railway**
```bash
# Commit the fixes
git add .
git commit -m "Fix Railway deployment configuration"
git push origin main

# Railway will automatically redeploy with the fixed Dockerfile
```

### **1.3 Test Railway Deployment**
```bash
# Test health endpoint
curl https://your-app.up.railway.app/api/health

# Should return: {"status": "healthy", "timestamp": "..."}

# Test manual job trigger (replace with your JOB_ENDPOINT)
curl -X POST https://your-app.up.railway.app/your-secret-cron-path

# Should return: {"status": "success", "message": "Job completed successfully"}
```

---

## 📊 **STEP 2: DEPLOY GITHUB PAGES DASHBOARD**

### **2.1 Configure API Endpoint**
Edit `docs/config.js` and update your Railway URL:
```javascript
API_BASE_URL: 'https://your-actual-railway-app.railway.app'
```

### **2.2 Enable GitHub Pages**
1. Go to your GitHub repository settings
2. Navigate to **Pages** section
3. Set Source to **Deploy from a branch**
4. Select branch: `gh-pages`
5. Select folder: `/docs`
6. Click **Save**

### **2.3 Commit and Deploy Dashboard**
```bash
# Make sure you're on gh-pages branch
git checkout gh-pages

# Update the API URL in config.js first!
# Edit docs/config.js and set your Railway URL

git add .
git commit -m "Deploy dashboard to GitHub Pages"
git push origin gh-pages

# GitHub Actions will automatically deploy to Pages
```

### **2.4 Access Your Dashboard**
Your dashboard will be available at:
```
https://hanu-cordbot.github.io/hanu-feedbot/
```

---

## ⏰ **STEP 3: SET UP CRON JOBS**

### **3.1 Railway Cron Configuration**
In Railway dashboard:
1. Go to your service
2. Add a **Cron Job**
3. Set schedule: `0 * * * *` (every hour)
4. Set command: 
   ```bash
   curl -X POST https://your-app.railway.app/your-secret-cron-path
   ```

### **3.2 Alternative: External Cron Service**
Use services like:
- **UptimeRobot** (free monitoring + cron)
- **Cronhub** 
- **EasyCron**
- **Your own server** with cron

Example cron job:
```bash
# Add to crontab (crontab -e)
0 * * * * curl -X POST https://your-app.railway.app/your-secret-cron-path >/dev/null 2>&1
```

---

## 🧪 **STEP 4: TESTING & VALIDATION**

### **4.1 Test Railway API**
```bash
# Health check
curl https://your-app.railway.app/api/health

# Manual job trigger
curl -X POST https://your-app.railway.app/your-secret-cron-path

# Check stats endpoint
curl https://your-app.railway.app/api/stats
```

### **4.2 Test GitHub Pages Dashboard**
1. Visit `https://hanu-cordbot.github.io/hanu-feedbot/`
2. Check that it loads without errors
3. Verify API calls work (check browser console)
4. Test navigation between pages

### **4.3 Monitor First Cron Run**
1. Trigger manual job via dashboard or curl
2. Check Railway logs for processing output
3. Verify Discord posts appear
4. Check stats in dashboard

---

## 📈 **STEP 5: MONITORING & MAINTENANCE**

### **5.1 Railway Logs**
Monitor Railway deployment logs:
```
[STATS] Raw entries parsed: 225
[STATS] New entries to process: 12
[STATS] Posts sent to Discord: 8
[STATS] R2 uploads: 1
[STATS] Catbox uploads: 2
[STATS] Errors handled: 0
```

### **5.2 Dashboard Analytics**
Monitor in GitHub Pages dashboard:
- Processing statistics
- Success/failure rates
- Media upload distribution
- Performance metrics

### **5.3 Cost Monitoring**
- **Railway**: Monitor serverless usage (should be ~$0-5/month)
- **R2 Storage**: Monitor storage usage and bandwidth
- **GitHub Pages**: Free (no monitoring needed)

---

## 🔒 **STEP 6: SECURITY & CONFIGURATION**

### **6.1 Secure Your Endpoints**
```bash
# Use a strong, random JOB_ENDPOINT
JOB_ENDPOINT=/cron-job-8f4e2a9b-1234-5678-9abc-def012345678

# Set strong admin password
ADMIN_PASS=YourSecureAdminPassword123!
```

### **6.2 Environment Security**
- ✅ Never commit sensitive keys to git
- ✅ Use Railway's environment variables
- ✅ Rotate API keys periodically
- ✅ Monitor access logs

---

## 🚀 **DEPLOYMENT CHECKLIST**

### **Railway (Backend)**
- ✅ Fixed Dockerfile configuration
- ✅ Environment variables set
- ✅ Health endpoint working
- ✅ Cron job endpoint working
- ✅ Logs showing successful processing

### **GitHub Pages (Dashboard)**  
- ✅ API URL configured in `docs/config.js`
- ✅ GitHub Pages enabled
- ✅ Dashboard accessible online
- ✅ API calls working from dashboard

### **Integration**
- ✅ Cron jobs triggering Railway
- ✅ Discord posts appearing
- ✅ Statistics updating in dashboard
- ✅ Media uploads working (Discord/Catbox/R2)

---

## 🎉 **SUCCESS METRICS**

Once deployed successfully, you should see:

1. **Railway Dashboard**:
   - Successful deployments
   - Regular cron job hits every hour
   - Clean logs with processing statistics

2. **GitHub Pages Dashboard**:
   - Live statistics updating
   - Feed management interface
   - Analytics and monitoring

3. **Discord**:
   - Hourly posts from Facebook feeds
   - Posts showing original Facebook page avatars/names
   - Media files properly uploaded and displayed

4. **Cost Efficiency**:
   - Railway costs: ~$0-5/month (serverless)
   - R2 costs: ~$1-5/month (depending on video volume)
   - GitHub Pages: $0/month (free)

**Total estimated cost: $1-10/month** (vs $20+/month for 24/7 hosting)

---

## 🆘 **TROUBLESHOOTING**

### **Common Railway Issues**
```bash
# If deployment fails, check:
1. Environment variables are set
2. Dockerfile builds successfully  
3. Port 8080 is exposed
4. Health endpoint returns 200

# Debug command:
railway logs --tail
```

### **Common Dashboard Issues**
```bash
# If dashboard doesn't load:
1. Check GitHub Pages is enabled
2. Verify docs/config.js has correct API URL
3. Check browser console for errors
4. Ensure gh-pages branch is deployed

# Debug: Check browser dev tools Network tab
```

### **Common Integration Issues**
```bash
# If cron jobs fail:
1. Verify JOB_ENDPOINT path is correct
2. Check Railway service is running
3. Verify network connectivity
4. Check Railway logs for errors
```

---

## 🎯 **NEXT STEPS AFTER DEPLOYMENT**

1. **Monitor for 24 hours** - ensure cron jobs run successfully
2. **Optimize feed list** - add/remove Facebook feeds as needed
3. **Customize prompts** - use dashboard to refine AI responses
4. **Scale R2 storage** - monitor usage and adjust retention
5. **Add monitoring** - set up UptimeRobot for additional monitoring

**Your enhanced bot is now production-ready with cost-effective, scalable architecture! 🚀**
