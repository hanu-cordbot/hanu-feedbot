# Goal: R2 video pipeline
Status: in-progress

Purpose: Upload large videos reliably to R2, return public URLs, and maintain retention.

# Checklist:
- [x] 4.1 Verify `r2/uploader.py` supports multipart uploads (implemented in dispatcher.py)
- [ ] 4.2 Add integration tests (moto/mock) for uploads
- [ ] 4.3 Add workflow step to upload artifacts to R2 and capture URLs
- [x] 4.4 Update post-processing to use R2 URLs in messages and dashboard (completed - R2 URLs used in video embeds)

Human interventions:
- [HUMAN_REVIEW] R2 public URL exposure policy and retention settings
