import asyncio
import json
import random
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from studybot import ingest, questions  # noqa: E402
from studybot.db import Store  # noqa: E402

PASSAGE = (
    "Enzymes speed up reactions by lowering the activation energy required for the reaction to proceed. "
    "They do not change the equilibrium position of a reaction. Competitive inhibitors bind to the active site "
    "and can be overcome by increasing substrate concentration, whereas non-competitive inhibitors bind elsewhere "
    "and reduce the maximum rate regardless of how much substrate is added. Temperature increases reaction rate "
    "until the enzyme denatures, after which activity falls sharply."
)


def draft(**overrides):
    q = {
        "stem": "A drug binds an enzyme's active site. What happens if you greatly increase substrate concentration?",
        "correct_answer": "The inhibition is largely overcome",
        "distractors": [
            {"text": "The maximum rate falls permanently", "misconception": "Confuses competitive with non-competitive"},
            {"text": "The equilibrium shifts toward products", "misconception": "Thinks enzymes move equilibrium"},
            {"text": "The enzyme denatures more quickly", "misconception": "Mixes up substrate and temperature effects"},
        ],
        "explanation": "Competitive inhibitors compete for the active site, so more substrate outcompetes them.",
        "source_quote": "Competitive inhibitors bind to the active site and can be overcome by increasing substrate concentration",
        "difficulty": "medium",
        "cognitive_level": "apply",
    }
    q.update(overrides)
    return q


def test_chunking_keeps_paragraphs_and_overlaps():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(20))
    chunks = ingest.chunk_text(text, size=1500, overlap=200)
    assert len(chunks) > 3
    assert all(len(c) <= 1500 + 200 + 10 for c in chunks)
    assert all(f"Paragraph {i}." in text for i in range(20))
    joined = " ".join(chunks)
    assert all(f"Paragraph {i}." in joined for i in range(20))


def test_extract_plain_text_and_rejects_unknown():
    assert ingest.extract_text("notes.md", b"Hello\r\n\r\n\r\nworld") == "Hello\n\nworld"
    try:
        ingest.extract_text("song.mp3", b"x")
    except ingest.UnsupportedFile:
        pass
    else:
        raise AssertionError("expected UnsupportedFile")


def test_local_checks_accept_good_and_catch_cues():
    assert questions.local_problems(draft(), PASSAGE, []) is None
    assert "all/none" in questions.local_problems(
        draft(distractors=[*draft()["distractors"][:2], {"text": "All of the above", "misconception": "x"}]), PASSAGE, []
    )
    assert "longest" in questions.local_problems(
        draft(correct_answer="The inhibition is largely overcome because substrate molecules outcompete the inhibitor for the site"),
        PASSAGE,
        [],
    )
    assert "quote" in questions.local_problems(draft(source_quote="Enzymes are made of DNA and act as genes in the nucleus"), PASSAGE, [])
    assert "duplicate" in questions.local_problems(draft(), PASSAGE, [draft()["stem"]])
    assert "refers to the source" in questions.local_problems(draft(stem="According to the passage, what do enzymes do?"), PASSAGE, [])


def test_shuffle_tracks_correct_answer():
    for seed in range(10):
        q = questions.shuffle_options(draft(), random.Random(seed))
        assert q["options"][q["correct_index"]] == "The inhibition is largely overcome"
        assert q["rationales"][q["correct_index"]] == ""
        assert sorted(q["options"]) == sorted([draft()["correct_answer"]] + [d["text"] for d in draft()["distractors"]])


def test_pipeline_drops_questions_the_blind_solver_gets_wrong(monkeypatch):
    calls = []

    async def fake_generate_json(prompt, *, system, audio=None, temperature=0.7, tries=3):
        calls.append(system)
        if system == questions.WRITER_SYSTEM:
            return {"questions": [draft(), draft(stem="Which change would raise an enzyme's activity until it suddenly collapses?",
                                              correct_answer="Raising the temperature",
                                              source_quote="Temperature increases reaction rate until the enzyme denatures")]}
        if system == questions.SOLVER_SYSTEM:
            items = json.loads(prompt.split("QUESTIONS:\n", 1)[1].split("\n\nFor each", 1)[0])
            answers = []
            for item in items:
                letter = next(k for k, v in item["options"].items() if v in ("The inhibition is largely overcome", "Raising the temperature"))
                # Solver agrees on the first question and disagrees on the second.
                if item["id"] == 1:
                    letter = "ABCD"[("ABCD".index(letter) + 1) % 4]
                answers.append({"id": item["id"], "choice": letter, "ambiguous": False, "reason": ""})
            return {"answers": answers}
        return {"reviews": [{"id": 0, "verdict": "keep", "problems": "",
                             "scores": {k: 5 for k in ("grounded", "unambiguous", "distractors", "learning_value", "standalone")}}]}

    monkeypatch.setattr(questions.llm, "generate_json", fake_generate_json)
    report = asyncio.run(questions.generate_from_passage(PASSAGE, 2, [], rng=random.Random(1)))
    assert calls == [questions.WRITER_SYSTEM, questions.SOLVER_SYSTEM, questions.REVIEWER_SYSTEM]
    assert len(report.accepted) == 1 and report.accepted[0]["review_score"] == 5
    assert any("blind solver disagreed" in reason for _, reason in report.rejected)


def test_store_roundtrip_ordering_and_flags():
    store = Store(":memory:")
    deck = store.get_or_create_deck(1, "Bio")
    assert store.get_or_create_deck(1, " bio ") == deck
    doc = store.add_document(deck, "notes.txt", "abc", [PASSAGE], user_id=7)
    assert store.add_document(deck, "notes.txt", "abc", [PASSAGE], user_id=7) is None
    chunk = store.pick_chunks(deck, 1, focus="inhibitors")[0]
    assert chunk["document_id"] == doc

    ids = [store.add_question(deck, chunk["id"], questions.shuffle_options(draft(stem=f"Question number {i} about enzymes?"), random.Random(i)))
           for i in range(3)]
    first = store.next_questions(deck, user_id=42, count=3)
    assert {q["id"] for q in first} == set(ids)

    store.record_attempt(ids[0], 42, 0, correct=False)
    store.record_attempt(ids[1], 42, 0, correct=True)
    order = [q["id"] for q in store.next_questions(deck, 42, 3)]
    assert order == [ids[2], ids[0], ids[1]]  # unseen, then missed, then known
    assert [q["id"] for q in store.next_questions(deck, 42, 3, skip_recent_seconds=600)] == [ids[2]]

    assert store.flag_question(ids[2], 1) is False
    assert store.flag_question(ids[2], 1) is False  # same person twice counts once
    assert store.flag_question(ids[2], 2) is True
    assert ids[2] not in [q["id"] for q in store.next_questions(deck, 42, 3)]

    stats = store.user_stats(42, deck)
    assert (stats["answered"], stats["correct"]) == (2, 1)


def test_login_budget(tmp_path, monkeypatch):
    from studybot import __main__ as entry, config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "MAX_LOGINS_PER_DAY", 3)
    assert [entry.take_login_slot() for _ in range(3)] == [0, 0, 0]
    assert entry.take_login_slot() > 23 * 3600
    stale = [time.time() - 25 * 3600] * 3
    (tmp_path / "logins.json").write_text(json.dumps(stale))
    assert entry.take_login_slot() == 0


def _deck_with_questions(n=3):
    store = Store(":memory:")
    deck = store.get_or_create_deck(9, "Enzymes 101")
    store.add_document(deck, "bio-notes.pdf", "h", [PASSAGE], user_id=1)
    for i in range(n):
        q = draft(stem=f"Question {i}: what happens to inhibition when substrate rises?")
        if i == 0:
            q["explanation"] = "Watch out: </script><script>alert(1)</script> is just text."
        store.add_question(deck, None, questions.shuffle_options(q, random.Random(i)))
    return store, deck


def test_export_html_embeds_questions_safely():
    from studybot import export

    store, deck = _deck_with_questions()
    data = export.pack_data(store, deck, "enzymes 101")
    page = export.render_html(data)
    assert data["sources"] == ["bio-notes.pdf"] and len(data["questions"]) == 3
    assert "</script><script>alert" not in page  # document text can't break out of the data block
    embedded = page.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded)["questions"][0]["options"] == data["questions"][0]["options"]


def test_export_anki_and_index(tmp_path):
    from studybot import export

    store, _ = _deck_with_questions(2)
    written = export.export_guild(store, 9, tmp_path)
    assert sorted(p.name for p in written) == ["enzymes-101.anki.txt", "enzymes-101.html", "index.html"]
    notes = (tmp_path / "enzymes-101.anki.txt").read_text().splitlines()
    assert notes[:2] == ["#separator:tab", "#html:true"]
    assert all(len(line.split("\t")) == 3 for line in notes[3:])
    assert 'href="enzymes-101.html"' in (tmp_path / "index.html").read_text()


# --- extracting existing questions -------------------------------------------

def test_parser_handles_common_layouts():
    from studybot.extract import parse_mcqs

    text = """Unit 3 Quiz
Choose the best answer.

1. Which organelle produces ATP?
A. Nucleus
B. Mitochondrion
C. Ribosome
D. Golgi body
Answer: B
Explanation: Mitochondria run
oxidative phosphorylation.

Q2) Capital of France? (A) Berlin (B) Paris (C) Rome

Which molecule carries amino acids to the ribosome?
a) mRNA
b) tRNA *
c) rRNA

4. Who wrote Faust?
A. Goethe
B. Schiller

Answer Key
2. B
"""
    qs = parse_mcqs(text)
    assert [q.stem for q in qs] == [
        "Which organelle produces ATP?",
        "Capital of France?",
        "Which molecule carries amino acids to the ribosome?",
        "Who wrote Faust?",
    ]
    assert [q.answer for q in qs] == [1, 1, 1, None]  # answer line, key section, star, none given
    assert qs[0].explanation == "Mitochondria run oxidative phosphorylation."
    assert qs[1].options == ["Berlin", "Paris", "Rome"]
    assert parse_mcqs("Enzymes speed reactions. A. Smith wrote about it. B. Jones agreed.") == []


def test_docx_bold_option_marks_the_answer(tmp_path):
    import docx
    from studybot.extract import parse_mcqs

    d = docx.Document()
    d.add_paragraph("1. Which gas do plants absorb?")
    d.add_paragraph("A. Oxygen")
    d.add_paragraph().add_run("B. Carbon dioxide").bold = True
    d.add_paragraph("C. Nitrogen")
    path = tmp_path / "q.docx"
    d.save(path)
    qs = parse_mcqs(ingest.extract_text("q.docx", path.read_bytes()))
    assert len(qs) == 1 and qs[0].answer == 1 and qs[0].options[1] == "Carbon dioxide"


def test_ai_copy_drops_questions_not_in_the_file(monkeypatch):
    from studybot import extract

    source = "| 1 | What is the boiling point of water at sea level? | 90 C | 100 C | 110 C |\n" * 2

    async def fake(prompt, *, system, audio=None, temperature=0.7, tries=3):
        return {"questions": [
            {"number": 1, "stem": "What is the boiling point of water at sea level?", "options": ["90 C", "100 C", "110 C"], "answer_position": None},
            {"number": 2, "stem": "What is the freezing point of mercury?", "options": ["-39 C", "0 C", "12 C"], "answer_position": 1},
        ]}

    monkeypatch.setattr(extract.llm, "generate_json", fake)
    found, dropped = asyncio.run(extract.copy_with_ai(source))
    assert [q.stem for q in found] == ["What is the boiling point of water at sea level?"] and dropped == 1


def test_find_questions_skips_the_model_when_not_needed(monkeypatch):
    from studybot import extract

    async def boom(*a, **k):
        raise AssertionError("model should not be called")

    monkeypatch.setattr(extract.llm, "generate_json", boom)
    clean = "1. Pick one?\nA. x\nB. y\nAnswer: A\n"
    assert asyncio.run(extract.find_questions("q.txt", clean.encode(), clean)).method == "parser"
    notes = "Plain lecture notes about enzymes. " * 20
    assert asyncio.run(extract.find_questions("n.txt", notes.encode(), notes)).questions == []


def test_ai_answers_are_labelled():
    from studybot import extract

    q = extract.Extracted("Who wrote Hamlet?", ["Marlowe", "Shakespeare"], answer=None)
    assert extract.to_stored(q) is None
    stored = extract.to_stored(q, {"index": 1, "confidence": "high", "reason": "He did."})
    assert stored["answer_source"] == "ai" and stored["correct_index"] == 1
    assert "suggested by AI" in questions.caution(stored)
    assert questions.caution(extract.to_stored(extract.Extracted("Q?", ["a", "b"], answer=0))) == ""
    assert "AI-written" in questions.caution({"origin": "generated"})


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, deck_id INTEGER, chunk_id INTEGER, stem TEXT, "
                 "options_json TEXT, correct_index INTEGER, explanation TEXT, rationales_json TEXT, source_quote TEXT, "
                 "difficulty TEXT, cognitive_level TEXT, review_score REAL, flags INTEGER DEFAULT 0, "
                 "retired INTEGER DEFAULT 0, created_at REAL)")
    conn.commit()
    conn.close()
    cols = {r["name"] for r in Store(path).conn.execute("PRAGMA table_info(questions)")}
    assert {"origin", "answer_source", "document_id"} <= cols
