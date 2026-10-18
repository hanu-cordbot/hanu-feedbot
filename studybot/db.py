"""SQLite storage: decks of source material, vetted questions, and learner history."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
    id INTEGER PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT 'general',
    created_by INTEGER,
    created_at REAL NOT NULL,
    UNIQUE (guild_id, name)
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    added_by INTEGER,
    added_at REAL NOT NULL,
    UNIQUE (deck_id, sha256)
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    deck_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    text TEXT NOT NULL,
    times_used INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    deck_id INTEGER NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
    chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    stem TEXT NOT NULL,
    options_json TEXT NOT NULL,
    correct_index INTEGER NOT NULL,
    explanation TEXT NOT NULL,
    rationales_json TEXT NOT NULL,
    source_quote TEXT,
    difficulty TEXT,
    cognitive_level TEXT,
    review_score REAL,
    origin TEXT NOT NULL DEFAULT 'generated',
    answer_source TEXT NOT NULL DEFAULT 'ai',
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    flags INTEGER NOT NULL DEFAULT 0,
    retired INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    chosen_index INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    answered_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS attempts_user ON attempts(user_id, question_id);
CREATE TABLE IF NOT EXISTS question_ratings (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    value INTEGER NOT NULL,
    PRIMARY KEY (question_id, user_id)
);
CREATE TABLE IF NOT EXISTS quiz_runs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    question_ids TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS quiz_prefs (
    user_id INTEGER PRIMARY KEY,
    settings TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS question_flags (
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    reason TEXT,
    PRIMARY KEY (question_id, user_id)
);
"""

# A question is pulled from rotation once this many different people flag it.
FLAGS_TO_RETIRE = 2


class Store:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        deck_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(decks)")}
        if "subject" not in deck_cols:
            self.conn.execute("ALTER TABLE decks ADD COLUMN subject TEXT NOT NULL DEFAULT 'general'")
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(questions)")}
        for name, ddl in (
            ("origin", "origin TEXT NOT NULL DEFAULT 'generated'"),
            ("answer_source", "answer_source TEXT NOT NULL DEFAULT 'ai'"),
            ("document_id", "document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL"),
        ):
            if name not in cols:
                self.conn.execute(f"ALTER TABLE questions ADD COLUMN {ddl}")
        run_cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(quiz_runs)")}
        for name, ddl in (
            ("settings", "settings TEXT NOT NULL DEFAULT '{}'"),
            ("picks", "picks TEXT NOT NULL DEFAULT '[]'"),
            ("asked_at", "asked_at REAL NOT NULL DEFAULT 0"),
        ):
            if name not in run_cols:
                self.conn.execute(f"ALTER TABLE quiz_runs ADD COLUMN {ddl}")
        self.conn.commit()

    # --- decks -----------------------------------------------------------
    def get_or_create_deck(
        self, guild_id: int, name: str, user_id: Optional[int] = None, subject: Optional[str] = None
    ) -> int:
        """Finds or creates a question set. A given subject is applied to existing sets too."""
        name = name.strip().lower()
        subject = subject.strip().lower() if subject and subject.strip() else None
        row = self.conn.execute(
            "SELECT id FROM decks WHERE guild_id = ? AND name = ?", (guild_id, name)
        ).fetchone()
        if row:
            if subject:
                self.conn.execute("UPDATE decks SET subject = ? WHERE id = ?", (subject, row["id"]))
                self.conn.commit()
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO decks (guild_id, name, subject, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (guild_id, name, subject or "general", user_id, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_deck(self, deck_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM decks WHERE id = ?", (deck_id,)).fetchone()

    def set_deck_subject(self, deck_id: int, subject: str) -> None:
        self.conn.execute("UPDATE decks SET subject = ? WHERE id = ?", (subject.strip().lower() or "general", deck_id))
        self.conn.commit()

    def rename_deck(self, deck_id: int, name: str) -> bool:
        """False if another set in the server already has that name."""
        try:
            self.conn.execute("UPDATE decks SET name = ? WHERE id = ?", (name.strip().lower(), deck_id))
        except sqlite3.IntegrityError:
            return False
        self.conn.commit()
        return True

    def subjects(self, guild_id: int, prefix: str = "") -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT subject FROM decks WHERE guild_id = ? AND subject LIKE ? ORDER BY subject LIMIT 25",
            (guild_id, prefix.lower() + "%"),
        ).fetchall()
        return [r["subject"] for r in rows]

    def library(self, guild_id: int) -> list[sqlite3.Row]:
        """Every question set with counts for each provenance label, grouped by subject."""
        return self.conn.execute(
            """
            SELECT d.id, d.name, d.subject,
                   COUNT(q.id) AS questions,
                   COALESCE(SUM(q.origin = 'extracted' AND q.answer_source = 'document'), 0) AS from_file,
                   COALESCE(SUM(q.origin = 'extracted' AND q.answer_source = 'ai'), 0) AS ai_answer,
                   COALESCE(SUM(q.origin = 'generated'), 0) AS ai_written,
                   COALESCE(SUM((SELECT COALESCE(SUM(value), 0) FROM question_ratings r
                                 WHERE r.question_id = q.id) >= 2), 0) AS favourites
            FROM decks d LEFT JOIN questions q ON q.deck_id = d.id AND q.retired = 0
            WHERE d.guild_id = ?
            GROUP BY d.id ORDER BY d.subject, d.name
            """,
            (guild_id,),
        ).fetchall()

    def find_deck(self, guild_id: int, name: str) -> Optional[int]:
        row = self.conn.execute(
            "SELECT id FROM decks WHERE guild_id = ? AND name = ?",
            (guild_id, name.strip().lower()),
        ).fetchone()
        return row["id"] if row else None

    def list_decks(self, guild_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT d.id, d.name,
                   (SELECT COUNT(*) FROM documents WHERE deck_id = d.id) AS docs,
                   (SELECT COUNT(*) FROM questions WHERE deck_id = d.id AND retired = 0) AS questions,
                   (SELECT COUNT(*) FROM questions WHERE deck_id = d.id AND retired = 0
                    AND (origin = 'generated' OR answer_source = 'ai')) AS ai_questions
            FROM decks d WHERE d.guild_id = ? ORDER BY d.name
            """,
            (guild_id,),
        ).fetchall()

    def deck_names(self, guild_id: int, prefix: str = "") -> list[str]:
        rows = self.conn.execute(
            "SELECT name FROM decks WHERE guild_id = ? AND name LIKE ? ORDER BY name LIMIT 25",
            (guild_id, prefix.lower() + "%"),
        ).fetchall()
        return [r["name"] for r in rows]

    # --- documents and chunks -------------------------------------------
    def add_document(
        self, deck_id: int, filename: str, sha256: str, chunks: list[str], user_id: Optional[int]
    ) -> Optional[int]:
        """Stores a document's chunks. Returns None if the same file is already in the deck."""
        try:
            cur = self.conn.execute(
                """INSERT INTO documents (deck_id, filename, sha256, char_count, added_by, added_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (deck_id, filename, sha256, sum(len(c) for c in chunks), user_id, time.time()),
            )
        except sqlite3.IntegrityError:
            return None
        doc_id = cur.lastrowid
        self.conn.executemany(
            "INSERT INTO chunks (document_id, deck_id, position, text) VALUES (?, ?, ?, ?)",
            [(doc_id, deck_id, i, text) for i, text in enumerate(chunks)],
        )
        self.conn.commit()
        return doc_id

    def pick_chunks(self, deck_id: int, limit: int, focus: Optional[str] = None) -> list[sqlite3.Row]:
        """Chooses source passages, preferring ones least used so coverage spreads out."""
        if focus:
            terms = " OR ".join(f'"{w}"' for w in focus.replace('"', " ").split() if w)
            if terms:
                rows = self.conn.execute(
                    """
                    SELECT c.* FROM chunks_fts f JOIN chunks c ON c.id = f.rowid
                    WHERE chunks_fts MATCH ? AND c.deck_id = ?
                    ORDER BY c.times_used, bm25(chunks_fts) LIMIT ?
                    """,
                    (terms, deck_id, limit),
                ).fetchall()
                if rows:
                    return rows
        return self.conn.execute(
            "SELECT * FROM chunks WHERE deck_id = ? ORDER BY times_used, RANDOM() LIMIT ?",
            (deck_id, limit),
        ).fetchall()

    def mark_chunk_used(self, chunk_id: int) -> None:
        self.conn.execute("UPDATE chunks SET times_used = times_used + 1 WHERE id = ?", (chunk_id,))
        self.conn.commit()

    def existing_stems(self, deck_id: int, limit: int = 60) -> list[str]:
        rows = self.conn.execute(
            "SELECT stem FROM questions WHERE deck_id = ? ORDER BY id DESC LIMIT ?",
            (deck_id, limit),
        ).fetchall()
        return [r["stem"] for r in rows]

    # --- questions -------------------------------------------------------
    def add_question(
        self, deck_id: int, chunk_id: Optional[int], q: dict, document_id: Optional[int] = None
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO questions (deck_id, chunk_id, stem, options_json, correct_index,
                   explanation, rationales_json, source_quote, difficulty, cognitive_level,
                   review_score, origin, answer_source, document_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                deck_id,
                chunk_id,
                q["stem"],
                json.dumps(q["options"]),
                q["correct_index"],
                q["explanation"],
                json.dumps(q["rationales"]),
                q.get("source_quote"),
                q.get("difficulty"),
                q.get("cognitive_level"),
                q.get("review_score"),
                q.get("origin", "generated"),
                q.get("answer_source", "ai"),
                document_id,
                time.time(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_question(self, question_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
        return _question_dict(row) if row else None

    def next_questions(
        self, deck_id: int, user_id: int, count: int, skip_recent_seconds: float = 0
    ) -> list[dict]:
        """Unseen questions first, then ones this user last got wrong, then the rest.
        Questions answered within `skip_recent_seconds` are left out so a quiz doesn't repeat itself."""
        cutoff = time.time() - skip_recent_seconds if skip_recent_seconds else None
        rows = self.conn.execute(
            """
            SELECT q.*,
                   (SELECT a.correct FROM attempts a WHERE a.question_id = q.id AND a.user_id = ?
                    ORDER BY a.answered_at DESC LIMIT 1) AS last_correct,
                   (SELECT MAX(a.answered_at) FROM attempts a
                    WHERE a.question_id = q.id AND a.user_id = ?) AS last_seen
            FROM questions q
            WHERE q.deck_id = ? AND q.retired = 0 AND (? IS NULL OR last_seen IS NULL OR last_seen < ?)
            ORDER BY
                CASE WHEN last_correct IS NULL THEN 0 WHEN last_correct = 0 THEN 1 ELSE 2 END,
                last_seen, RANDOM()
            LIMIT ?
            """,
            (user_id, user_id, deck_id, cutoff, cutoff, count),
        ).fetchall()
        return [_question_dict(r) for r in rows]

    def question_pool(self, deck_ids: list[int], user_id: Optional[int] = None) -> list[dict]:
        """Questions in rotation from these sets, with ratings, and this user's last result."""
        if not deck_ids:
            return []
        marks = ",".join("?" * len(deck_ids))
        rows = self.conn.execute(
            f"""
            SELECT q.*,
                   (SELECT COALESCE(SUM(value), 0) FROM question_ratings r WHERE r.question_id = q.id) AS net_rating,
                   (SELECT a.correct FROM attempts a WHERE a.question_id = q.id AND a.user_id = ?
                    ORDER BY a.answered_at DESC LIMIT 1) AS last_correct
            FROM questions q
            WHERE q.deck_id IN ({marks}) AND q.retired = 0
            ORDER BY q.id
            """,
            (user_id or 0, *deck_ids),
        ).fetchall()
        return [_question_dict(r) for r in rows]

    def deck_questions(self, deck_id: int) -> list[dict]:
        """Every question still in rotation, for exporting."""
        return self.question_pool([deck_id])

    def deck_subject(self, deck_id: int) -> str:
        row = self.conn.execute("SELECT subject FROM decks WHERE id = ?", (deck_id,)).fetchone()
        return row["subject"] if row else "general"

    def rate_question(self, question_id: int, user_id: int, value: int) -> int:
        """Records a 👍 (+1) or 👎 (-1), replacing this user's earlier vote. Returns the net rating."""
        self.conn.execute(
            "INSERT OR REPLACE INTO question_ratings (question_id, user_id, value) VALUES (?, ?, ?)",
            (question_id, user_id, 1 if value > 0 else -1),
        )
        self.conn.commit()
        return self.conn.execute(
            "SELECT COALESCE(SUM(value), 0) FROM question_ratings WHERE question_id = ?", (question_id,)
        ).fetchone()[0]

    # --- solo quiz runs (persisted so private quizzes survive restarts) ---
    def create_run(self, user_id: int, question_ids: list[int], settings: Optional[dict] = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO quiz_runs (user_id, question_ids, settings, created_at) VALUES (?, ?, ?, ?)",
            (user_id, json.dumps(question_ids), json.dumps(settings or {}), time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_run(self, run_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM quiz_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        run["question_ids"] = json.loads(run["question_ids"])
        run["settings"] = json.loads(run.get("settings") or "{}")
        run["picks"] = json.loads(run.get("picks") or "[]")
        return run

    def advance_run(self, run_id: int, expected_position: int, correct: bool, pick: Optional[int] = None) -> bool:
        """Moves a run past one answer. False if that position was already answered (double click).
        `pick` is the stored option index chosen (None for a timeout), kept for the end-of-quiz review."""
        cur = self.conn.execute(
            "UPDATE quiz_runs SET position = position + 1, correct = correct + ?, "
            "picks = json_insert(COALESCE(picks, '[]'), '$[#]', ?) WHERE id = ? AND position = ?",
            (int(correct), pick, run_id, expected_position),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def mark_asked(self, run_id: int, when: float) -> None:
        """When the current question was shown, for the solo timer."""
        self.conn.execute("UPDATE quiz_runs SET asked_at = ? WHERE id = ?", (when, run_id))
        self.conn.commit()

    def get_prefs(self, user_id: int) -> dict:
        row = self.conn.execute("SELECT settings FROM quiz_prefs WHERE user_id = ?", (user_id,)).fetchone()
        return json.loads(row["settings"]) if row else {}

    def set_prefs(self, user_id: int, settings: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO quiz_prefs (user_id, settings) VALUES (?, ?)", (user_id, json.dumps(settings))
        )
        self.conn.commit()

    def deck_sources(self, deck_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT filename FROM documents WHERE deck_id = ? ORDER BY added_at", (deck_id,)
        ).fetchall()
        return [r["filename"] for r in rows]

    def record_attempt(self, question_id: int, user_id: int, chosen: int, correct: bool) -> None:
        self.conn.execute(
            """INSERT INTO attempts (question_id, user_id, chosen_index, correct, answered_at)
               VALUES (?, ?, ?, ?, ?)""",
            (question_id, user_id, chosen, int(correct), time.time()),
        )
        self.conn.commit()

    def flag_question(self, question_id: int, user_id: int, reason: str = "") -> bool:
        """Records a flag. Returns True if this flag retired the question."""
        self.conn.execute(
            "INSERT OR IGNORE INTO question_flags (question_id, user_id, reason) VALUES (?, ?, ?)",
            (question_id, user_id, reason),
        )
        flags = self.conn.execute(
            "SELECT COUNT(*) FROM question_flags WHERE question_id = ?", (question_id,)
        ).fetchone()[0]
        retired = flags >= FLAGS_TO_RETIRE
        self.conn.execute(
            "UPDATE questions SET flags = ?, retired = MAX(retired, ?) WHERE id = ?",
            (flags, int(retired), question_id),
        )
        self.conn.commit()
        return retired

    def user_stats(self, user_id: int, deck_id: Optional[int] = None) -> sqlite3.Row:
        where, args = "a.user_id = ?", [user_id]
        if deck_id is not None:
            where += " AND q.deck_id = ?"
            args.append(deck_id)
        return self.conn.execute(
            f"""SELECT COUNT(*) AS answered, COALESCE(SUM(a.correct), 0) AS correct,
                       COUNT(DISTINCT a.question_id) AS distinct_questions
                FROM attempts a JOIN questions q ON q.id = a.question_id WHERE {where}""",
            args,
        ).fetchone()


def _question_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["options"] = json.loads(d.pop("options_json"))
    d["rationales"] = json.loads(d.pop("rationales_json"))
    return d
