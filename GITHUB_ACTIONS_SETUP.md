# GitHub Actions Secrets Setup Guide

This document provides instructions for setting up the required repository secrets for the HANU Feed Bot GitHub Actions workflow.

## Required Secrets

Navigate to your repository settings → Secrets and variables → Actions → New repository secret

### Discord Configuration

1. **DISCORD_BOT_TOKEN** (Required)
   - Value: `YOUR_DISCORD_BOT_TOKEN_HERE`
   - Description: Discord bot token for authentication

2. **CHANNEL_ID** (Required)
   - Value: `YOUR_DISCORD_CHANNEL_ID`
   - Description: Primary Discord channel ID for posting

3. **GLOBAL_FALLBACK_CHANNEL_ID** (Required)
   - Value: `YOUR_FALLBACK_CHANNEL_ID`
   - Description: Fallback channel for unmapped feeds

4. **DISCORD_WEBHOOK_URL** (Optional)
   - Value: `YOUR_DISCORD_WEBHOOK_URL`
   - Description: Discord webhook URL for notifications

5. **SUMMARY_CHANNEL_ID** (Optional)
   - Value: (Set if you want summaries in a different channel)
   - Description: Channel ID for daily summaries

### Gemini AI Configuration

6. **GEMINI_API_KEY** (Required)
   - Value: `YOUR_GEMINI_API_KEY`
   - Description: Google Gemini API key for content processing

### Cloudflare R2 Configuration

7. **R2_BUCKET** (Optional)
   - Value: `YOUR_R2_BUCKET_NAME`
   - Description: Cloudflare R2 bucket name

8. **R2_ACCOUNT_ID** (Optional)
   - Value: `YOUR_R2_ACCOUNT_ID`
   - Description: Cloudflare R2 account ID

9. **R2_ACCESS_KEY_ID** (Optional)
   - Value: `YOUR_R2_ACCESS_KEY_ID`
   - Description: Cloudflare R2 access key ID

10. **R2_SECRET_ACCESS_KEY** (Optional)
    - Value: `YOUR_R2_SECRET_ACCESS_KEY`
    - Description: Cloudflare R2 secret access key

11. **R2_ENDPOINT** (Optional)
    - Value: `YOUR_R2_ENDPOINT_URL`
    - Description: Cloudflare R2 endpoint URL

12. **R2_PUBLIC_BASE** (Optional)
    - Value: `YOUR_R2_PUBLIC_BASE_URL`
    - Description: Public base URL for R2 content

13. **R2_MAX_BYTES** (Optional)
    - Value: `5000000000`
    - Description: Maximum file size for R2 uploads

### Bot Configuration

14. **MAX_AGE_HOURS** (Optional)
    - Value: `36`
    - Description: Maximum age of posts to process (in hours)

15. **FALLBACK_ENABLED** (Optional)
    - Value: `true`
    - Description: Enable fallback posting mechanism

16. **ADMIN_PASS** (Optional)
    - Value: `github-actions-secure`
    - Description: Admin password for bot management

## Quick Setup Commands

Copy and run these commands in your repository settings:

```bash
# Required secrets
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
CHANNEL_ID=YOUR_DISCORD_CHANNEL_ID
GLOBAL_FALLBACK_CHANNEL_ID=YOUR_FALLBACK_CHANNEL_ID
GEMINI_API_KEY=YOUR_GEMINI_API_KEY

# Optional secrets (R2 storage)
R2_BUCKET=YOUR_R2_BUCKET_NAME
R2_ACCOUNT_ID=YOUR_R2_ACCOUNT_ID
R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
R2_ENDPOINT=YOUR_R2_ENDPOINT_URL
R2_PUBLIC_BASE=YOUR_R2_PUBLIC_BASE_URL
R2_MAX_BYTES=5000000000

# Optional configuration
MAX_AGE_HOURS=36
FALLBACK_ENABLED=true
ADMIN_PASS=github-actions-secure
```

## Testing the Workflow

### Manual Trigger

1. Go to **Actions** tab in your repository
2. Select **HANU Feed Bot** workflow
3. Click **Run workflow**
4. Optionally configure:
   - Max age hours (default: 36)
   - Force run (to ignore lock files)
   - Debug mode (for verbose logging)

### Schedule

The workflow runs automatically every hour at minute 0 (e.g., 1:00, 2:00, 3:00, etc.).

## Monitoring

### Execution Logs

- Check the **Actions** tab for workflow runs
- Each run provides detailed logs and status
- Failed runs will show error details

### State Persistence

The workflow automatically commits state changes back to the repository:
- `seen.json` - Processed entries
- `details_threads.json` - Active Discord threads
- `avatar_cache.json` - Cached user avatars
- `feed_meta.json` - Feed metadata

### Artifacts

Each run uploads execution artifacts for debugging:
- Bot logs and state files
- Retained for 7 days
- Download from the Actions run page

## Security Notes

- All credentials are stored as encrypted secrets
- Secrets are only accessible during workflow execution
- Lock files prevent concurrent executions
- State changes are committed with `[skip ci]` to prevent loops

## Troubleshooting

### Common Issues

1. **Missing Secrets**: Ensure all required secrets are configured
2. **Permission Errors**: Verify Discord bot permissions
3. **Lock File Issues**: Use force run option if needed
4. **API Limits**: Check Gemini/Discord rate limits

### Manual Intervention

If the bot gets stuck:
1. Use the "Force run" option to ignore lock files
2. Check Discord channel permissions
3. Verify API keys are still valid
4. Review the execution logs for specific errors
