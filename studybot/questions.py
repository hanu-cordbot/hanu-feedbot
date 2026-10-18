"""Multiple-choice question pipeline: write -> blind-solve -> critique -> local checks.

Every stage exists to throw away questions a careful teacher would not put on a test:
  * the writer must ground each answer in a verbatim quote and give every distractor a
    named misconception, so wrong options are tempting for a reason rather than filler;
  * a separate blind solver answers each question *without* the key. If it picks a
    different option, or thinks two are defensible, the question is ambiguous;
  * a reviewer scores grounding, ambiguity, distractor quality and learning value, and
    may repair a question;
  * cheap local checks catch test-taking cues (longest-answer bias, "all of the above",
    duplicate options, near-duplicate questions, unverifiable quotes).
Options are shuffled here, never by the model, so the key's position carries no signal.
"""
import difflib
import json
import logging
import random
import re
from dataclasses import dataclass, field
from typing import Optional

from . import llm

log = logging.getLogger(__name__)

MIN_REVIEW_SCORE = 4  # every criterion must reach this (out of 5)
BANNED_OPTION_PATTERNS = re.compile(
    r"\b(all|none) of the (above|these|options)\b|\bboth (a|b|c|d)\b|\b[a-d] and [a-d]\b", re.I
)

WRITER_SYSTEM = """You are an expert assessment writer who builds exam questions that teach.
You write multiple-choice questions the way a careful professor does when the exam matters:

STEM
- Self-contained: answerable without seeing the options, and without the passage in front of you.
- Tests one important idea from the passage, not trivia (no "which page", dates or names unless they are the point).
- Prefer understanding, application and analysis (scenarios, predictions, "what would happen if", "which best explains") over recall.
- No negatives ("NOT", "EXCEPT") unless unavoidable. No absolute cue words that give the answer away.
- Never refers to "the passage", "the text", "the author" or "the document". Learners will not see it.

CORRECT ANSWER
- Exactly one option is correct, and an expert would agree with no caveats.
- It must be directly supported by the passage. Quote the supporting sentence(s) verbatim in source_quote.

DISTRACTORS (exactly 3)
- Each is wrong for a specific, nameable reason: a common misconception, a confusion with a related concept,
  a partial truth, a reversed cause and effect, or a misapplied rule. State that reason in "misconception".
- Each must be tempting to a learner who half-understands the material, and clearly wrong to one who understands it.
- Same grammatical form, similar length and specificity as the correct answer. No joke options.
- Never "all of the above", "none of the above", or combinations of other options.

EXPLANATION
- 2 to 4 sentences that teach: why the answer is right, and the principle a learner should remember.

Return JSON only."""

WRITER_PROMPT = """Write {count} multiple-choice questions from the passage below.
Spread them across different ideas in the passage. Do not duplicate any of these existing questions:
{existing}
{focus_line}
PASSAGE:
<<<
{passage}
>>>

Return JSON: {{"questions": [{{
  "stem": str,
  "correct_answer": str,
  "distractors": [{{"text": str, "misconception": str}}, ...3 items],
  "explanation": str,
  "source_quote": str,
  "difficulty": "easy" | "medium" | "hard",
  "cognitive_level": "remember" | "understand" | "apply" | "analyze" | "evaluate"
}}]}}"""

SOLVER_SYSTEM = """You are a top student taking an exam. Use the reference passage to answer each question.
Be honest about ambiguity: if more than one option could reasonably be defended, or none is fully correct, say so.
Return JSON only."""

SOLVER_PROMPT = """REFERENCE PASSAGE:
<<<
{passage}
>>>

QUESTIONS:
{questions}

For each question return your chosen option letter and whether the question is ambiguous.
Return JSON: {{"answers": [{{"id": int, "choice": "A"|"B"|"C"|"D", "ambiguous": bool, "reason": str}}]}}"""

REVIEWER_SYSTEM = """You are a strict assessment reviewer. Your job is to stop weak questions from reaching learners.
Score each criterion from 1 to 5, where 5 means you would put it on a final exam unchanged:
- grounded: the keyed answer is fully supported by the passage and factually correct.
- unambiguous: exactly one option is defensible; the stem is clear without reading the options.
- distractors: every wrong option is plausible to a partial learner, wrong for a real reason, and gives no length/wording cue.
- learning_value: it tests an important idea (ideally understanding or application), not trivia.
- standalone: makes sense to someone who never saw the passage (no "according to the text").
verdict: "keep" if all scores are >= 4; "revise" if a small fix makes all scores >= 4 (then supply the
fixed question in "revised" with the same fields as the input); otherwise "reject".
Return JSON only."""

REVIEWER_PROMPT = """PASSAGE:
<<<
{passage}
>>>

QUESTIONS WITH ANSWER KEYS:
{questions}

Return JSON: {{"reviews": [{{
  "id": int,
  "scores": {{"grounded": int, "unambiguous": int, "distractors": int, "learning_value": int, "standalone": int}},
  "problems": str,
  "verdict": "keep" | "revise" | "reject",
  "revised": null | {{"stem": str, "correct_answer": str, "distractors": [{{"text": str, "misconception": str}}],
                     "explanation": str, "source_quote": str, "difficulty": str, "cognitive_level": str}}
}}]}}"""


def caution(q: dict) -> str:
    """Warning to show learners when a question or its answer came from AI, not people."""
    if q.get("origin", "generated") == "generated":
        return "⚠️ AI-written question: it may be wrong or ambiguous. Flag it if something's off."
    if q.get("answer_source") == "ai":
        return "⚠️ The file didn't include an answer for this one; the answer shown was suggested by AI."
    return ""


@dataclass
class GenerationReport:
    written: int = 0
    accepted: list[dict] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (stem, reason)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", text.lower())).strip()


def quote_supported(quote: str, passage: str) -> bool:
    """True if the cited quote really comes from the passage (tolerating small edits)."""
    q, p = _norm(quote), _norm(passage)
    if not q or len(q) < 15:
        return False
    if q in p:
        return True
    words = q.split()
    if len(words) < 5:
        return False
    grams = [" ".join(words[i:i + 5]) for i in range(len(words) - 4)]
    return sum(g in p for g in grams) / len(grams) >= 0.6


def local_problems(raw: dict, passage: str, existing_stems: list[str]) -> Optional[str]:
    """Returns a reason to reject the question, or None if it passes the mechanical checks."""
    stem = (raw.get("stem") or "").strip()
    correct = (raw.get("correct_answer") or "").strip()
    distractors = raw.get("distractors") or []
    if len(stem) < 15:
        return "stem too short"
    if not correct or len(distractors) != 3:
        return "needs one answer and exactly three distractors"
    texts = [correct] + [(d.get("text") or "").strip() for d in distractors]
    if any(not t for t in texts):
        return "empty option"
    if any(len(t) > 300 for t in texts):
        return "option too long"
    if len({_norm(t) for t in texts}) != 4:
        return "duplicate options"
    if any(BANNED_OPTION_PATTERNS.search(t) for t in texts):
        return "uses all/none-of-the-above style option"
    if any(not (d.get("misconception") or "").strip() for d in distractors):
        return "distractor without a stated misconception"
    if re.search(r"\b(the|this) (passage|text|document|excerpt|article)\b", stem, re.I):
        return "stem refers to the source text"
    others = [len(t) for t in texts[1:]]
    if len(correct) > 1.6 * (sum(others) / 3) and len(correct) - max(others) > 25:
        return "correct answer is conspicuously longest"
    if not quote_supported(raw.get("source_quote") or "", passage):
        return "source quote not found in material"
    for old in existing_stems:
        if difflib.SequenceMatcher(None, _norm(stem), _norm(old)).ratio() > 0.85:
            return "near-duplicate of an existing question"
    return None


def shuffle_options(raw: dict, rng: random.Random) -> dict:
    """Builds the stored form: options in random order, with the key and per-option rationale."""
    entries = [(raw["correct_answer"].strip(), "")] + [
        (d["text"].strip(), d["misconception"].strip()) for d in raw["distractors"]
    ]
    order = list(range(4))
    rng.shuffle(order)
    options = [entries[i][0] for i in order]
    rationales = [entries[i][1] for i in order]
    return {
        "stem": raw["stem"].strip(),
        "options": options,
        "rationales": rationales,
        "correct_index": order.index(0),
        "explanation": raw["explanation"].strip(),
        "source_quote": raw.get("source_quote", "").strip(),
        "difficulty": raw.get("difficulty"),
        "cognitive_level": raw.get("cognitive_level"),
    }


def _for_solver(questions: list[dict]) -> str:
    return json.dumps(
        [
            {"id": i, "stem": q["stem"], "options": {"ABCD"[j]: o for j, o in enumerate(q["options"])}}
            for i, q in enumerate(questions)
        ],
        indent=1,
    )


async def generate_from_passage(
    passage: str,
    count: int,
    existing_stems: list[str],
    focus: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> GenerationReport:
    rng = rng or random.Random()
    report = GenerationReport()
    # Ask for extra candidates: the review stages are meant to discard some.
    want = min(count + 2, 8)
    existing = "\n".join(f"- {s}" for s in existing_stems[-40:]) or "(none yet)"
    focus_line = f"Concentrate on: {focus}\n" if focus else ""
    data = await llm.generate_json(
        WRITER_PROMPT.format(count=want, existing=existing, focus_line=focus_line, passage=passage),
        system=WRITER_SYSTEM,
        temperature=0.8,
    )
    drafts = data.get("questions", []) if isinstance(data, dict) else []
    report.written = len(drafts)

    seen = list(existing_stems)
    candidates: list[tuple[dict, dict]] = []  # (raw draft, shuffled form)
    for raw in drafts:
        reason = local_problems(raw, passage, seen)
        if reason:
            report.rejected.append((raw.get("stem", "?"), reason))
            continue
        candidates.append((raw, shuffle_options(raw, rng)))
        seen.append(raw["stem"])
    if not candidates:
        return report

    shuffled = [c[1] for c in candidates]
    solved = await llm.generate_json(
        SOLVER_PROMPT.format(passage=passage, questions=_for_solver(shuffled)),
        system=SOLVER_SYSTEM,
        temperature=0.0,
    )
    answers = {a.get("id"): a for a in solved.get("answers", [])} if isinstance(solved, dict) else {}

    survivors: list[tuple[dict, dict]] = []
    for i, (raw, q) in enumerate(candidates):
        ans = answers.get(i)
        if not ans:
            report.rejected.append((q["stem"], "blind solver skipped it"))
            continue
        choice = "ABCD".find(str(ans.get("choice", "")).strip().upper()[:1])
        if ans.get("ambiguous"):
            report.rejected.append((q["stem"], f"ambiguous: {ans.get('reason', '')}".strip()))
        elif choice != q["correct_index"]:
            report.rejected.append((q["stem"], f"blind solver disagreed with the key: {ans.get('reason', '')}".strip()))
        else:
            survivors.append((raw, q))
    if not survivors:
        return report

    keyed = json.dumps(
        [
            {
                "id": i,
                "stem": raw["stem"],
                "correct_answer": raw["correct_answer"],
                "distractors": raw["distractors"],
                "explanation": raw["explanation"],
                "source_quote": raw.get("source_quote"),
                "difficulty": raw.get("difficulty"),
                "cognitive_level": raw.get("cognitive_level"),
            }
            for i, (raw, _) in enumerate(survivors)
        ],
        indent=1,
    )
    reviewed = await llm.generate_json(
        REVIEWER_PROMPT.format(passage=passage, questions=keyed),
        system=REVIEWER_SYSTEM,
        temperature=0.0,
    )
    reviews = {r.get("id"): r for r in reviewed.get("reviews", [])} if isinstance(reviewed, dict) else {}

    for i, (raw, q) in enumerate(survivors):
        review = reviews.get(i)
        if not review:
            report.rejected.append((q["stem"], "reviewer skipped it"))
            continue
        verdict = review.get("verdict")
        scores = review.get("scores") or {}
        if verdict == "revise" and isinstance(review.get("revised"), dict):
            fixed = review["revised"]
            reason = local_problems(fixed, passage, [s for s in seen if s != raw["stem"]])
            if reason:
                report.rejected.append((q["stem"], f"revision failed checks: {reason}"))
                continue
            q = shuffle_options(fixed, rng)
        elif verdict != "keep":
            report.rejected.append((q["stem"], review.get("problems") or "reviewer rejected it"))
            continue
        elif any(int(v) < MIN_REVIEW_SCORE for v in scores.values() if isinstance(v, (int, float))):
            report.rejected.append((q["stem"], review.get("problems") or "low review score"))
            continue
        numeric = [v for v in scores.values() if isinstance(v, (int, float))]
        q["review_score"] = round(sum(numeric) / len(numeric), 2) if numeric else None
        report.accepted.append(q)
        if len(report.accepted) >= count:
            break
    return report
