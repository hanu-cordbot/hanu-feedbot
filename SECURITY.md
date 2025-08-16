# 🔒 SECURITY GUIDE FOR HANU-FEEDBOT

## ⚠️ **CRITICAL SECURITY NOTICE**

This repository contains sensitive authentication tokens and API keys. **NEVER make this repository public** without following the security checklist below.

---

## 🛡️ **SECURITY CHECKLIST**

### **✅ Before Making Repository Public:**

1. **Remove ALL sensitive files from git history**
2. **Regenerate ALL API keys and tokens**  
3. **Use environment variables for ALL secrets**
4. **Verify .gitignore is working properly**
5. **Test with clean clone of repository**

### **🚨 Files That Must NEVER Be Public:**

- `.env` - Contains all your API keys and tokens
- `cookies.txt` - Facebook authentication cookies
- `netscape_cookies.txt` - Additional cookie files
- `avatar_cache.json` - Cached avatar data
- `channels.json` - Discord channel configuration
- `seen.json` - Bot state data
- `system_prompt.json` - System configuration
- Any files with your actual API keys, tokens, or passwords

---

## 🔑 **API KEYS AND TOKENS TO REGENERATE**

If this repository was ever public, you MUST regenerate these:

### **Discord:**
1. Go to https://discord.com/developers/applications
2. Select your bot application
3. Go to "Bot" section → "Reset Token"
4. Update DISCORD_BOT_TOKEN in Railway environment variables

### **Discord Webhook:**
1. Go to your Discord server settings
2. Integrations → Webhooks → Delete old webhook
3. Create new webhook → Copy new URL
4. Update DISCORD_WEBHOOK_URL in Railway environment variables

### **Google Gemini API:**
1. Go to https://aistudio.google.com/app/apikey
2. Delete old API key → Create new API key
3. Update GEMINI_API_KEY in Railway environment variables

### **Cloudflare R2:**
1. Go to Cloudflare dashboard → R2 → Manage R2 API tokens
2. Delete old tokens → Create new API token
3. Update R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY in Railway

---

## 🚀 **SECURE DEPLOYMENT GUIDE**

### **Option 1: Keep Repository Private (Recommended)**
- Keep the GitHub repository private
- Deploy to Railway from private repository
- Share code only with trusted collaborators

### **Option 2: Make Repository Public (Advanced)**
Only do this if you've completed ALL security steps:

1. **Clean Git History:**
   ```bash
   # Remove sensitive files from ALL commits
   git filter-branch --force --index-filter \
   'git rm --cached --ignore-unmatch .env cookies.txt netscape_cookies.txt' \
   --prune-empty --tag-name-filter cat -- --all
   
   # Force push to remove history
   git push origin --force --all
   ```

2. **Regenerate ALL secrets** (see list above)

3. **Test with clean clone:**
   ```bash
   git clone https://github.com/your-username/hanu-feedbot.git test-repo
   cd test-repo
   # Verify no sensitive data is present
   ```

4. **Use Railway environment variables only**

---

## 💡 **BEST PRACTICES**

### **✅ DO:**
- Use Railway environment variables for ALL secrets
- Keep `.env.example` as template (without real values)
- Add sensitive files to `.gitignore`
- Regularly rotate API keys and tokens
- Use strong, unique passwords
- Monitor your API usage for suspicious activity

### **❌ DON'T:**
- Commit real API keys, tokens, or passwords
- Share sensitive files via email, Discord, etc.
- Use the same password for multiple services
- Ignore security warnings
- Make repository public without following checklist

---

## 🆘 **IF YOU ACCIDENTALLY EXPOSED SECRETS**

### **Immediate Actions:**
1. **Regenerate ALL API keys and tokens immediately**
2. **Change ALL passwords**
3. **Review your API usage logs for suspicious activity**
4. **Monitor your Discord server for unauthorized activity**
5. **Check your Cloudflare R2 usage for unexpected charges**

### **GitHub Exposure:**
1. **Make repository private immediately**
2. **Follow the git history cleaning steps above**
3. **Contact GitHub support if needed**

---

## 📞 **EMERGENCY CONTACTS**

If you believe your credentials were compromised:

- **Discord Support:** https://support.discord.com/
- **Google Cloud Support:** https://cloud.google.com/support
- **Cloudflare Support:** https://support.cloudflare.com/
- **GitHub Support:** https://support.github.com/

---

## ✅ **VERIFICATION CHECKLIST**

Before considering your setup secure:

- [ ] Repository is private OR all sensitive data removed
- [ ] All API keys and tokens regenerated  
- [ ] Railway environment variables updated with new secrets
- [ ] `.gitignore` includes all sensitive file types
- [ ] Tested deployment with clean repository clone
- [ ] No sensitive data in git history
- [ ] All team members follow security practices

**Remember: Security is an ongoing process, not a one-time setup!** 🔒
