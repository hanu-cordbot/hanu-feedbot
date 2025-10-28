# R2 Video Storage Documentation

## Overview
The HANU Feed Bot now uses Cloudflare R2 storage for large videos (>8MB) instead of relying solely on Catbox. This provides better reliability, performance, and organization of video content.

## How It Works

### File Size Handling
- **Small videos (<8MB)**: Uploaded directly to Discord as file attachments
- **Large videos (>8MB)**: Uploaded to R2 bucket and embedded via public URL
- **Fallback**: If R2 fails, system falls back to Catbox, then graceful failure

### Storage Structure
Videos are stored in R2 with the following structure:
```
videos/
├── 20250824_Facebook_Video_Post_a1b2c3d4.mp4
├── 20250824_News_Update_e5f6g7h8.mp4
└── 20250825_Event_Announcement_i9j0k1l2.mp4
```

**Filename Format**: `videos/{YYYYMMDD}_{clean_title}_{8_char_hash}.mp4`

### Discord Embedding
Discord now receives the raw video URL on its own line so the client auto-embeds the mp4 preview. The post title and original source link are included above and below the mirror:
```
**Video Title**
https://pub-xxxxx.r2.dev/videos/20250824_Video_Title_12345678.mp4
Original: https://facebook.com/post/12345
```

## Configuration

### Required Environment Variables
```bash
# R2 Basic Configuration (required)
R2_BUCKET=your_bucket_name
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_ENDPOINT=https://your_account_id.r2.cloudflarestorage.com

# R2 Public URL (required for video embeds)
R2_PUBLIC_URL=https://pub-xxxxx.r2.dev
```

### R2 Bucket Setup
1. Create a Cloudflare R2 bucket
2. Configure public access for the bucket
3. Set up a custom domain (recommended) or use the default R2 public URL
4. Add the `R2_PUBLIC_URL` environment variable

## Technical Details

### Thread Media Posting Fix
The dispatcher logic was restructured to properly handle Discord threads:
- **Forum channels**: Create new threads with media as the first message
- **Existing threads**: Post media directly into the thread
- **Text channels**: Post media directly to the channel

### Error Handling
The system includes comprehensive error handling:
1. **R2 upload fails**: Falls back to Catbox
2. **Catbox upload fails**: Logs error and continues
3. **Video too large**: Skips with warning
4. **Download fails**: Continues with other media

### Performance Improvements
- Async video uploads don't block other operations
- Centralized file size limit management
- Efficient filename generation with collision prevention

## Monitoring

### Logs to Watch For
- `📤 Uploading to R2: filename.mp4 (XX.XMB)` - R2 upload started
- `✅ Video uploaded to R2: https://...` - R2 upload successful
- `⚠️ R2 upload failed, falling back to Catbox...` - Fallback triggered
- `❌ Both R2 and Catbox upload failed` - Complete failure

### File Organization
Videos are automatically organized by date, making it easy to:
- Monitor storage usage over time
- Clean up old content if needed
- Track video posting patterns

## Maintenance

### Automatic Storage Guardrail
Before each upload, the bot checks total usage with the R2 `list_objects_v2` paginator. When usage exceeds 90% of the configured 4.9GB soft cap, it automatically deletes the oldest objects until usage drops below 70%. This keeps the mirror operational without manual intervention.

### Storage Monitoring
Monitor your R2 bucket usage in the Cloudflare dashboard to ensure you stay within your storage limits. The automatic cleanup is intentionally conservative; raise or lower the threshold in `bot/r2_video.py` if your bucket allows more or less headroom.

## Benefits

1. **Reliability**: R2 is more reliable than third-party services like Catbox
2. **Performance**: Direct video embedding works better than external links
3. **Organization**: Systematic file naming and storage structure
4. **Control**: Full control over video storage and access
5. **Cost-effective**: R2 pricing is competitive for video storage
6. **Discord-friendly**: Videos embed properly with thumbnails and play controls
