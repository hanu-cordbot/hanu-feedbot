# 🧪 GitHub Actions Test Workflow Guide

## ✅ **PROBLEM SOLVED**: Verification Without Flooding Discord

You were absolutely right! The main workflow might be working perfectly but not posting anything because all entries are already in `seen.json`. 

I've created a **dedicated test workflow** that:
- ✅ **Ignores seen entries** - Forces processing of recent content
- ✅ **Supports Forum channels** - Your thread channel `1393729514927947817` is ready!
- ✅ **Configurable test count** - Choose how many posts to test
- ✅ **Safe state management** - Automatically backs up and restores `seen.json`

## 🚀 **How to Test the Workflow**

### **Step 1: Access the Test Workflow**
1. Go to your repository: https://github.com/hanu-cordbot/hanu-feedbot
2. Click **Actions** tab
3. Select **"HANU Feed Bot - TEST MODE"** from the workflow list
4. Click **"Run workflow"** button

### **Step 2: Configure Test Parameters**
```yaml
📊 Number of test entries: 3        # How many posts to process
📍 Target channel ID: (leave empty) # Uses default mapping
🔧 Force test run: true             # Ignores locks and seen entries
```

### **Step 3: Monitor Execution**
- Watch the workflow progress in real-time
- Check each step: setup → validation → backup → test run → restore
- Expected duration: 5-10 minutes

### **Step 4: Verify Results**
**In Discord:**
- ✅ **Forum Channel**: Check for new threads in `1393729514927947817`
- ✅ **Regular Channel**: Check for posts in your mapped channels
- ✅ **Content Quality**: Verify AI summaries and media processing

## 🎯 **What You Should See**

### **Forum Channel Behavior:**
- Each RSS entry creates a **separate thread**
- Thread title = Post title (truncated to 100 chars)
- Full content posted inside the thread
- No daily summary (forum channels work differently)

### **Text Channel Behavior:**
- Daily summary message posted
- Details thread created under summary
- All entries posted in the details thread
- Summary updated with entry links

## 📊 **Current Configuration Status**

Based on the test results:
- ✅ **Discord Access**: Confirmed working
- ✅ **Forum Channel**: `1393729514927947817` detected as ForumChannel
- ✅ **Feed Mapping**: 2 feeds mapped (1 to forum, 1 to regular channel)
- ✅ **Seen Entries**: 10 entries currently marked as seen
- ✅ **Environment**: All required secrets configured

## 🔧 **Troubleshooting Guide**

### **If No Posts Appear:**
1. **Check workflow logs** - Look for error messages
2. **Verify channel permissions** - Bot needs CREATE_THREADS in forum
3. **Check feed content** - Run locally: `python test_forum_workflow.py`
4. **API rate limits** - Wait 5 minutes and try again

### **If Only Some Posts Appear:**
1. **Age filtering** - Test uses 7-day lookback (168 hours)
2. **Duplicate detection** - Some entries might still be in seen.json
3. **Feed parsing** - Check for malformed RSS entries

### **If Workflow Fails:**
1. **Missing secrets** - Verify DISCORD_BOT_TOKEN and GEMINI_API_KEY
2. **Permission errors** - Check bot permissions in target channels
3. **Timeout issues** - Forum thread creation might be slow

## 📋 **Production vs Test Mode**

| Feature | Production Workflow | Test Workflow |
|---------|-------------------|---------------|
| **Schedule** | Every hour (0 * * * *) | Manual trigger only |
| **Seen entries** | Respects seen.json | Ignores most entries |
| **Age limit** | 36 hours | 168 hours (7 days) |
| **Entry count** | Unlimited | Configurable (default: 3) |
| **State changes** | Permanent | Backed up & restored |
| **Purpose** | Production use | Testing & verification |

## 🎯 **Expected Test Results**

After running the test workflow, you should see:

1. **In Workflow Logs:**
   ```
   ✅ Processed X new entries
   📝 Check Discord channels for new test posts
   🧵 Forum channel test: Check for new threads
   ```

2. **In Discord Forum Channel (`1393729514927947817`):**
   ```
   New threads created for recent RSS entries
   Each thread contains full formatted content
   AI-generated summaries in Vietnamese
   ```

3. **In Discord Text Channels:**
   ```
   Daily summary message updated
   Details thread with new entries
   Proper media processing and links
   ```

## 🚀 **Ready to Test!**

The test workflow is now live and ready. Here's what to do:

1. **Go to GitHub Actions** → "HANU Feed Bot - TEST MODE"
2. **Click "Run workflow"** with default settings
3. **Monitor the execution** (should complete in ~10 minutes)
4. **Check Discord channels** for new test posts
5. **Verify forum threads** in channel `1393729514927947817`

The test will automatically restore your original state, so it's completely safe to run! 🎯

---

## 📞 **Support**

If you encounter any issues:
1. Check the workflow execution logs
2. Run `python test_forum_workflow.py` locally
3. Verify bot permissions in Discord channels
4. Review the troubleshooting guide above

**The test workflow is your verification tool - use it anytime you want to confirm the bot is working without affecting production data!** ✨
