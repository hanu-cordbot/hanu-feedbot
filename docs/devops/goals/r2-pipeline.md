# Goal: R2 video pipeline
Status: todo

Purpose: Upload large videos reliably to R2, return public URLs, and maintain retention.

# Checklist:
- [ ] 4.1 Verify `r2/uploader.py` supports multipart uploads
- [ ] 4.2 Add integration tests (moto/mock) for uploads
- [ ] 4.3 Add workflow step to upload artifacts to R2 and capture URLs
- [ ] 4.4 Update post-processing to use R2 URLs in messages and dashboard

Human interventions:
- [HUMAN_REVIEW] R2 public URL exposure policy and retention settings
