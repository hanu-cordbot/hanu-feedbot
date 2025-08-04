# ELI5 Roadmap for Testing Deployment and Dashboard Integration

This is a simple step-by-step guide to make sure everything works on Railway (or local). We'll do one thing at a time.

## 1. Prepare Your Code
- Make sure your Flask app (`app.py`) has:
  1. A `Procfile` with:
     ```
     web: gunicorn app:app --bind 0.0.0.0:$PORT
     ```
  2. `requirements.txt` listing `flask`, `gunicorn`, and other dependencies.
  3. Your `app.run()` uses `port=int(os.environ.get('PORT', 5000))` and `host='0.0.0.0'`.

## 2. Update `index.html` and `dashboard.html`
- In both files, change any hard-coded fetch URL like `http://127.0.0.1:5000/api/...` back to relative paths, e.g.,
  ```js
  fetch('/api/public/feeds')
  ```
  so they work wherever the app is hosted.

## 3. Verify API Wrapper (`api.js`)
- Confirm `api.js` uses:
  ```js
  this.baseUrl = window.location.origin;
  ```
- Remove any old URLs. All calls should go to `/api/...` or `window.location.origin + '/api/...'`.

## 4. Commit & Push to GitHub
- `git add .`
- `git commit -m "Ready for Railway test: Procfile, relative URLs, baseUrl update"`
- `git push`

## 5. Link Repo on Railway
1. Create a new Railway project and connect your GitHub repo.
2. Set environment variables (Railway auto-sets `PORT`). Add:
   - `JOB_ENDPOINT` (your secret path)
   - `ADMIN_USER`, `ADMIN_PASS_HASH`, `DISCORD_BOT_TOKEN` if needed.
3. Deploy the project and watch the Logs.

## 6. Smoke Test the Public Page
1. Open the Railway URL in your browser (e.g. `https://your-app.up.railway.app/`).
2. It should show the public feed tracker page.
3. Check the browser console for errors (should see successful `GET /api/public/feeds`).

## 7. Smoke Test the Admin Dashboard
1. Go to `https://your-app.up.railway.app/dashboard.html`.
2. Log in with `ADMIN_USER` + `ADMIN_PASS_HASH` credentials.
3. Verify feeds, channels, and groups load.
4. Test adding/removing a feed or group.

## 8. Fix Any Issues
- If errors appear in the console or Logs, note them.
- We'll tackle each problem in order if anything breaks.

---

**Ready?** Let's start with Step 1: ensure your `Procfile` and `app.py` are configured correctly. Let me know when you're ready!
