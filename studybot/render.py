"""Embeds shared by solo and live quizzes."""
import discord

from . import quality, questions

LETTERS = "ABCDEF"
EMBED_LIMIT = 4000
FIELD_LIMIT = 1000


def clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def options_block(q: dict) -> str:
    return "\n".join(f"**{LETTERS[i]}.** {opt}" for i, opt in enumerate(q["options"]))


def footer_text(q: dict) -> str:
    meta = [quality.labels(q)] + [x for x in (q.get("difficulty"), q.get("cognitive_level")) if x]
    return " · ".join(meta)


def question_embed(q: dict, number: int, total: int) -> discord.Embed:
    embed = discord.Embed(
        title=f"Question {number} of {total}",
        description=clip(f"**{q['stem']}**\n\n{options_block(q)}", EMBED_LIMIT),
        colour=0x5865F2,
    )
    embed.set_footer(text=footer_text(q))
    return embed


def answered_embed(q: dict, chosen: int, number: int, total: int) -> discord.Embed:
    correct = chosen == q["correct_index"]
    lines = []
    for i, opt in enumerate(q["options"]):
        mark = "✅" if i == q["correct_index"] else ("❌" if i == chosen else "▫️")
        lines.append(f"{mark} **{LETTERS[i]}.** {opt}")
    embed = discord.Embed(
        title=f"Question {number} of {total} — {'Correct!' if correct else 'Not quite'}",
        description=clip(f"**{q['stem']}**\n\n" + "\n".join(lines), EMBED_LIMIT),
        colour=0x57F287 if correct else 0xED4245,
    )
    add_teaching_fields(embed, q, chosen)
    embed.set_footer(text=footer_text(q) + " · Rate it: was this a good question?")
    return embed


def add_teaching_fields(embed: discord.Embed, q: dict, chosen: int | None = None) -> None:
    if q.get("explanation"):
        embed.add_field(name="Why", value=clip(q["explanation"], FIELD_LIMIT), inline=False)
    wrong = [
        f"**{LETTERS[i]}** — {q['rationales'][i]}"
        for i in range(len(q["options"]))
        if i != q["correct_index"] and i < len(q["rationales"]) and q["rationales"][i]
    ]
    if wrong:
        # Lead with the option they picked: that is the misconception they need to hear about.
        if chosen is not None and chosen != q["correct_index"]:
            wrong.sort(key=lambda line: not line.startswith(f"**{LETTERS[chosen]}**"))
        embed.add_field(name="Why the others are wrong", value=clip("\n".join(wrong), FIELD_LIMIT), inline=False)
    if q.get("source_quote"):
        embed.add_field(name="From your material", value=clip(f"> {q['source_quote']}", FIELD_LIMIT), inline=False)
    if questions.caution(q):
        embed.add_field(name="Heads up", value=questions.caution(q), inline=False)
