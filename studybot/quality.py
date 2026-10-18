"""Labels, quality scores and question picking.

Every question carries emoji that say where it came from and what people think of it:
  📄 answer from the file · 🤖 AI-suggested answer · ✨ AI-written question
  ⭐ community favourite (net 👍 ≥ 2) · 🚩 flagged by someone
The quality score decides which questions come up more often. Real questions with the
file's own answers beat AI ones, and people's 👍/👎/🚩 move them up or down.
"""
import random
from typing import Optional

LEGEND = "📄 answer from the file · 🤖 AI-suggested answer · ✨ AI-written · ⭐ favourite · 🚩 flagged"
FAVOURITE_AT = 2

SUBJECT_EMOJI = [
    (("bio", "anatomy", "physiology", "genetic"), "🧬"),
    (("chem",), "⚗️"),
    (("physic",), "⚛️"),
    (("math", "calculus", "algebra", "statistic", "geometry"), "📐"),
    (("history",), "🏛️"),
    (("english", "literature", "writing", "reading"), "📖"),
    (("computer", "programming", "coding", "software", "cs"), "💻"),
    (("geo",), "🌍"),
    (("econ", "business", "finance", "accounting"), "📈"),
    (("language", "spanish", "french", "german", "chinese", "japanese", "malay", "korean"), "🗣️"),
    (("art", "design"), "🎨"),
    (("music",), "🎵"),
    (("law", "legal"), "⚖️"),
    (("medic", "nursing", "health", "pharma"), "🩺"),
    (("psych",), "🧠"),
]


def subject_emoji(subject: Optional[str]) -> str:
    words = (subject or "").lower().replace("-", " ").split()
    for keys, emoji in SUBJECT_EMOJI:
        if any(w.startswith(k) for w in words for k in keys):
            return emoji
    return "📚"


def source_label(q: dict) -> str:
    if q.get("origin", "generated") == "generated":
        return "✨"
    return "🤖" if q.get("answer_source") == "ai" else "📄"


def labels(q: dict) -> str:
    out = [source_label(q)]
    if (q.get("net_rating") or 0) >= FAVOURITE_AT:
        out.append("⭐")
    if (q.get("flags") or 0) >= 1:
        out.append("🚩")
    return " ".join(out)


def quality(q: dict) -> float:
    base = {"📄": 2, "🤖": 0, "✨": -1}[source_label(q)]
    return base + (q.get("net_rating") or 0) - 2 * (q.get("flags") or 0)


def weight(q: dict, personal: bool) -> float:
    w = max(0.2, 1 + 0.3 * quality(q))
    if personal:
        last = q.get("last_correct")
        # Unseen and previously-missed questions come up more; ones you know, less.
        w *= 1.5 if last is None else (1.8 if last == 0 else 0.6)
    return w


def pick(pool: list[dict], n: int, rng: Optional[random.Random] = None, personal: bool = False) -> list[dict]:
    """A random mix of n questions, weighted toward better ones.

    Net-negative questions are only used if the pool would otherwise run short.
    Weighted sampling without replacement: each item gets key = u ** (1 / weight).
    """
    rng = rng or random.Random()
    good = [q for q in pool if quality(q) >= 0]
    weak = [q for q in pool if quality(q) < 0]

    def sample(items: list[dict], k: int) -> list[dict]:
        keyed = sorted(items, key=lambda q: rng.random() ** (1 / weight(q, personal)), reverse=True)
        return keyed[:k]

    chosen = sample(good, n)
    if len(chosen) < n:
        chosen += sample(weak, n - len(chosen))
    rng.shuffle(chosen)
    return chosen
