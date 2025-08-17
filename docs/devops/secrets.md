# Secrets & Sensitive Data Handling

Purpose: Describe how to store and manage secrets and sensitive files (feeds.txt, tokens) for automation.

Principles
- Never print secret values to CI logs.
- Keep secrets in GitHub Actions Secrets or a secure vault (HashiCorp Vault, AWS Secrets Manager, etc.).
- Avoid committing runtime state into VCS when possible.

Required secrets (examples):
- DISCORD_BOT_TOKEN
- GEMINI_API_KEY
- CHANNEL_ID
- GLOBAL_FALLBACK_CHANNEL_ID
- R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT
- ADMIN_PASS
- GH_BOT_PAT (scoped, if you want CI to push state files back to the repo)

Feeds handling options
- Preferred: Upload `feeds.txt` to R2 and grant read access to CI/runtime only.
- Alternate: Encrypt `feeds.txt` with sops and decrypt in CI using secrets.
- Least preferred: Keep `feeds.txt` on the deployment host's filesystem (e.g., Railway `/data`) and do not commit it.

How to add GH_BOT_PAT
1. Create a GitHub Personal Access Token with `repo` scope (only `contents: write` is ideal). Keep it secret.
2. In the repository Settings -> Secrets -> Actions, add `GH_BOT_PAT` with the token value.

How to upload feeds to R2 (example using aws-cli):
```powershell
# Configure aws-cli with R2 credentials (or use environment variables)
aws --endpoint-url https://<account>.r2.cloudflarestorage.com s3 cp feeds.txt s3://<bucket>/feeds.txt
```

Notes
- Rotate tokens if you accidentally print or push them.
- If a secret exposure is suspected, follow the recovery steps in `docs/devops/goals/repo-hygiene.md`.

Seen state lifecycle guidance
- We compress `seen.json` before uploading to R2 to minimize storage size.
- Consider a lifecycle rule on the R2 bucket to automatically delete objects older than N days (e.g., 30 days) to avoid cost surprises.
- Alternatively, store only the last N GUIDs (code currently keeps last 500) and rely on expiration to limit cost.

Example lifecycle policy (Cloudflare R2/compatible):
 - Delete objects older than 30 days.

