"""Interview practice: ask an open question, grade the answer (typed or spoken) on a rubric."""
import json
from dataclasses import dataclass, field
from typing import Optional

from . import llm

DEFAULT_RUBRIC = """1. Accuracy (0-4): claims are correct and consistent with the material.
2. Depth (0-3): explains why/how, not just what; covers the key points.
3. Structure (0-2): clear, logical order; gets to the point.
4. Communication (0-1): concise, confident, appropriate terminology."""

INTERVIEWER_SYSTEM = """You are an experienced interviewer and examiner. You ask one open-ended question at a time,
the kind that separates someone who understands the material from someone who memorised it:
"explain why", "walk me through", "how would you handle", "what goes wrong if", "compare".
Questions must be answerable in about one to two minutes of speech, and must not refer to "the document".
Return JSON only."""

QUESTION_PROMPT = """Material the candidate is being tested on:
<<<
{material}
>>>

Rubric that answers will be graded on:
<<<
{rubric}
>>>
{focus_line}
Questions already asked in this session (do not repeat or closely paraphrase):
{asked}

Write the next question. Increase difficulty slightly each time.
Return JSON: {{"question": str, "key_points": [str, ...3-6 points a strong answer covers], "difficulty": "easy"|"medium"|"hard"}}"""

GRADER_SYSTEM = """You are a fair, specific and encouraging examiner. Grade strictly against the rubric and the material.
Quote or paraphrase what the candidate actually said as evidence for every score. Never invent content they did not say.
Feedback must be actionable: say exactly what to add, cut or reorder next time.
If audio is attached, first transcribe it faithfully (keep filler words out), then grade the transcript, and you may
comment briefly on delivery (pace, hesitation, clarity) under Communication.
Return JSON only."""

GRADE_PROMPT = """Material:
<<<
{material}
>>>

Rubric:
<<<
{rubric}
>>>

Question: {question}
Key points a strong answer covers: {key_points}

Candidate's answer: {answer}

Return JSON: {{
  "transcript": str | null,
  "criteria": [{{"name": str, "score": number, "max": number, "evidence": str, "advice": str}}],
  "total": number,
  "max_total": number,
  "strengths": [str],
  "improvements": [str],
  "model_answer": str,
  "follow_up": str
}}
"model_answer" is a concise, spoken-style answer (under 120 words) that would earn full marks.
"follow_up" is one probing follow-up question an interviewer would ask next, based on a gap in this answer."""

SUMMARY_PROMPT = """You coached a candidate through this interview practice session. Results (JSON):
{results}

Return JSON: {{"headline": str, "patterns": [str], "next_steps": [str]}}
"patterns" are recurring strengths or weaknesses across answers; "next_steps" are 2-4 concrete things to practise."""


@dataclass
class InterviewSession:
    user_id: int
    deck_id: int
    material: str
    rubric: str = DEFAULT_RUBRIC
    focus: Optional[str] = None
    total_questions: int = 3
    asked: list[str] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    current: Optional[dict] = None
    busy: bool = False

    @property
    def finished(self) -> bool:
        return len(self.results) >= self.total_questions


async def next_question(session: InterviewSession) -> dict:
    asked = "\n".join(f"- {q}" for q in session.asked) or "(none)"
    focus_line = f"\nFocus the question on: {session.focus}\n" if session.focus else ""
    q = await llm.generate_json(
        QUESTION_PROMPT.format(material=session.material, rubric=session.rubric, focus_line=focus_line, asked=asked),
        system=INTERVIEWER_SYSTEM,
        temperature=0.8,
    )
    session.current = q
    session.asked.append(q["question"])
    return q


async def grade(session: InterviewSession, text: Optional[str], audio: Optional[tuple[bytes, str]]) -> dict:
    assert session.current is not None
    answer = text if text else "(see attached audio recording)"
    result = await llm.generate_json(
        GRADE_PROMPT.format(
            material=session.material,
            rubric=session.rubric,
            question=session.current["question"],
            key_points="; ".join(session.current.get("key_points", [])),
            answer=answer,
        ),
        system=GRADER_SYSTEM,
        audio=audio,
        temperature=0.2,
    )
    result["question"] = session.current["question"]
    session.results.append(result)
    return result


async def summarize(session: InterviewSession) -> dict:
    compact = [
        {
            "question": r["question"],
            "total": r.get("total"),
            "max_total": r.get("max_total"),
            "improvements": r.get("improvements"),
            "strengths": r.get("strengths"),
        }
        for r in session.results
    ]
    return await llm.generate_json(
        SUMMARY_PROMPT.format(results=json.dumps(compact, indent=1)),
        system=GRADER_SYSTEM,
        temperature=0.3,
    )
