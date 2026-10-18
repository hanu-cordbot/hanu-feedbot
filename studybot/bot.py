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

from . import config, export, extract, ingest, interview, play, quality, questions
from .db import Store
from .render import EMBED_LIMIT, FIELD_LIMIT, clip

log = logging.getLogger(__name__)

QUESTIONS_PER_PASSAGE = 3
COMMON_SUBJECTS = ["biology", "chemistry", "physics", "mathematics", "history", "english", "computer science",
                   "geography", "economics", "business", "psychology", "languages", "art", "music"]
MAX_AUDIO_BYTES = 18 * 1024 * 1024  # Gemini's inline request limit is 20MB


class StudyBot(commands.Bot):
    def __init__(self, store: Store):
        intents = discord.Intents.default()
        intents.message_content = True  # read typed interview answers
        # Question text comes from uploaded files, so it must never be able to ping @everyone, roles or users.
        super().__init__(
            command_prefix=commands.when_mentioned, intents=intents, allowed_mentions=discord.AllowedMentions.none()
        )
        self.store = store
        self.interviews: dict[int, interview.InterviewSession] = {}
        self.live_games: dict[int, play.LiveGame] = {}

    async def setup_hook(self) -> None:
        self.add_dynamic_items(*play.DYNAMIC_ITEMS)
        await self.add_cog(StudyCog(self))
        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        log.info("Study bot ready as %s in %d server(s)", self.user, len(self.guilds))


class GenerateOffer(discord.ui.View):
    """Shown when an upload has no questions: the uploader opts in to AI-written ones."""

    def __init__(self, cog: "StudyCog", owner: int, deck_id: int, deck: str):
        super().__init__(timeout=3600)
        self.cog, self.owner, self.deck_id, self.deck = cog, owner, deck_id, deck

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("Only the person who uploaded the file can choose this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Write 6 questions with AI", emoji="⚠️", style=discord.ButtonStyle.primary)
    async def write(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.message.edit(view=None)
        await self.cog.run_generation(interaction, self.deck_id, self.deck, 6)

    @discord.ui.button(label="No thanks", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(view=None)
        await interaction.followup.send(
            f"OK. The file is still in **{self.deck}** for `/interview`, and you can run `/generate` later.", ephemeral=True
        )


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

    @app_commands.command(name="upload", description="Add any file: existing questions in it are pulled out, the rest is kept as study material")
    @app_commands.describe(
        file="PDF, Word, PowerPoint, text, JSON question bank, or a photo/screenshot of a worksheet",
        deck="Question set to add it to (defaults to the file name)",
        subject="Subject it belongs to, e.g. biology (used to group sets in /library and /quiz)",
    )
    @app_commands.guild_only()
    async def upload_cmd(
        self, interaction: discord.Interaction, file: discord.Attachment, deck: Optional[str] = None, subject: Optional[str] = None
    ):
        if file.size > config.MAX_UPLOAD_BYTES:
            await interaction.response.send_message("That file is over 25MB.", ephemeral=True)
            return
        deck = (deck or export.slugify(file.filename.rsplit(".", 1)[0])).strip().lower()
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

        deck_id = self.store.get_or_create_deck(interaction.guild_id, deck, interaction.user.id, subject)
        chunks = ingest.chunk_text(text) if len(text) >= 200 else []
        doc_id = self.store.add_document(deck_id, file.filename, ingest.sha256(data), chunks, interaction.user.id)
        if doc_id is None:
            await interaction.followup.send(f"`{file.filename}` is already in **{deck}**.")
            return

        try:
            found = await extract.find_questions(file.filename, data, text)
        except Exception:
            log.exception("Question extraction failed for %s", file.filename)
            found = extract.ExtractionResult(extract.parse_mcqs(text), "parser")
        items = found.questions
        suggestions: dict[int, dict] = {}
        if any(q.answer is None for q in items):
            try:
                suggestions = await extract.suggest_answers(items, text)
            except Exception:
                log.exception("Answer suggestion failed")

        existing = {extract._norm(s) for s in self.store.existing_stems(deck_id, limit=100000)}
        from_file = ai_answer = no_answer = duplicate = 0
        for i, q in enumerate(items):
            stored = extract.to_stored(q, suggestions.get(i))
            if stored is None:
                no_answer += 1
                continue
            if extract._norm(q.stem) in existing:
                duplicate += 1
                continue
            existing.add(extract._norm(q.stem))
            self.store.add_question(deck_id, None, stored, document_id=doc_id)
            if stored["answer_source"] == "document":
                from_file += 1
            else:
                ai_answer += 1

        added = from_file + ai_answer
        if added:
            how = "read directly from the file" if found.method == "parser" else "copied out with AI help, each one checked against the file's text"
            lines = [f"📚 Found **{added}** question(s) in `{file.filename}` → deck **{deck}** ({how})."]
            if from_file:
                lines.append(f"✅ {from_file} with answers from the file itself.")
            if ai_answer:
                lines.append(f"⚠️ {ai_answer} had no answer in the file, so AI suggested one. These are marked in the quiz; please flag any that look wrong.")
            if no_answer:
                lines.append(f"Skipped {no_answer} with no answer in the file that AI couldn't answer.")
            if duplicate:
                lines.append(f"Skipped {duplicate} already in the deck.")
            if found.dropped:
                lines.append(f"Ignored {found.dropped} that didn't match the file's text.")
            lines.append(f"Play it with `/quiz`, or share it with `/share deck:{deck}`.")
            await interaction.followup.send(clip("\n".join(lines), 1990))
            return

        if not chunks:
            await interaction.followup.send(
                f"I couldn't find any multiple-choice questions or enough readable text in `{file.filename}`. "
                "If it's a photo, try a clearer, straight-on shot."
            )
            return
        await interaction.followup.send(
            f"📄 Saved `{file.filename}` to **{deck}** as study material. **I didn't find any multiple-choice questions in it.**\n"
            "I can write some from it, but **AI-written questions can be wrong or ambiguous**. They'll be labelled ⚠️ "
            "everywhere they appear, and anyone can flag them. Questions from real past papers or worksheets are always better.",
            view=GenerateOffer(self, interaction.user.id, deck_id, deck),
        )

    @upload_cmd.autocomplete("deck")
    async def _upload_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    @upload_cmd.autocomplete("subject")
    async def _subject_ac(self, interaction, current):
        known = self.store.subjects(interaction.guild_id or 0, current)
        common = [s for s in COMMON_SUBJECTS if s.startswith(current.lower()) and s not in known]
        return [app_commands.Choice(name=f"{quality.subject_emoji(s)} {s}", value=s) for s in (known + common)[:25]]

    @app_commands.command(name="generate", description="⚠️ Have AI write questions from a deck's notes (when the files had none)")
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
            await interaction.response.send_message(f"No deck called **{deck}**. Add material with `/upload` first.", ephemeral=True)
            return
        await self.run_generation(interaction, deck_id, deck, count, focus)

    async def run_generation(
        self, interaction: discord.Interaction, deck_id: int, deck: str, count: int, focus: Optional[str] = None
    ) -> None:
        passages = self.store.pick_chunks(deck_id, math.ceil(count / QUESTIONS_PER_PASSAGE) + 1, focus)
        if not passages:
            await interaction.response.send_message(f"**{deck}** has no material yet.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✍️ Writing questions for **{deck}** from {len(passages)} passages. Each one is drafted, "
            "answered blind by a second pass, then reviewed, and weak ones are thrown out. They'll still be "
            "marked ⚠️ AI-written. This takes a minute or two…"
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

        lines = [f"✅ Added **{accepted}** ⚠️ AI-written question(s) to **{deck}** (from {written} drafts)."]
        if rejected:
            lines.append(f"Rejected {len(rejected)} that didn't meet the bar, e.g.:")
            lines += [f"• _{clip(stem, 80)}_ — {clip(reason, 120)}" for stem, reason in rejected[:4]]
        if errors:
            lines.append(f"⚠️ {errors} passage(s) failed (model error or rate limit). Try again shortly.")
        if accepted:
            lines.append("Play them with `/quiz`.")
        await interaction.edit_original_response(content=clip("\n".join(lines), 1990))

    @generate_cmd.autocomplete("deck")
    async def _generate_ac(self, interaction, current):
        return await self.deck_autocomplete(interaction, current)

    @app_commands.command(name="quiz", description="Pick subjects and question sets, then play solo (private) or live with everyone")
    @app_commands.guild_only()
    async def quiz_cmd(self, interaction: discord.Interaction):
        picker = play.QuizPicker(self.store, interaction.guild_id, interaction.user.id)
        if not picker.visible_sets():
            await interaction.response.send_message("No questions yet. Add a file with `/upload` first.", ephemeral=True)
            return
        await interaction.response.send_message(embed=picker.embed(), view=picker, ephemeral=True)

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

    @app_commands.command(name="library", description="Browse every subject and question set in this server")
    @app_commands.guild_only()
    async def library_cmd(self, interaction: discord.Interaction):
        rows = self.store.library(interaction.guild_id)
        if not rows:
            await interaction.response.send_message("The library is empty. Start with `/upload`.", ephemeral=True)
            return
        embed = discord.Embed(title="📚 Library", colour=0x5865F2)
        by_subject: dict[str, list] = {}
        for r in rows:
            by_subject.setdefault(r["subject"], []).append(r)
        for subject, sets in list(by_subject.items())[:25]:
            lines = [f"`{r['name']}` — {play.set_summary(r)}" for r in sets]
            embed.add_field(
                name=f"{quality.subject_emoji(subject)} {subject.title()}", value=clip("\n".join(lines), FIELD_LIMIT), inline=False
            )
        embed.set_footer(text=quality.LEGEND + " · /quiz to play")
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
