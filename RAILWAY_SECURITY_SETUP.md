# 🚀 RAILWAY ENVIRONMENT SETUP INSTRUCTIONS

## 📋 **REQUIRED: Update Railway Environment Variables**

After regenerating your API keys, set these in your Railway dashboard:

### **1. Go to Railway Dashboard**
- Visit: https://railway.app/
- Select your hanu-feedbot project
- Go to Variables tab

### **2. Set These Variables:**

```bash
# Discord Configuration
DISCORD_BOT_TOKEN=your_new_discord_bot_token
DISCORD_WEBHOOK_URL=your_new_discord_webhook_url  
CHANNEL_ID=your_discord_channel_id

# AI Configuration
GEMINI_API_KEY=your_new_gemini_api_key

# R2 Storage (if using)
R2_BUCKET=your_r2_bucket_name
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_ACCESS_KEY_ID=your_new_r2_access_key
R2_SECRET_ACCESS_KEY=your_new_r2_secret_key
R2_REGION=auto
R2_ENDPOINT=https://your_account_id.r2.cloudflarestorage.com
R2_PUBLIC_BASE=https://your_account_id.r2.cloudflarestorage.com/your_bucket
R2_MAX_BYTES=5000000000

# Bot Configuration
MAX_AGE_HOURS=36
JOB_ENDPOINT=/your-secret-cron-path
ADMIN_PASS=your_secure_admin_password

# Optional
DATA_DIR=/app/data
```

### **3. Deploy Updated Configuration**
```bash
railway up
```

### **4. Test the Deployment**
```bash
# Test health endpoint
curl https://hanu-feedbot-production.up.railway.app/api/health

# Test job endpoint (should require auth)
curl -X POST https://hanu-feedbot-production.up.railway.app/your-secret-path
```

---

## 🔐 **SECURITY STATUS AFTER FOLLOWING THIS GUIDE:**

### **✅ SECURED:**
- Sensitive files removed from git tracking
- Proper .gitignore in place
- Security documentation added
- Environment template provided

### **⚠️ STILL NEEDED:**
- [ ] Regenerate ALL API keys and tokens
- [ ] Update Railway environment variables
- [ ] Test deployment with new credentials
- [ ] Keep repository PRIVATE
- [ ] Set up secure cron jobs

---

## 🎯 **NEXT STEPS:**

1. **Regenerate credentials** (all services listed above)
2. **Update Railway variables** with new credentials  
3. **Test deployment** to ensure everything works
4. **Keep repository private** for security
5. **Set up cron jobs** using Railway or external service

**Your bot deployment will continue working with the new secure setup!** 🚀
