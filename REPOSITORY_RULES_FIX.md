# 🚨 REPOSITORY RULES VIOLATION FIX

## The Issue
```
To https://github.com/hanu-cordbot/hanu-feedbot.git
 ! [remote rejected] main -> main (push declined due to repository rule violations)
error: failed to push some refs to 'https://github.com/hanu-cordbot/hanu-feedbot.git'
```

## Root Cause
Your GitHub repository has **branch protection rules** enabled on the `main` branch that prevent direct pushes.

## Solutions (Choose One):

### 🔧 **OPTION 1: Create Pull Request (Recommended)**

1. **Create a new branch for changes:**
   ```bash
   git checkout -b phase1-migration-setup
   git push -u origin phase1-migration-setup
   ```

2. **Go to GitHub and create a pull request:**
   - Navigate to: https://github.com/hanu-cordbot/hanu-feedbot/pulls
   - Click "New pull request"
   - Base: `main` ← Compare: `phase1-migration-setup`
   - Title: "Phase 1: Complete standalone worker migration"
   - Description: "Implements Phase 1 of Railway → GitHub Actions migration"

3. **Merge the pull request** (as repository owner, you can approve your own PR)

### 🔧 **OPTION 2: Temporarily Disable Branch Protection**

1. **Go to repository settings:**
   - https://github.com/hanu-cordbot/hanu-feedbot/settings/branches
   
2. **Find the main branch rule and click "Edit"**

3. **Temporarily uncheck protection options:**
   - [ ] Restrict pushes that create files
   - [ ] Require a pull request before merging
   
4. **Push your changes:**
   ```bash
   git push origin main
   ```

5. **Re-enable protection rules** after successful push

### 🔧 **OPTION 3: Force Push (Use with Caution)**
```bash
git push --force-with-lease origin main
```
⚠️ **Warning**: Only use if you're certain no one else is working on the repository

## ✅ After Successful Push

1. **Set up GitHub Secrets** (as outlined in PHASE1_COMPLETE.md)
2. **Test GitHub Actions workflow**
3. **Proceed with Phase 3 development**

## 🔄 Best Practice Workflow Going Forward

For future changes, use this workflow:
```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and commit
git add .
git commit -m "Your descriptive commit message"

# Push feature branch
git push -u origin feature/your-feature-name

# Create pull request on GitHub
# Merge when ready
```

This prevents branch protection conflicts and maintains clean history.
