# 🤖 AUTOMATED GITHUB PAGES + RAILWAY SYNC SETUP

## 🎯 **WHAT THIS DOES:**

Your GitHub Pages dashboard will automatically:
1. **Fetch fresh data** from Railway API every hour
2. **Update the dashboard** with latest stats and feeds  
3. **Deploy automatically** via GitHub Actions
4. **Fallback gracefully** to direct Railway API if local data fails

---

## 🔧 **SETUP STEPS:**

### **Step 1: Enable GitHub Actions**
```bash
# Go to your GitHub repository settings:
# https://github.com/hanu-cordbot/hanu-feedbot/settings/actions

1. Go to Settings → Actions → General
2. Under "Actions permissions":
   - Select "Allow all actions and reusable workflows"
3. Under "Workflow permissions":
   - Select "Read and write permissions"
   - Check "Allow GitHub Actions to create and approve pull requests"
4. Click "Save"
```

### **Step 2: Configure GitHub Pages**
```bash
# In your repo settings:
# https://github.com/hanu-cordbot/hanu-feedbot/settings/pages

1. Go to Settings → Pages
2. Under "Source":
   - Select "GitHub Actions"
3. Click "Save"
```

### **Step 3: Add GitHub Token (Optional - for Railway triggers)**
```bash
# Create a GitHub Personal Access Token:
# https://github.com/settings/tokens

1. Go to GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. Select scopes: "repo", "workflow"
4. Copy the token

# Add to Railway environment variables:
5. Go to Railway dashboard → Variables
6. Add: GITHUB_TOKEN=your_token_here
```

### **Step 4: Deploy and Test**
```bash
# Commit and push the new workflow files:
git add .
git commit -m "Add automated GitHub Pages sync with Railway"
git push origin main

# This will trigger:
1. ✅ Deploy workflow (immediate)
2. ✅ Update workflow (every hour at :05 minutes)
```

---

## 🕐 **HOW THE AUTOMATION WORKS:**

### **Hourly Sync Schedule:**
```
:00 - Railway cron job runs (processes feeds)
:05 - GitHub Actions fetches Railway data 
:06 - GitHub Pages rebuilds with fresh data
:07 - Dashboard shows updated stats
```

### **Data Flow:**
```
[Facebook Feeds] 
     ↓
[Railway Bot Processing]
     ↓  
[Railway API Endpoints]
     ↓
[GitHub Actions Fetch]
     ↓
[GitHub Pages Dashboard]
     ↓
[Users See Updated Data]
```

### **Smart Data Loading:**
- **Primary**: Local cached data (fast loading)
- **Fallback**: Direct Railway API (real-time)
- **Hybrid**: Best of both worlds

---

## 📊 **ENDPOINTS CREATED:**

### **Public Railway Endpoints (no auth needed):**
- `GET /api/public/feeds` - Feed list and count
- `GET /api/public/stats` - Basic service stats

### **Admin Railway Endpoints:**
- `POST /api/trigger-pages-update` - Manual GitHub Pages update

### **GitHub Pages Data:**
- `./data/feeds.json` - Cached feed data
- `./data/stats.json` - Cached stats data  
- `./data/meta.json` - Update metadata

---

## ✅ **VERIFICATION:**

### **Test GitHub Actions:**
```bash
# Check if workflows are running:
1. Go to: https://github.com/hanu-cordbot/hanu-feedbot/actions
2. Look for "Deploy GitHub Pages Dashboard" workflow
3. Should show green checkmarks
```

### **Test Data Sync:**
```bash
# After 1 hour, check:
1. Railway processes feeds (check logs)
2. GitHub Actions runs update workflow  
3. GitHub Pages shows fresh data
```

### **Test Fallback:**
```bash
# Delete local data files to test API fallback:
rm docs/data/*.json
# Dashboard should still work via Railway API
```

---

## 🎉 **BENEFITS:**

### **Performance:**
- ⚡ **Faster loading** (cached data)
- 🌐 **Global CDN** (GitHub Pages)
- 📱 **Mobile optimized**

### **Reliability:**
- 🔄 **Auto-updates** every hour
- 🛡️ **Graceful fallbacks**
- 📊 **Always fresh data**

### **Cost:**
- 💰 **$0 hosting** (GitHub Pages free)
- ⚡ **Minimal Railway usage**
- 📈 **Scales automatically**

---

## 🔍 **MONITORING:**

### **GitHub Actions:**
- **Logs**: https://github.com/hanu-cordbot/hanu-feedbot/actions
- **Status**: Check for green/red indicators
- **Manual trigger**: "Run workflow" button

### **Railway API:**
- **Health**: https://hanu-feedbot-production.up.railway.app/api/health
- **Public data**: https://hanu-feedbot-production.up.railway.app/api/public/feeds

### **GitHub Pages:**
- **Dashboard**: https://hanu-cordbot.github.io/hanu-feedbot/
- **Data cache**: Check browser dev tools → Network tab

---

## 🚀 **NEXT STEPS:**

1. **Enable GitHub Actions** (most important!)
2. **Configure GitHub Pages source**
3. **Push these changes**
4. **Wait 5-10 minutes** for first deployment
5. **Check dashboard** is live and updating

**Your dashboard will now automatically stay in sync with Railway data!** 🎯
