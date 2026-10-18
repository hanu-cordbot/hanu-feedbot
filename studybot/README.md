# Study bot

An always-on Discord bot that turns your documents into a question bank people can learn from:

- **`/ingest deck file`**: upload a PDF, DOCX, TXT or MD. It's split into passages and stored in SQLite.
- **`/generate deck [count] [focus]`**: writes multiple-choice questions and vets each one before it's saved (see below).
- **`/quiz deck [count]`**: one question at a time, with A–D buttons. After each answer you see why it's right, *why each wrong option is wrong*, and the line from your material that backs it. Unseen questions come first, then ones you missed.
- **`/interview deck [focus] [rubric] [questions]`**: opens a thread and asks open-ended questions. Answer **by typing or with a Discord voice message** (hold the 🎤 button). Each answer is graded against your rubric (or a default one), with evidence for each score, what to fix, a full-marks model answer, and a follow-up question. Ends with a session summary.
- **`/share deck`**: posts the deck as a **standalone study pack** that anyone can use without the bot (details below).
- **`/decks`**, **`/stats [deck]`**, and a 🚩 button on every answered question. Two flags from different people pull a question from rotation.

## How questions are kept high quality

Each `/generate` runs a pipeline (`questions.py`) that is designed to discard drafts:

1. **Writer.** Gemini drafts questions from one passage. The prompt asks for understanding and application rather than trivia, and for self-contained stems. Every distractor must name the specific **misconception** that makes it tempting. The correct answer must quote its supporting sentence from your material verbatim.
2. **Local checks.** These reject cues a test-wise student could exploit: the correct answer being conspicuously the longest, "all/none of the above", duplicate options, "according to the passage", quotes that don't actually appear in the material, and near-duplicates of questions already in the deck.
3. **Blind solver.** A second call answers each question *without the key*. If it picks a different option, or says two are defensible, the question is ambiguous and gets dropped.
4. **Reviewer.** A strict reviewer scores grounding, ambiguity, distractor quality, learning value and standalone-ness from 1 to 5. Anything under 4 is rejected or repaired. A repaired question goes through the local checks again.
5. Options are **shuffled by code**, not by the model, so the key's position never carries a signal.

`/generate` reports how many drafts were written, how many survived, and sample reasons for rejections.

## Sharing material without the bot

Writing and vetting questions is the expensive part, and it only has to happen once. After that, a deck can live on its own as files:

- **`<deck>.html`** is a single self-contained page that works offline and on phones. It has an interactive quiz (missed questions come back first, and progress is saved in that browser) and a **review sheet** tab that prints cleanly as a paper handout.
- **`<deck>.anki.txt`** is a flashcard deck. Import it via Anki's *File → Import* for spaced repetition.

Get them with `/share deck` in Discord. To publish every deck on the existing GitHub Pages site with an index page, run:

```
python -m studybot.export --guild <server id> --out docs/study
```

Then commit `docs/study/`. The packs are served at `https://hanu-cordbot.github.io/hanu-feedbot/study/`. People can keep learning from them even while the bot is offline.

## Running it so it stays up

Restarting the bot does **not** invalidate its token. Discord resets a token only if:

- someone clicks **Reset Token** in the developer portal,
- the token is **published**, for example committed to a public GitHub repo (Discord scans GitHub and resets leaked tokens automatically), or
- the bot logs in **~1000 times in 24 hours**, which usually means a crash loop.

The bot guards against the last case. It counts its own logins in `data/studybot/logins.json` and waits rather than exceeding `STUDYBOT_MAX_LOGINS_PER_DAY` (default 200). discord.py also reconnects and resumes on its own after network drops, so a healthy process logs in once and stays up. Keep the token in `.env` or your host's secret settings, never in a file you commit.

GitHub Actions can't host this: jobs are capped at 6 hours, and the existing feed bot is designed to run once and exit. Pick something that runs continuously:

| Where | How |
|---|---|
| Any box with Docker (VPS, home server, Oracle Cloud free tier) | `docker compose -f studybot/docker-compose.yml up -d --build` (restarts automatically; data stays in a named volume) |
| Linux VM / Raspberry Pi without Docker | `studybot/deploy/studybot.service` (systemd, with restart back-off) |
| Railway / Fly.io / Render (background worker) | Build with `studybot/Dockerfile`, set the env vars, and attach a volume at `/data` so the database survives redeploys |
| Just trying it | `pip install -r studybot/requirements.txt && python -m studybot` |

### Setup

1. In the [Discord developer portal](https://discord.com/developers/applications): open your application, go to **Bot**, and enable **Message Content Intent**. You can reuse the feed bot's application or make a new one.
2. Invite it with the `bot` and `applications.commands` scopes, plus these permissions: Send Messages, Embed Links, Read Message History, Create Public Threads, Send Messages in Threads.
3. Set the following in `.env` (see `.env.example`):
   - `GEMINI_API_KEY`
   - `STUDYBOT_TOKEN` (falls back to `DISCORD_BOT_TOKEN`)
   - optionally `STUDYBOT_GUILD_ID`, so slash commands appear instantly in your server instead of within about an hour.
4. To limit who can `/ingest` or `/generate` (these cost API calls), use **Server Settings → Integrations → your bot**.

### Models

`STUDYBOT_GENERATION_MODEL` (default `gemini-2.5-pro`) writes, solves, reviews and grades. `STUDYBOT_FALLBACK_MODEL` (default `gemini-2.5-flash`) is used when the first model is rate limited. Quality is noticeably better on the larger model, and the pipeline makes 3 calls per passage.

## Limits / next steps

- Interview sessions live in memory. A restart ends any interview in progress, but decks, questions and quiz scores are on disk, and quiz buttons keep working across restarts.
- Scanned PDFs (images only) need OCR before upload.
- **Live voice-channel mode** (the bot listens in VC and talks back) isn't built yet. discord.py can't receive voice audio natively, so it needs `discord-ext-voice-recv` plus a text-to-speech engine. Voice messages in the interview thread cover the speak-and-get-graded loop today.
