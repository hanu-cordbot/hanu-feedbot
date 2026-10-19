# Study bot

An always-on Discord bot that turns the files you already have into quizzes people can learn from.

## The simple version

1. **`/upload file`**: drop in a past paper, worksheet, slide deck, notes, or a photo of a printed quiz.
   - **Questions already in the file are pulled out as written.** Nothing is rewritten, and the deck is named after the file unless you choose a name.
   - **Answers come from the file** wherever it puts them: `Answer: B` lines, an *Answer key* section at the end, a starred `*` / `(correct)` option, or a **bold or highlighted** option in Word files.
   - **No answer in the file?** AI suggests one, and that question is marked **⚠️ answer suggested by AI** everywhere it appears.
   - **No questions in the file at all?** It's saved as study material, and the bot warns that AI-written questions can be wrong. You choose whether to have AI write some; those are marked **⚠️ AI-written**.
2. **`/quiz`**: opens a private settings panel, and remembers your last settings:
   - **What to play:** subject, question sets, which questions (all / only answers from the file / skip AI-written), order (🧠 smart mix / 🎲 random / 📑 file order), length (5–50 or every question), timer (none, or 5–120 s) and auto-advance (live: next question 3–30 s after the answer, or the host presses Next).
   - **Options (on/off):** 🔀 shuffle answer choices · 👀 show the answer after each question (solo; off = review at the end) · 🖼️ Quizizz-style cards.
   - **Live game extras** (one multi-select): 🏆 leaderboard after each question · ⏱️ faster answers score more (off = 1,000 per right answer) · 🔥 streak bonus · ⚡ power-ups · 🎵 music in voice.
   - **🧑‍🎓 Solo (private)**: only you see the questions, your picks and your score. With a timer, late answers count as missed. Questions you missed come up more often. Solo quizzes keep working after a bot restart.
   - **🎮 Live for everyone** (Quizizz-style): the whole game is one channel message: the question card, a countdown and **"🙋 N answered"**, with A/B/C/D right on it. A click is private, so nobody sees anyone's pick; you get a private reply with your points and rank. When time runs out (or the host presses ⏭) the card reveals the answer and how many picked each tile, plus a leaderboard; **📊 My result** shows your own pick, points and rank. The game ends with a podium. Only the host can move on or end the game. Works in threads too.
   - **⚡ Power-ups** (live): everyone gets a random one with their first answer and another for every 3 right in a row (hold up to 3). **⚡ Power-ups** on the game message opens your private menu. 🌗 50-50 and 🧽 Eraser remove wrong answers for you · 🛡️ Immunity gives a second try · ⏸️ Time Freeze stops your clock (full speed points) · ✌️ 2x doubles your points · 🎲 Double Jeopardy doubles them, or takes that much away if you're wrong · 🔒 Streak Saver keeps your streak through a wrong answer · 📈 Streak Booster adds 2 to your streak · 🚀 Supersonic gives +50% on your next 3 right answers · ⚡ Power Play gives everyone +50% on that question · 🎁 Gift hands 800 points to a random player. Power Play and Gift are announced on the game message. Quizizz doesn't publish exact numbers; these follow how its power-ups are usually described.
   - **🎵 Music** (live): if the host is in a voice channel when the game starts, the bot joins it and plays a question loop, a sting on each reveal, a calmer loop between questions and a fanfare at the end, then leaves (or after 10 idle minutes on one answer screen). The music is synthesised by the bot (original, nothing to license). Put your own audio files (mp3/ogg/wav/flac/m4a) in `data/studybot/music/` to use them as the question loop instead, picked at random per game. Needs ffmpeg and libopus on the host.
   - **Cards:** each question is drawn as a Quizizz-style picture (coloured answer tiles, with buttons in matching colours). Long answers switch to a 2×2 grid and the card grows taller rather than cutting text. Turn cards off for plain text.
3. **`/library`**: every subject and question set, with label counts.
4. **`/share deck`**: a standalone study page and an Anki file anyone can use without the bot.

### Labels and "better questions first"

| Label | Meaning |
|---|---|
| 📄 | Question and answer both from your file |
| 🤖 | Question from your file, answer suggested by AI |
| ✨ | Question written by AI |
| ⭐ | Community favourite (net 👍 of 2 or more) |
| 🚩 | Someone flagged it (two flags pull it from rotation) |

After every answer you can rate the question 👍 / 👎 or flag it 🚩. Each question's score is +2 for 📄, 0 for 🤖 and −1 for ✨, plus its net rating, minus 2 per flag. Higher-scoring questions are drawn more often. Negative ones are only used when a set would otherwise run short.

Subjects are set with `/upload file subject:biology`. Uploading again with a different subject moves the set. Each subject gets an emoji automatically: 🧬 ⚗️ ⚛️ 📐 🏛️ 📖 💻 🌍 📈 🗣️ 🎨 🎵 ⚖️ 🩺 🧠, or 📚 when no keyword matches.

Also available: `/interview` (answer out loud with a voice message and get graded on a rubric), `/generate` (ask AI for more questions), and `/stats`.

### How questions are found in a file

| File | What happens |
|---|---|
| Clean layouts (numbered or not, `A.` `a)` `(A)` options, options on one line, answer lines, answer keys) | Read by a plain parser. No AI involved, and nothing can be invented. |
| Messy layouts the parser can't fully account for (tables, odd formatting) | Gemini *copies* the questions out, with explicit instructions not to write or fix anything. Every copied question is then **checked against the file's own text**, and anything that doesn't match is discarded. |
| Photos, screenshots, scanned PDFs (no text layer) | Gemini reads the image and copies the questions out. These can't be checked against text, so give them a quick look. |

Supported files: PDF, DOCX, PPTX, TXT/MD/CSV/HTML, JSON, PNG/JPG/WEBP/HEIC. JSON question banks (any object with a question, a list of options and, optionally, an answer such as `{"q", "options", "correctIndex", "explanation"}`, at any depth) are read directly with no AI; other JSON is read as text. Questions with 2–6 options are supported.

## How AI-written questions are vetted (`/generate`)

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
2. Invite it with the `bot` and `applications.commands` scopes, plus these permissions: Send Messages, Embed Links, Attach Files, Read Message History, Create Public Threads, Send Messages in Threads, and Connect + Speak for game music.
3. Set the following in `.env` (see `.env.example`):
   - nothing for the model by default: it runs GPT Luna through the Codex CLI (see **Models**). For Gemini instead, set `STUDYBOT_PROVIDER=gemini` and `GEMINI_API_KEY`.
   - `STUDYBOT_TOKEN` (falls back to `DISCORD_BOT_TOKEN`)
   - optionally `STUDYBOT_GUILD_ID`, so slash commands appear instantly in your server instead of within about an hour.
4. To limit who can `/upload` or `/generate` (these cost API calls), use **Server Settings → Integrations → your bot**.

### Models

By default (`STUDYBOT_PROVIDER=codex`) every model call runs `codex exec -m gpt-6-luna` using the Codex CLI's ChatGPT login, so no API key is needed. The catch is that the bot has to run on a machine where `codex login` has been done, and every call counts against that account's Codex quota. Each call runs in an empty temp dir with a read-only sandbox, with hooks and memories turned off. Images go to Luna directly; scanned PDFs are rendered to page images first (`pdftoppm`, from poppler-utils). Luna can't hear audio, so interview voice answers use Gemini when `GEMINI_API_KEY` is set and are refused otherwise (text answers always work). Options: `STUDYBOT_CODEX_MODEL` (default `gpt-6-luna`), `STUDYBOT_CODEX_EFFORT` (default `medium`), `STUDYBOT_CODEX_TIMEOUT` (seconds, default 300), and `STUDYBOT_CODEX_MAX_PAGES` (default 20). A three-question `/generate` pass takes about 30 s on Luna.

With `STUDYBOT_PROVIDER=gemini`, `STUDYBOT_GENERATION_MODEL` (default `gemini-2.5-pro`) writes, solves, reviews and grades. `STUDYBOT_FALLBACK_MODEL` (default `gemini-2.5-flash`) is used when the first model is rate limited. Quality is noticeably better on the larger model, and the pipeline makes 3 calls per passage.

## Limits / next steps

- Interviews and live games live in memory, so a restart ends any that are in progress (old live buttons then say the game has ended). Sets, questions, ratings, scores and solo quizzes are on disk and survive restarts.
- **Live voice-channel mode** (the bot listens in VC and talks back) isn't built yet. discord.py can't receive voice audio natively, so it needs `discord-ext-voice-recv` plus a text-to-speech engine. Voice messages in the interview thread cover the speak-and-get-graded loop today.
