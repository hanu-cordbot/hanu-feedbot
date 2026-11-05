"""Finds multiple-choice questions that already exist in an uploaded file.

Existing questions were written by people, so they're preferred over generated ones.
Three layers, cheapest first:
  1. A plain parser for the common layouts: numbered or unnumbered stems, options
     labelled A./a)/(A), options on one line, "Answer: B" lines, starred options, and
     an "Answer key" section at the end.
  2. If the file clearly contains options the parser couldn't account for (tables, odd
     layouts), or it's a scan or photo, Gemini *copies* the questions out. It is told
     not to write or fix anything, and every copied stem is checked against the
     file's text, so invented questions are dropped.
  3. Questions whose answer isn't in the file get an AI-suggested answer, stored
     with answer_source="ai" so learners are warned.
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from . import ingest, llm

log = logging.getLogger(__name__)

LABELS = "ABCDEF"
MIN_OPTIONS, MAX_OPTIONS = 2, 6

OPTION_RE = re.compile(r"^\s*[\(\[]?([A-Fa-f])[\)\]\.:]\s+(\S.*)$")
NUMBERED_RE = re.compile(r"^\s*(?:Q(?:uestion)?\s*)?(\d{1,3})\s*[\.\):]\s*(\S.*)$", re.I)
ANSWER_RE = re.compile(r"^\s*(?:correct\s+)?(?:answer|ans)\b\s*(?:is)?\s*[:\-–.=]?\s*\(?([A-Fa-f])\)?(?![A-Za-z])", re.I)
EXPLAIN_RE = re.compile(r"^\s*(?:explanation|rationale|reason|solution)\s*[:\-–]\s*(.+)$", re.I)
KEY_HEADING_RE = re.compile(r"^\s*(?:answer\s*key|answers|answer\s*sheet|solutions|key)\s*:?\s*$", re.I)
KEY_PAIR_RE = re.compile(r"(?<!\d)(\d{1,3})\s*[\.\):\-–=]?\s*\(?([A-Fa-f])\)?(?![A-Za-z])")
INLINE_MARK_RE = re.compile(r"(?:^|(?<=\s))[\(\[]?([A-F])[\)\]\.]\s+")
QUESTION_END_RE = re.compile(r"(\?|:|_{2,}|\.{3}|…)\s*$")
CORRECT_MARK_RE = re.compile(r"^\*\s*|\s*(?:\*|✓|✔|\((?:correct|answer)\))\s*$", re.I)


@dataclass
class Extracted:
    stem: str
    options: list[str]
    answer: Optional[int] = None  # index into options, None if the file doesn't say
    explanation: str = ""
    number: Optional[int] = None


@dataclass
class ExtractionResult:
    questions: list[Extracted] = field(default_factory=list)
    method: str = "none"  # "parser", "ai-copy" or "none"
    dropped: int = 0  # items the AI copied that couldn't be matched to the file


# --- 1. plain parser -------------------------------------------------------

def split_inline_options(line: str) -> list[str]:
    """'What is X? A. foo B. bar C. baz' -> ['What is X?', 'A. foo', 'B. bar', 'C. baz']."""
    marks = [m for m in INLINE_MARK_RE.finditer(line)]
    seq, want = [], 0
    for m in marks:
        if m.group(1) == LABELS[want]:
            seq.append(m)
            want += 1
            if want == MAX_OPTIONS:
                break
    if len(seq) < 2:
        return [line]
    lead = line[: seq[0].start()].strip()
    # "A. Smith said... B. Jones agreed" is prose; real inline options follow a question.
    if len(seq) < 3 and lead and not QUESTION_END_RE.search(lead):
        return [line]
    parts = [line[: seq[0].start()].strip()] if line[: seq[0].start()].strip() else []
    for i, m in enumerate(seq):
        end = seq[i + 1].start() if i + 1 < len(seq) else len(line)
        parts.append(line[m.start():end].strip())
    return parts


def split_answer_key(text: str) -> tuple[str, dict[int, int]]:
    """Separates a trailing answer-key section and parses it into {question number: index}."""
    lines = text.split("\n")
    for i in range(len(lines) - 1, -1, -1):
        if KEY_HEADING_RE.match(lines[i]):
            key_text = "\n".join(lines[i + 1:])
            pairs = {int(n): LABELS.index(l.upper()) for n, l in KEY_PAIR_RE.findall(key_text)}
            if pairs:
                return "\n".join(lines[:i]), pairs
    return text, {}


def option_signal(text: str) -> int:
    """How many option-looking lines the text has; used to judge whether parsing missed some."""
    count = 0
    for line in text.split("\n"):
        for part in split_inline_options(line):
            if OPTION_RE.match(part):
                count += 1
    return count


def parse_mcqs(text: str) -> list[Extracted]:
    body, key = split_answer_key(text)
    lines: list[str] = []
    for raw in body.split("\n"):
        lines.extend(split_inline_options(raw))

    found: list[Extracted] = []
    stem: list[str] = []
    number: Optional[int] = None
    options: list[str] = []
    marked: list[int] = []
    answer: Optional[int] = None
    explanation = ""

    def finish():
        nonlocal stem, number, options, marked, answer, explanation
        stem_text = " ".join(stem).strip()
        looks_like_question = bool(QUESTION_END_RE.search(stem_text)) or len(options) >= 3
        if stem and MIN_OPTIONS <= len(options) <= MAX_OPTIONS and (looks_like_question or answer is not None or marked):
            ans = answer
            if ans is None and len(marked) == 1:
                ans = marked[0]
            if ans is None and number is not None:
                ans = key.get(number)
            if ans is not None and ans >= len(options):
                ans = None
            found.append(Extracted(stem_text, options, ans, explanation.strip(), number))
        stem, number, options, marked, answer, explanation = [], None, [], [], None, ""

    for line in lines:
        s = line.strip()
        if not s:
            if not options:
                stem = [] if number is None else stem  # an unnumbered stem is its last paragraph
            continue
        opt = OPTION_RE.match(s)
        if opt and opt.group(1).upper() == LABELS[min(len(options), MAX_OPTIONS - 1)] and (stem or options):
            text_ = opt.group(2).strip()
            if CORRECT_MARK_RE.search(text_):
                marked.append(len(options))
                text_ = CORRECT_MARK_RE.sub("", text_).strip()
            options.append(text_)
            continue
        if options:
            m = ANSWER_RE.match(s)
            if m:
                answer = LABELS.index(m.group(1).upper())
                continue
            m = EXPLAIN_RE.match(s)
            if m:
                explanation = m.group(1)
                continue
            if explanation and not NUMBERED_RE.match(s):
                explanation += " " + s
                continue
            if s[0].islower() and answer is None:
                options[-1] += " " + s  # wrapped option text
                continue
            finish()
        num = NUMBERED_RE.match(s)
        if num and not stem:
            number, stem = int(num.group(1)), [num.group(2)]
        elif num and stem and number is None:
            number, stem = int(num.group(1)), [num.group(2)]  # heading text before "1." isn't the stem
        else:
            stem.append(s)
    finish()
    return found


# --- 2. AI copy (never AI writing) -----------------------------------------

COPY_SYSTEM = """You copy multiple-choice questions out of documents for a study database.
You are a transcriber, not an author:
- Copy only questions that are actually in the document. Never write, complete, improve or invent questions or options.
- Keep the original wording. You may only repair broken line wraps, hyphenation and spacing.
- Options in printed order, without their labels (no "A.", "(b)" etc.).
- answer_position: the 1-based position of the correct option ONLY if the document states it (an answer line, an answer
  key, a ticked/circled/starred/bold/highlighted option). If the document does not say, use null. Do not solve it yourself.
- Skip questions that have no options (open questions); count them in "open_questions".
Return JSON only."""

COPY_PROMPT = """{key_note}DOCUMENT{part}:
<<<
{text}
>>>

Return JSON: {{"questions": [{{"number": int | null, "stem": str, "options": [str, ...],
  "answer_position": int | null, "explanation": str | null}}], "open_questions": int}}"""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower())).strip()


def appears_in(snippet: str, source_norm: str) -> bool:
    """True if `snippet` is (nearly) verbatim in the normalised source text."""
    s = _norm(snippet)
    if not s:
        return False
    if s in source_norm:
        return True
    words = s.split()
    if len(words) < 4:
        return False
    grams = [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]
    return sum(g in source_norm for g in grams) / len(grams) >= 0.7


def _from_copy(item: dict, key: dict[int, int]) -> Optional[Extracted]:
    stem = (item.get("stem") or "").strip()
    opts = [str(o).strip() for o in (item.get("options") or []) if str(o).strip()]
    if not stem or not (MIN_OPTIONS <= len(opts) <= MAX_OPTIONS):
        return None
    pos = item.get("answer_position")
    ans = pos - 1 if isinstance(pos, int) and 1 <= pos <= len(opts) else None
    number = item.get("number") if isinstance(item.get("number"), int) else None
    if ans is None and number is not None:
        ans = key.get(number)
    return Extracted(stem, opts, ans, (item.get("explanation") or "").strip(), number)


async def copy_with_ai(text: Optional[str], file: Optional[tuple[bytes, str]] = None) -> tuple[list[Extracted], int]:
    """Returns (questions, dropped). With `text`, each copied question must match it."""
    if file is not None:
        data = await llm.generate_json(
            COPY_PROMPT.format(key_note="", part=" (attached file)", text="(see attachment)"),
            system=COPY_SYSTEM, audio=file, temperature=0.0,
        )
        items = [_from_copy(i, {}) for i in data.get("questions", [])]
        return [q for q in items if q], 0

    assert text is not None
    body, key = split_answer_key(text)
    key_note = f"An answer key was found at the end of the document: {json.dumps({n: LABELS[i] for n, i in key.items()})}\n\n" if key else ""
    windows = ingest.chunk_text(body, size=12000, overlap=1500)
    source = _norm(text)
    out: list[Extracted] = []
    dropped = 0
    for n, window in enumerate(windows, 1):
        part = f" (part {n} of {len(windows)})" if len(windows) > 1 else ""
        data = await llm.generate_json(
            COPY_PROMPT.format(key_note=key_note, part=part, text=window), system=COPY_SYSTEM, temperature=0.0
        )
        for item in data.get("questions", []) if isinstance(data, dict) else []:
            q = _from_copy(item, key)
            if not q:
                continue
            # Hallucination guard: the stem and most options must really be in the file.
            hits = sum(appears_in(o, source) or _norm(o) in source for o in q.options)
            if appears_in(q.stem, source) and hits >= max(2, len(q.options) - 1):
                out.append(q)
            else:
                dropped += 1
    return dedupe(out), dropped


def dedupe(items: list[Extracted]) -> list[Extracted]:
    seen, out = set(), []
    for q in items:
        k = _norm(q.stem)[:200]
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


async def find_questions(filename: str, data: bytes, text: str) -> ExtractionResult:
    """Best effort at getting the file's own questions, without ever writing new ones."""
    if filename.lower().endswith(".json"):
        found = parse_json_mcqs(data)
        if found:
            return ExtractionResult(dedupe(found), "parser")
    if ingest.needs_vision(filename, text):
        if len(data) > 18 * 1024 * 1024:
            return ExtractionResult()
        found, _ = await copy_with_ai(None, (data, ingest.mime_type(filename)))
        return ExtractionResult(found, "ai-copy" if found else "none")

    parsed = parse_mcqs(text)
    signal = option_signal(text)
    consumed = sum(len(q.options) for q in parsed)
    if parsed and consumed >= 0.8 * signal:
        return ExtractionResult(parsed, "parser")
    if signal < 3:
        return ExtractionResult(parsed, "parser" if parsed else "none")
    # Plenty of options the parser couldn't place: let the model copy them out.
    copied, dropped = await copy_with_ai(text)
    if len(copied) > len(parsed):
        return ExtractionResult(copied, "ai-copy", dropped)
    return ExtractionResult(parsed, "parser", dropped)


# --- 2b. JSON question banks ----------------------------------------------

STEM_KEYS = ("q", "question", "stem", "prompt", "questionText", "question_text", "text")
OPTION_KEYS = ("options", "choices", "answers", "alternatives", "answerOptions", "answer_options")
ANSWER_KEYS = ("correctIndex", "correct_index", "answerIndex", "answer_index", "correctOption", "correct_option",
               "correctAnswer", "correct_answer", "correct", "answer", "key", "solution")
EXPLANATION_KEYS = ("explanation", "explain", "rationale", "reason", "feedback", "solution_text")
OPTION_TEXT_KEYS = ("text", "label", "option", "value", "content", "answer")
MAX_JSON_QUESTIONS = 5000


def _json_options(raw) -> tuple[list[str], Optional[int]]:
    """Options as plain strings, plus the answer if the options themselves mark it."""
    if isinstance(raw, dict):  # {"A": "...", "B": "..."}
        raw = [raw[k] for k in sorted(raw)]
    if not isinstance(raw, list):
        return [], None
    opts, marked = [], None
    for i, o in enumerate(raw):
        if isinstance(o, dict):
            text = next((o[k] for k in OPTION_TEXT_KEYS if isinstance(o.get(k), (str, int, float))), None)
            if o.get("correct") is True or o.get("isCorrect") is True or o.get("is_correct") is True:
                marked = i
            o = text
        if isinstance(o, (int, float)) and not isinstance(o, bool):
            o = str(o)
        if not isinstance(o, str) or not o.strip():
            return [], None
        opts.append(o.strip())
    return opts, marked


def _json_answer(item: dict, options: list[str]) -> Optional[int]:
    """Only answers the file states unambiguously; anything else is left for an AI suggestion (marked ⚠️)."""
    for key in ANSWER_KEYS:
        if key not in item:
            continue
        v = item[key]
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            if "index" in key.lower() or "option" in key.lower():
                return v if 0 <= v < len(options) else None
            return 0 if v == 0 else None  # "answer": 2 could be 0- or 1-based
        if isinstance(v, str):
            s = v.strip()
            if len(s) == 1 and s.upper() in LABELS[:len(options)]:
                return LABELS.index(s.upper())
            norm = [_norm(o) for o in options]
            if _norm(s) in norm:
                return norm.index(_norm(s))
    return None


def parse_json_mcqs(data: bytes) -> list[Extracted]:
    """Finds every {question, options, answer}-shaped object anywhere in a JSON file."""
    try:
        root = json.loads(data.decode("utf-8-sig", errors="replace"))
    except (json.JSONDecodeError, RecursionError):
        return []
    out: list[Extracted] = []
    stack = [root]
    while stack and len(out) < MAX_JSON_QUESTIONS:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(reversed(node))
            continue
        if not isinstance(node, dict):
            continue
        stem = next((node[k] for k in STEM_KEYS if isinstance(node.get(k), str) and node[k].strip()), None)
        raw_opts = next((node[k] for k in OPTION_KEYS if isinstance(node.get(k), (list, dict))), None)
        options, marked = _json_options(raw_opts) if raw_opts is not None else ([], None)
        if stem and 2 <= len(options) <= len(LABELS):
            answer = marked if marked is not None else _json_answer(node, options)
            explanation = next((node[k] for k in EXPLANATION_KEYS if isinstance(node.get(k), str)), "")
            out.append(Extracted(stem.strip(), options, answer, explanation.strip()))
            continue
        stack.extend(reversed(list(node.values())))
    return out


# --- 3. answers the file doesn't give --------------------------------------

SUGGEST_SYSTEM = """You are a subject expert checking a question bank. For each question pick the correct option and
explain in one or two sentences why. Rate confidence honestly: "high" only if an expert would agree with no caveats.
Return JSON only."""

SUGGEST_PROMPT = """Context from the same document (may help):
<<<
{context}
>>>

QUESTIONS:
{questions}

Return JSON: {{"answers": [{{"id": int, "answer_position": int, "confidence": "high"|"medium"|"low", "reason": str}}]}}"""


async def suggest_answers(items: list[Extracted], context: str) -> dict[int, dict]:
    """AI answers for questions without a key. Returns {index in items: {...}}."""
    todo = [(i, q) for i, q in enumerate(items) if q.answer is None]
    out: dict[int, dict] = {}
    for start in range(0, len(todo), 20):
        batch = todo[start:start + 20]
        payload = json.dumps(
            [{"id": i, "stem": q.stem, "options": {str(j + 1): o for j, o in enumerate(q.options)}} for i, q in batch],
            indent=1,
        )
        data = await llm.generate_json(
            SUGGEST_PROMPT.format(context=context[:20000], questions=payload), system=SUGGEST_SYSTEM, temperature=0.0
        )
        for a in data.get("answers", []) if isinstance(data, dict) else []:
            i, pos = a.get("id"), a.get("answer_position")
            q = items[i] if isinstance(i, int) and 0 <= i < len(items) else None
            if q and isinstance(pos, int) and 1 <= pos <= len(q.options):
                out[i] = {"index": pos - 1, "confidence": a.get("confidence", "low"), "reason": a.get("reason", "")}
    return out


def to_stored(q: Extracted, suggestion: Optional[dict] = None) -> Optional[dict]:
    """Converts to the stored question shape, keeping the file's own option order."""
    if q.answer is not None:
        answer, source, explanation = q.answer, "document", q.explanation
    elif suggestion:
        answer, source = suggestion["index"], "ai"
        explanation = q.explanation or f"AI-suggested ({suggestion['confidence']} confidence): {suggestion['reason']}"
    else:
        return None
    return {
        "stem": q.stem,
        "options": q.options,
        "rationales": [""] * len(q.options),
        "correct_index": answer,
        "explanation": explanation,
        "source_quote": None,
        "difficulty": None,
        "cognitive_level": None,
        "origin": "extracted",
        "answer_source": source,
    }

