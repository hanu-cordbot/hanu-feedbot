# Testing GitHub Actions Workflow

This guide helps you test the HANU Feed Bot GitHub Actions workflow.

## Pre-deployment Testing

Run the validation script locally:

```bash
python test_workflow_setup.py
```

This will check:
- ✅ Environment variables
- ✅ Required files
- ✅ Workflow YAML syntax
- ✅ Discord bot connection
- ✅ Feed parsing functionality

## Manual Workflow Testing

### 1. Trigger Manual Run

1. Go to your repository on GitHub
2. Navigate to **Actions** tab
3. Select **HANU Feed Bot** workflow
4. Click **Run workflow**
5. Configure options:
   - **Max age hours**: `36` (default)
   - **Force run**: `false` (default)
   - **Debug mode**: `true` (for testing)

### 2. Monitor Execution

Check the workflow run progress:
- Initial setup and validation
- Bot execution with live logs
- State file updates
- Cleanup and summary

### 3. Verify Results

After successful execution:
- Check Discord channel for new posts
- Verify state files were updated
- Download execution artifacts if needed

## Scheduled Execution

The workflow runs automatically every hour at minute 0:
- 1:00 AM, 2:00 AM, 3:00 AM, etc.
- Uses repository secrets for configuration
- Commits state changes back to repository

## Troubleshooting

### Common Issues

1. **Missing Secrets**
   ```
   Error: Missing required secrets: ['DISCORD_BOT_TOKEN', 'GEMINI_API_KEY']
   ```
   **Solution**: Configure all required secrets in repository settings

2. **Permission Denied**
   ```
   Error: Bot doesn't have permission to send messages
   ```
   **Solution**: Check Discord bot permissions in target channel

3. **Lock File Issues**
   ```
   Error: Another bot instance is already running
   ```
   **Solution**: Use "Force run" option or wait for lock timeout

4. **API Rate Limits**
   ```
   Error: Too Many Requests (429)
   ```
   **Solution**: Bot will retry automatically; consider increasing MAX_AGE_HOURS

### Debug Mode

Enable debug mode for verbose logging:
- Set `debug_mode: true` in manual trigger
- Check detailed execution logs
- Monitor resource usage and timing

### State Management

The workflow manages these state files:
- `seen.json` - Processed entries (prevents duplicates)
- `details_threads.json` - Active Discord threads
- `avatar_cache.json` - Cached user avatars
- `feed_meta.json` - Feed metadata

These files are automatically committed back to the repository.

## Monitoring Checklist

- [ ] Workflow runs successfully on schedule
- [ ] Bot posts new content to Discord
- [ ] State files are updated correctly
- [ ] No permission or API errors
- [ ] Execution time under 30 minutes
- [ ] Lock files are cleaned up properly

## Emergency Procedures

### Stop Scheduled Runs
1. Go to **Actions** → **HANU Feed Bot**
2. Click **Disable workflow**
3. Manually remove lock files if needed

### Force Manual Run
1. Use `force_run: true` option
2. This ignores existing lock files
3. Useful for stuck processes

### Reset State
If the bot gets stuck in a bad state:
1. Delete problematic state files from repository
2. Run workflow with `force_run: true`
3. Monitor next few executions

## Performance Monitoring

Track these metrics:
- **Execution time**: Should be under 10 minutes normally
- **Memory usage**: Monitor for memory leaks
- **API calls**: Stay within Discord/Gemini limits
- **Error rate**: Should be minimal

## Success Indicators

A healthy workflow shows:
- ✅ Regular hourly executions
- ✅ New posts in Discord channels
- ✅ State files being updated
- ✅ No recurring errors
- ✅ Execution times consistent
