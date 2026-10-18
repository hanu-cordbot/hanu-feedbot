"""Discord front end: slash commands, quiz buttons and interview threads."""
import asyncio
import io
import logging
import math
import random
import re
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import config, export, ingest, interview, questions
from .db import Store

log = logging.getLogger(__name__)

LETTERS = "ABCD"
EMBED_LIMIT = 4000
FIELD_LIMIT = 1000
QUESTIONS_PER_PASSAGE = 3
MAX_AUDIO_BYTES = 18 * 1024 * 1024  # Gemini's inline request limit is 20MB


def clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


class StudyBot(commands.Bot):
    def __init__(self, store: Store):
        intents = discord.Intents.default()
        intents.message_content = True  # read typed interview answers
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.store = store
        self.interviews: dict[int, interview.InterviewSession] = {}

    async def setup_hook(self) -> None:
        self.add_dynamic_items(AnswerButton, NextButton, FlagButton)
        await self.add_cog(StudyCog(self))
        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("Study bot ready as %s in %d server(s)", self.user, len(self.guilds))


# --- quiz rendering ----------------------------------------------------------

def question_embed(q: dict, number: int, total: int) -> discord.Embed:
    body = f"**{q['stem']}**\n\n" + "\n".join(f"**{LETTERS[i]}.** {opt}" for i, opt in enumerate(q["options"]))
    embed = discord.Embed(title=f"Question {number} of {total}", description=clip(body, EMBED_LIMIT), colour=0x5865F2)
    meta = " · ".join(x for x in (q.get("difficulty"), q.get("cognitive_level")) if x)
    if meta:
        embed.set_footer(text=meta)
    return embed


def answered_embed(q: dict, chosen: int, number: int, total: int) -> discord.Embed:
    correct = chosen == q["correct_index"]
    lines = []
    for i, opt in enumerate(q["options"]):
        mark = "✅" if i == q["correct_index"] else ("❌" if i == chosen else "▫️")
        lines.append(f"{mark} **{LETTERS[i]}.** {opt}")
    body = f"**{q['stem']}**\n\n" + "\n".join(lines)
    embed = discord.Embed(
        title=f"Question {number} of {total} — {'Correct!' if correct else 'Not quite'}",
        description=clip(body, EMBED_LIMIT),
        colour=0x57F287 if correct else 0xED4245,
    )
    embed.add_field(name="Why", value=clip(q["explanation"], FIELD_LIMIT), inline=False)
    wrong = [
        f"**{LETTERS[i]}** — {q['rationales'][i]}"
        for i in range(len(q["options"]))
        if i != q["correct_index"] and q["rationales"][i]
    ]
    if wrong:
        # Lead with the option they picked: that is the misconception they need to hear about.
        if not correct:
            wrong.sort(key=lambda line: not line.startswith(f"**{LETTERS[chosen]}**"))
        embed.add_field(name="Why the others are wrong", value=clip("\n".join(wrong), FIELD_LIMIT), inline=False)
    if q.get("source_quote"):
        embed.add_field(name="From your material", value=clip(f"> {q['source_quote']}", FIELD_LIMIT), inline=False)
    return embed


def question_view(q: dict, owner: int, left: int, right: int, done: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    for i in range(len(q["options"])):
        view.add_item(AnswerButton(q["id"], i, owner, left, right, done))
    return view


async def send_next_question(
    interaction: discord.Interaction, deck_id: int, owner: int, left: int, right: int, done: int
) -> None:
    store: Store = interaction.client.store  # type: ignore[attr-defined]
    picks = store.next_questions(deck_id, owner, 1, skip_recent_seconds=1800)
    total = left + done
    if not picks:
        await interaction.followup.send(
            f"That's every question in this deck for now. You scored **{right}/{done}**. "
            "Run `/generate` to add more.",
        )
        return
    q = picks[0]
    await interaction.followup.send(
        embed=question_embed(q, done + 1, total), view=question_view(q, owner, left - 1, right, done)
    )


class AnswerButton(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:a:(?P<q>\d+):(?P<c>\d):(?P<o>\d+):(?P<l>\d+):(?P<r>\d+):(?P<d>\d+)"):
    """All quiz state lives in the custom_id, so buttons keep working across restarts."""

    def __init__(self, qid: int, choice: int, owner: int, left: int, right: int, done: int):
        self.qid, self.choice, self.owner = qid, choice, owner
        self.left, self.right, self.done = left, right, done
        super().__init__(
            discord.ui.Button(
                label=LETTERS[choice],
                style=discord.ButtonStyle.secondary,
                custom_id=f"sb:a:{qid}:{choice}:{owner}:{left}:{right}:{done}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        g = {k: int(v) for k, v in match.groupdict().items()}
        return cls(g["q"], g["c"], g["o"], g["l"], g["r"], g["d"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is someone else's quiz. Start your own with `/quiz`.", ephemeral=True)
            return
        store: Store = interaction.client.store  # type: ignore[attr-defined]
        q = store.get_question(self.qid)
        if not q:
            await interaction.response.send_message("That question was deleted.", ephemeral=True)
            return
        correct = self.choice == q["correct_index"]
        store.record_attempt(self.qid, self.owner, self.choice, correct)
        right, done = self.right + int(correct), self.done + 1
        total = self.left + done

        view = discord.ui.View(timeout=None)
        if self.left > 0:
            view.add_item(NextButton(q["deck_id"], self.owner, self.left, right, done))
        view.add_item(FlagButton(self.qid))
        await interaction.response.edit_message(embed=answered_embed(q, self.choice, done, total), view=view)
        if self.left == 0:
            pct = round(100 * right / done)
            await interaction.followup.send(f"🏁 Quiz finished: **{right}/{done}** ({pct}%). `/quiz` again to keep going — missed questions come back first.")


class NextButton(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:n:(?P<k>\d+):(?P<o>\d+):(?P<l>\d+):(?P<r>\d+):(?P<d>\d+)"):
    def __init__(self, deck_id: int, owner: int, left: int, right: int, done: int):
        self.deck_id, self.owner, self.left, self.right, self.done = deck_id, owner, left, right, done
        super().__init__(
            discord.ui.Button(
                label=f"Next ({left} left)",
                style=discord.ButtonStyle.primary,
                custom_id=f"sb:n:{deck_id}:{owner}:{left}:{right}:{done}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        g = {k: int(v) for k, v in match.groupdict().items()}
        return cls(g["k"], g["o"], g["l"], g["r"], g["d"])

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is someone else's quiz. Start your own with `/quiz`.", ephemeral=True)
            return
        # Drop the Next button from the old message so it can't be pressed twice.
        view = discord.ui.View.from_message(interaction.message, timeout=None) if interaction.message else None
        if view:
            for child in list(view.children):
                if getattr(child, "custom_id", "").startswith("sb:n:"):
                    view.remove_item(child)
        await interaction.response.edit_message(view=view)
        await send_next_question(interaction, self.deck_id, self.owner, self.left, self.right, self.done)


class FlagButton(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:f:(?P<q>\d+)"):
    def __init__(self, qid: int):
        self.qid = qid
        super().__init__(
            discord.ui.Button(label="Flag question", emoji="🚩", style=discord.ButtonStyle.secondary, custom_id=f"sb:f:{qid}")
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["q"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        store: Store = interaction.client.store  # type: ignore[attr-defined]
        retired = store.flag_question(self.qid, interaction.user.id)
        msg = "Thanks — flagged for review."
        if retired:
            msg += " Enough people flagged it, so it's been pulled from the quiz rotation."
        await interaction.response.send_message(msg, ephemeral=True)


# --- commands ----------------------------------------------------------------

class StudyCog(commands.Cog):
    def __init__(self, bot: StudyBot):
        self.bot = bot
        self.store = bot.store

    async def deck_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not interaction.guild_id:
            return []
        return [app_commands.Choice(name=n, value=n) for n in self.store.deck_names(interaction.guild_id, current)]

    def _deck(self, interaction: discord.Interaction, name: str) -> Optional[int]:
        return self.store.find_deck(interaction.guild_id or 0, name)

    @app_commands.command(name="ingest", description="Add a document (PDF, DOCX, TXT, MD) to a study deck")
    @app_commands.describe(deck="Deck name, e.g. 'biology-unit-3' (created if new)", file="The document to learn from")
    @app_commands.guild_only()
    async def ingest_cmd(self, interaction: discord.Interaction, deck: str, file: discord.Attachment):
        if file.size > config.MAX_UPLOAD_BYTES:
            await interaction.response.send_message("That file is over 25MB.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        data = await file.read()
        try:
            text = await asyncio.to_thread(ingest.extract_text, file.filename, data)
        except ingest.UnsupportedFile as exc:
            await interaction.followup.send(str(exc))
            return
        except Exception as exc:
            log.exception("Failed to read %s", file.filename)
            await interaction.followup.send(f"Couldn't read `{file.filename}`: {exc}")
            return
        if len(text) < 200:
            await interaction.followup.send(
                f"Only found {len(text)} characters of text in `{file.filename}`. "
                "If it's a scanned PDF, it needs OCR first."
            )
            return
        chunks = ingest.chunk_text(text)
        deck_id = self.store.get_or_create_deck(interaction.guild_id, deck, interaction.user.id)
        doc_id = self.store.add_document(deck_id, file.filename, ingest.sha256(data), chunks, interaction.user.id)
        if doc_id is None:
            await interaction.followup.send(f"`{file.filename}` is already in **{deck}**.")
            return
        await interaction.followup.send(
            f"📚 Added `{file.filename}` to **{deck}**: {len(text):,} characters in {len(chunks)} passages.\n"
            f"Next: `/generate deck:{deck}` to write questions, or `/interview deck:{deck}` to practise out loud."
        )

    @ingest_cmd.autocomplete("deck")
    async def _ingest_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    @app_commands.command(name="generate", description="Write and vet new multiple-choice questions from a deck")
    @app_commands.describe(
        deck="Which deck to draw from",
        count="How many questions to add (each goes through a write → blind-solve → review pipeline)",
        focus="Optional topic to concentrate on, e.g. 'enzyme kinetics'",
    )
    @app_commands.guild_only()
    async def generate_cmd(
        self,
        interaction: discord.Interaction,
        deck: str,
        count: app_commands.Range[int, 1, 20] = 6,
        focus: Optional[str] = None,
    ):
        deck_id = self._deck(interaction, deck)
        if not deck_id:
            await interaction.response.send_message(f"No deck called **{deck}**. Add material with `/ingest` first.", ephemeral=True)
            return
        passages = self.store.pick_chunks(deck_id, math.ceil(count / QUESTIONS_PER_PASSAGE) + 1, focus)
        if not passages:
            await interaction.response.send_message(f"**{deck}** has no material yet.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✍️ Writing questions for **{deck}** from {len(passages)} passages. Each one is drafted, "
            "answered blind by a second pass, then reviewed. This takes a minute or two…"
        )
        existing = self.store.existing_stems(deck_id)
        per = max(1, math.ceil(count / len(passages)))
        rng = random.Random()

        async def run(passage):
            try:
                return passage, await questions.generate_from_passage(passage["text"], per, existing, focus, rng)
            except Exception as exc:
                log.exception("Generation failed for chunk %s", passage["id"])
                return passage, exc

        results = await asyncio.gather(*(run(p) for p in passages))
        accepted, rejected, written, errors = 0, [], 0, 0
        for passage, report in results:
            if isinstance(report, Exception):
                errors += 1
                continue
            self.store.mark_chunk_used(passage["id"])
            written += report.written
            rejected.extend(report.rejected)
            for q in report.accepted:
                if accepted >= count:
                    break
                self.store.add_question(deck_id, passage["id"], q)
                accepted += 1

        lines = [f"✅ Added **{accepted}** question(s) to **{deck}** (from {written} drafts)."]
        if rejected:
            lines.append(f"Rejected {len(rejected)} that didn't meet the bar, e.g.:")
            lines += [f"• _{clip(stem, 80)}_ — {clip(reason, 120)}" for stem, reason in rejected[:4]]
        if errors:
            lines.append(f"⚠️ {errors} passage(s) failed (model error or rate limit). Try again shortly.")
        if accepted:
            lines.append(f"Start with `/quiz deck:{deck}`.")
        await interaction.edit_original_response(content=clip("\n".join(lines), 1990))

    @generate_cmd.autocomplete("deck")
    async def _generate_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    @app_commands.command(name="quiz", description="Take a multiple-choice quiz from a deck")
    @app_commands.describe(deck="Which deck", count="Number of questions")
    @app_commands.guild_only()
    async def quiz_cmd(self, interaction: discord.Interaction, deck: str, count: app_commands.Range[int, 1, 25] = 5):
        deck_id = self._deck(interaction, deck)
        if not deck_id:
            await interaction.response.send_message(f"No deck called **{deck}**.", ephemeral=True)
            return
        picks = self.store.next_questions(deck_id, interaction.user.id, 1)
        if not picks:
            await interaction.response.send_message(
                f"**{deck}** has no questions yet. Run `/generate deck:{deck}` first.", ephemeral=True
            )
            return
        q = picks[0]
        await interaction.response.send_message(
            embed=question_embed(q, 1, count), view=question_view(q, interaction.user.id, count - 1, 0, 0)
        )

    @quiz_cmd.autocomplete("deck")
    async def _quiz_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    @app_commands.command(name="share", description="Get a deck as a standalone study pack (HTML quiz + review sheet) and Anki file")
    @app_commands.describe(deck="Which deck")
    @app_commands.guild_only()
    async def share_cmd(self, interaction: discord.Interaction, deck: str):
        deck_id = self._deck(interaction, deck)
        if not deck_id:
            await interaction.response.send_message(f"No deck called **{deck}**.", ephemeral=True)
            return
        data = export.pack_data(self.store, deck_id, deck.strip().lower())
        if not data["questions"]:
            await interaction.response.send_message(f"**{deck}** has no questions yet. Run `/generate` first.", ephemeral=True)
            return
        files = [
            discord.File(io.BytesIO(export.render_html(data).encode()), filename=f"{data['slug']}.html"),
            discord.File(io.BytesIO(export.render_anki(data).encode()), filename=f"{data['slug']}.anki.txt"),
        ]
        await interaction.response.send_message(
            f"📦 **{deck}** study pack: {len(data['questions'])} questions. Open the `.html` in any browser "
            "(works offline, on phones, and prints as a review sheet). Import the `.anki.txt` into Anki for flashcards.",
            files=files,
        )

    @share_cmd.autocomplete("deck")
    async def _share_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    @app_commands.command(name="decks", description="List study decks in this server")
    @app_commands.guild_only()
    async def decks_cmd(self, interaction: discord.Interaction):
        rows = self.store.list_decks(interaction.guild_id)
        if not rows:
            await interaction.response.send_message("No decks yet. Start with `/ingest`.", ephemeral=True)
            return
        lines = [f"**{r['name']}** — {r['docs']} document(s), {r['questions']} question(s)" for r in rows]
        await interaction.response.send_message(clip("\n".join(lines), 1990), ephemeral=True)

    @app_commands.command(name="stats", description="Your quiz accuracy")
    @app_commands.describe(deck="Optional: limit to one deck")
    @app_commands.guild_only()
    async def stats_cmd(self, interaction: discord.Interaction, deck: Optional[str] = None):
        deck_id = self._deck(interaction, deck) if deck else None
        s = self.store.user_stats(interaction.user.id, deck_id)
        if not s["answered"]:
            await interaction.response.send_message("You haven't answered anything yet.", ephemeral=True)
            return
        pct = round(100 * s["correct"] / s["answered"])
        await interaction.response.send_message(
            f"{s['correct']}/{s['answered']} correct ({pct}%) across {s['distinct_questions']} different questions.",
            ephemeral=True,
        )

    @stats_cmd.autocomplete("deck")
    async def _stats_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    # --- interview -----------------------------------------------------------

    @app_commands.command(name="interview", description="Practise answering interview/exam questions; reply by text or voice message")
    @app_commands.describe(
        deck="Material to be tested on",
        focus="Optional topic to concentrate on",
        rubric="Optional rubric file (PDF/DOCX/TXT). A sensible default is used otherwise",
        num_questions="How many questions",
    )
    @app_commands.rename(num_questions="questions")
    @app_commands.guild_only()
    async def interview_cmd(
        self,
        interaction: discord.Interaction,
        deck: str,
        focus: Optional[str] = None,
        rubric: Optional[discord.Attachment] = None,
        num_questions: app_commands.Range[int, 1, 10] = 3,
    ):
        deck_id = self._deck(interaction, deck)
        if not deck_id:
            await interaction.response.send_message(f"No deck called **{deck}**.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Run this in a regular text channel; I'll open a thread for it.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        rubric_text = interview.DEFAULT_RUBRIC
        if rubric:
            try:
                rubric_text = await asyncio.to_thread(ingest.extract_text, rubric.filename, await rubric.read())
            except Exception as exc:
                await interaction.followup.send(f"Couldn't read the rubric: {exc}")
                return
        chunks = self.store.pick_chunks(deck_id, 12, focus)
        material = "\n\n---\n\n".join(c["text"] for c in chunks)
        session = interview.InterviewSession(
            user_id=interaction.user.id, deck_id=deck_id, material=material, rubric=rubric_text,
            focus=focus, total_questions=num_questions,
        )
        thread = await interaction.channel.create_thread(
            name=clip(f"Interview · {interaction.user.display_name} · {deck}", 95),
            type=discord.ChannelType.public_thread,
            auto_archive_duration=1440,
        )
        self.bot.interviews[thread.id] = session
        await interaction.followup.send(f"🎙️ Interview started in {thread.mention}.")
        await thread.send(
            f"{interaction.user.mention} Answer each question **by typing**, or hold the 🎤 button to send a "
            "**voice message**. I'll grade it against the rubric and coach you. Say `skip` to skip, `end` to finish."
        )
        await self._ask(thread, session)

    @interview_cmd.autocomplete("deck")
    async def _interview_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    async def _ask(self, thread: discord.Thread, session: interview.InterviewSession) -> None:
        async with thread.typing():
            q = await interview.next_question(session)
        n = len(session.results) + 1  # a skipped question doesn't use up a slot
        await thread.send(embed=discord.Embed(
            title=f"Question {n} of {session.total_questions}", description=clip(q["question"], EMBED_LIMIT), colour=0x5865F2
        ))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        session = self.bot.interviews.get(message.channel.id)
        if not session or message.author.id != session.user_id or session.busy:
            return
        thread = message.channel
        command = message.content.strip().lower()
        if command == "end":
            await self._finish(thread, session)
            return
        session.busy = True
        try:
            if command == "skip":
                await self._ask(thread, session)
                return
            audio = None
            for a in message.attachments:
                if (a.content_type or "").startswith("audio/") and a.size <= MAX_AUDIO_BYTES:
                    audio = (await a.read(), a.content_type.split(";")[0])
                    break
            if not audio and len(message.content.strip()) < 3:
                return
            async with thread.typing():
                result = await interview.grade(session, message.content.strip() or None, audio)
            await thread.send(embed=feedback_embed(result))
            if session.finished:
                await self._finish(thread, session)
            else:
                await self._ask(thread, session)
        except Exception:
            log.exception("Interview step failed")
            await thread.send("Something went wrong grading that (model error or rate limit). Try sending it again.")
        finally:
            session.busy = False

    async def _finish(self, thread: discord.Thread, session: interview.InterviewSession) -> None:
        self.bot.interviews.pop(thread.id, None)
        if not session.results:
            await thread.send("Interview ended. No answers to summarise.")
            return
        total = sum(float(r.get("total") or 0) for r in session.results)
        possible = sum(float(r.get("max_total") or 0) for r in session.results) or 1
        try:
            async with thread.typing():
                summary = await interview.summarize(session)
        except Exception:
            log.exception("Summary failed")
            summary = {}
        embed = discord.Embed(
            title=f"Session complete — {total:g}/{possible:g}",
            description=clip(summary.get("headline", ""), EMBED_LIMIT),
            colour=0xFEE75C,
        )
        if summary.get("patterns"):
            embed.add_field(name="Patterns", value=clip("\n".join(f"• {p}" for p in summary["patterns"]), FIELD_LIMIT), inline=False)
        if summary.get("next_steps"):
            embed.add_field(name="Practise next", value=clip("\n".join(f"• {p}" for p in summary["next_steps"]), FIELD_LIMIT), inline=False)
        await thread.send(embed=embed)


def feedback_embed(result: dict) -> discord.Embed:
    total, max_total = result.get("total"), result.get("max_total")
    embed = discord.Embed(title=f"Score: {total}/{max_total}", colour=0x57F287)
    if result.get("transcript"):
        embed.description = clip(f"**What I heard:** {result['transcript']}", EMBED_LIMIT)
    for c in result.get("criteria", [])[:8]:
        value = f"{c.get('evidence', '')}\n➜ {c.get('advice', '')}".strip()
        embed.add_field(name=clip(f"{c.get('name')}: {c.get('score')}/{c.get('max')}", 250), value=clip(value, FIELD_LIMIT), inline=False)
    if result.get("improvements"):
        embed.add_field(name="Do next time", value=clip("\n".join(f"• {x}" for x in result["improvements"]), FIELD_LIMIT), inline=False)
    if result.get("model_answer"):
        embed.add_field(name="A full-marks answer", value=clip(result["model_answer"], FIELD_LIMIT), inline=False)
    if result.get("follow_up"):
        embed.set_footer(text=clip(f"An interviewer might follow up: {result['follow_up']}", 2000))
    return embed
