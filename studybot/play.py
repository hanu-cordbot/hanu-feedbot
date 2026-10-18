"""Quiz front end: the /quiz picker, private solo runs and Quizizz-style live games.

Solo runs are ephemeral, so only the player sees questions, picks and results. Their
state lives in the quiz_runs table and buttons carry the run id, so a solo quiz
survives a bot restart.

Live games post one public message per question showing the stem, the options, a
countdown and "🙋 N answered". There are no answer buttons and no reaction counts on it.
Pressing ✋ Answer opens a private popup with the options, so nobody can spoil the
answer from the channel. After the timer (or the host's ⏭) the message reveals the
answer, the distribution, the explanation and a leaderboard. Live state is in memory.
"""
import asyncio
import itertools
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import discord

from . import quality
from .db import Store
from .render import FIELD_LIMIT, LETTERS, add_teaching_fields, answered_embed, clip, options_block, question_embed

log = logging.getLogger(__name__)

LENGTHS = (5, 10, 15, 20)
TIME_LIMITS = (10, 20, 30, 60)
COUNTER_EDIT_GAP = 2.0  # seconds between public "N answered" edits (rate limits)
# Starting from the clock means ids from before a restart never collide with new games.
_game_ids = itertools.count(int(time.time()))


def store_of(interaction: discord.Interaction) -> Store:
    return interaction.client.store  # type: ignore[attr-defined]


# --- shared buttons ------------------------------------------------------------

class RateButton(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:r:(?P<q>\d+):(?P<v>[ud])"):
    def __init__(self, qid: int, up: bool):
        self.qid, self.up = qid, up
        super().__init__(discord.ui.Button(
            emoji="👍" if up else "👎", style=discord.ButtonStyle.secondary, custom_id=f"sb:r:{qid}:{'u' if up else 'd'}"
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["q"]), match["v"] == "u")

    async def callback(self, interaction: discord.Interaction) -> None:
        net = store_of(interaction).rate_question(self.qid, interaction.user.id, 1 if self.up else -1)
        star = " It's now a ⭐ favourite." if net >= quality.FAVOURITE_AT else ""
        await interaction.response.send_message(
            f"Thanks, rated {'👍' if self.up else '👎'}. Better-rated questions come up more often.{star}", ephemeral=True
        )


class FlagButton(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:f:(?P<q>\d+)"):
    def __init__(self, qid: int):
        self.qid = qid
        super().__init__(discord.ui.Button(emoji="🚩", label="Flag", style=discord.ButtonStyle.secondary, custom_id=f"sb:f:{qid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["q"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        retired = store_of(interaction).flag_question(self.qid, interaction.user.id)
        msg = "Thanks — flagged for review."
        if retired:
            msg += " Enough people flagged it, so it's been pulled from rotation."
        await interaction.response.send_message(msg, ephemeral=True)


def feedback_items(qid: int) -> list[discord.ui.Item]:
    return [RateButton(qid, True), RateButton(qid, False), FlagButton(qid)]


# --- solo (private) ------------------------------------------------------------

def solo_question(store: Store, run: dict) -> tuple[discord.Embed, discord.ui.View]:
    pos = run["position"]
    q = store.get_question(run["question_ids"][pos])
    view = discord.ui.View(timeout=None)
    for i in range(len(q["options"])):
        view.add_item(SoloAnswer(run["id"], pos, i))
    return question_embed(q, pos + 1, len(run["question_ids"])), view


def solo_summary(run: dict) -> discord.Embed:
    total, right = len(run["question_ids"]), run["correct"]
    pct = round(100 * right / total) if total else 0
    medal = "🏆" if pct >= 90 else "🎉" if pct >= 70 else "💪"
    return discord.Embed(
        title=f"{medal} {right}/{total} correct ({pct}%)",
        description="Run `/quiz` again for a fresh mix. Questions you missed come up more often.",
        colour=0xFEE75C,
    )


async def start_solo(interaction: discord.Interaction, question_ids: list[int]) -> None:
    store = store_of(interaction)
    run = store.get_run(store.create_run(interaction.user.id, question_ids))
    embed, view = solo_question(store, run)
    await interaction.response.edit_message(content=None, embed=embed, view=view)


class SoloAnswer(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:sa:(?P<r>\d+):(?P<p>\d+):(?P<c>\d)"):
    def __init__(self, run_id: int, pos: int, choice: int):
        self.run_id, self.pos, self.choice = run_id, pos, choice
        super().__init__(discord.ui.Button(
            label=LETTERS[choice], style=discord.ButtonStyle.secondary, custom_id=f"sb:sa:{run_id}:{pos}:{choice}"
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["r"]), int(match["p"]), int(match["c"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        store = store_of(interaction)
        run = store.get_run(self.run_id)
        if not run or run["user_id"] != interaction.user.id:
            await interaction.response.send_message("This isn't your quiz. Start one with `/quiz`.", ephemeral=True)
            return
        q = store.get_question(run["question_ids"][self.pos])
        correct = self.choice == q["correct_index"]
        if not store.advance_run(self.run_id, self.pos, correct):
            await interaction.response.send_message("You already answered that one.", ephemeral=True)
            return
        store.record_attempt(q["id"], interaction.user.id, self.choice, correct)
        total = len(run["question_ids"])
        view = discord.ui.View(timeout=None)
        last = self.pos + 1 >= total
        view.add_item(SoloNext(self.run_id, last))
        for item in feedback_items(q["id"]):
            view.add_item(item)
        await interaction.response.edit_message(embed=answered_embed(q, self.choice, self.pos + 1, total), view=view)


class SoloNext(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:sn:(?P<r>\d+)"):
    def __init__(self, run_id: int, last: bool = False):
        self.run_id = run_id
        super().__init__(discord.ui.Button(
            label="See score" if last else "Next ▶", style=discord.ButtonStyle.primary, custom_id=f"sb:sn:{run_id}"
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["r"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        store = store_of(interaction)
        run = store.get_run(self.run_id)
        if not run or run["user_id"] != interaction.user.id:
            await interaction.response.send_message("This isn't your quiz. Start one with `/quiz`.", ephemeral=True)
            return
        if run["position"] >= len(run["question_ids"]):
            await interaction.response.edit_message(embed=solo_summary(run), view=None)
            return
        embed, view = solo_question(store, run)
        await interaction.response.edit_message(embed=embed, view=view)


# --- live (everyone) -----------------------------------------------------------

@dataclass
class LiveGame:
    id: int
    host_id: int
    channel: discord.abc.Messageable
    question_ids: list[int]
    time_limit: int
    index: int = -1
    question: Optional[dict] = None
    message: Optional[discord.Message] = None
    deadline: float = 0.0
    revealed: bool = False
    answers: dict[int, tuple[int, float]] = field(default_factory=dict)  # user -> (choice, seconds left)
    scores: dict[int, int] = field(default_factory=dict)
    streaks: dict[int, int] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    timer: Optional[asyncio.Task] = None
    counter_pending: bool = False
    last_counter_edit: float = 0.0

    @property
    def total(self) -> int:
        return len(self.question_ids)


def points_for(correct: bool, seconds_left: float, time_limit: int, streak: int) -> int:
    """Quizizz-style: 500–1000 for a correct answer depending on speed, plus a streak bonus."""
    if not correct:
        return 0
    speed = 500 + round(500 * max(0.0, min(1.0, seconds_left / time_limit)))
    return speed + min(streak, 5) * 50


def leaderboard(game: LiveGame, limit: int = 5) -> str:
    ranked = sorted(game.scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    medals = ["🥇", "🥈", "🥉"]
    return "\n".join(
        f"{medals[i] if i < 3 else f'`{i + 1}.`'} {game.names.get(uid, 'someone')} — **{pts:,}**"
        for i, (uid, pts) in enumerate(ranked)
    ) or "Nobody has scored yet."


def live_question_embed(game: LiveGame) -> discord.Embed:
    q = game.question
    embed = discord.Embed(
        title=f"🎮 Question {game.index + 1} of {game.total}",
        description=clip(f"**{q['stem']}**\n\n{options_block(q)}", 4000),
        colour=0x9B59B6,
    )
    embed.add_field(name="​", value=f"🙋 **{len(game.answers)}** answered · ⏱️ ends <t:{int(game.deadline)}:R>", inline=False)
    embed.set_footer(text=f"{quality.labels(q)} · Press ✋ Answer — your pick stays private")
    return embed


def live_reveal_embed(game: LiveGame) -> discord.Embed:
    q = game.question
    counts = [0] * len(q["options"])
    for choice, _ in game.answers.values():
        counts[choice] += 1
    n = max(1, len(game.answers))
    lines = []
    for i, opt in enumerate(q["options"]):
        bar = "▰" * round(8 * counts[i] / n) + "▱" * (8 - round(8 * counts[i] / n))
        mark = "✅" if i == q["correct_index"] else "▫️"
        lines.append(f"{mark} **{LETTERS[i]}.** {opt}\n{bar} {counts[i]}")
    right = counts[q["correct_index"]]
    embed = discord.Embed(
        title=f"🎮 Question {game.index + 1} of {game.total} — answer: {LETTERS[q['correct_index']]}",
        description=clip(f"**{q['stem']}**\n\n" + "\n".join(lines), 4000),
        colour=0x57F287,
    )
    embed.add_field(name="Results", value=f"{right}/{len(game.answers)} got it right", inline=False)
    add_teaching_fields(embed, q)
    embed.add_field(name="Leaderboard", value=clip(leaderboard(game), FIELD_LIMIT), inline=False)
    embed.set_footer(text=quality.labels(q))
    return embed


def live_controls(game: LiveGame, revealed: bool) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if revealed:
        last = game.index + 1 >= game.total
        view.add_item(LiveHost(game.id, "next", "🏁 Final results" if last else "Next ▶"))
        for item in feedback_items(game.question["id"]):
            view.add_item(item)
    else:
        view.add_item(LiveJoin(game.id, game.index))
        view.add_item(LiveHost(game.id, "reveal", "⏭ Reveal"))
    view.add_item(LiveHost(game.id, "end", "⏹ End"))
    return view


async def start_live(interaction: discord.Interaction, question_ids: list[int], time_limit: int) -> None:
    bot = interaction.client
    game = LiveGame(next(_game_ids), interaction.user.id, interaction.channel, question_ids, time_limit)
    bot.live_games[game.id] = game  # type: ignore[attr-defined]
    await interaction.response.edit_message(content="🎮 Live game started in the channel.", embed=None, view=None)
    await interaction.channel.send(
        f"🎮 **Live quiz** hosted by {interaction.user.mention}: {game.total} questions, {time_limit}s each. "
        "Press **✋ Answer** on each question. Your pick stays private, fastest correct answers score most."
    )
    await ask_next(bot, game)


async def ask_next(bot, game: LiveGame) -> None:
    game.index += 1
    if game.index >= game.total:
        await finish(bot, game)
        return
    game.question = bot.store.get_question(game.question_ids[game.index])
    game.answers, game.revealed = {}, False
    game.deadline = time.time() + game.time_limit
    game.message = await game.channel.send(embed=live_question_embed(game), view=live_controls(game, False))
    index = game.index

    async def timer():
        await asyncio.sleep(game.time_limit)
        await reveal(game, index)

    game.timer = asyncio.create_task(timer())


async def reveal(game: LiveGame, index: int) -> None:
    if game.revealed or game.index != index:
        return
    game.revealed = True
    if game.timer and game.timer is not asyncio.current_task():
        game.timer.cancel()
    for uid in game.scores:
        if uid not in game.answers:
            game.streaks[uid] = 0
    try:
        await game.message.edit(embed=live_reveal_embed(game), view=live_controls(game, True))
    except discord.HTTPException:
        log.exception("Couldn't reveal live question")


async def finish(bot, game: LiveGame, ended_early: bool = False) -> None:
    bot.live_games.pop(game.id, None)
    if game.timer:
        game.timer.cancel()
    ranked = sorted(game.scores.items(), key=lambda kv: kv[1], reverse=True)
    podium = "\n".join(
        f"{['🥇', '🥈', '🥉'][i]} **{game.names.get(uid, 'someone')}** — {pts:,}" for i, (uid, pts) in enumerate(ranked[:3])
    )
    rest = ", ".join(f"{game.names.get(uid, 'someone')} {pts:,}" for uid, pts in ranked[3:])
    embed = discord.Embed(
        title="🏁 Game over" + (" (ended early)" if ended_early else ""),
        description=podium or "Nobody answered this time.",
        colour=0xFEE75C,
    )
    if rest:
        embed.add_field(name="Everyone else", value=clip(rest, FIELD_LIMIT), inline=False)
    embed.set_footer(text="Start another with /quiz")
    await game.channel.send(embed=embed)


async def bump_counter(game: LiveGame) -> None:
    """Updates "🙋 N answered" at most once every COUNTER_EDIT_GAP seconds."""
    if game.counter_pending:
        return
    game.counter_pending = True
    try:
        await asyncio.sleep(max(0.0, game.last_counter_edit + COUNTER_EDIT_GAP - time.monotonic()))
        if not game.revealed and game.message:
            await game.message.edit(embed=live_question_embed(game))
            game.last_counter_edit = time.monotonic()
    except discord.HTTPException:
        pass
    finally:
        game.counter_pending = False


def live_game(interaction: discord.Interaction, game_id: int) -> Optional[LiveGame]:
    return interaction.client.live_games.get(game_id)  # type: ignore[attr-defined]


ENDED = "This live game has ended. Start a new one with `/quiz`."


class LiveJoin(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:lj:(?P<g>\d+):(?P<i>\d+)"):
    def __init__(self, game_id: int, index: int):
        self.game_id, self.index = game_id, index
        super().__init__(discord.ui.Button(
            label="Answer", emoji="✋", style=discord.ButtonStyle.success, custom_id=f"sb:lj:{game_id}:{index}"
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["g"]), int(match["i"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        game = live_game(interaction, self.game_id)
        if not game:
            await interaction.response.send_message(ENDED, ephemeral=True)
            return
        if game.index != self.index or game.revealed:
            await interaction.response.send_message("That question is closed. Wait for the next one!", ephemeral=True)
            return
        if interaction.user.id in game.answers:
            choice = game.answers[interaction.user.id][0]
            await interaction.response.send_message(f"You're locked in on **{LETTERS[choice]}**.", ephemeral=True)
            return
        q = game.question
        view = discord.ui.View(timeout=game.time_limit + 5)
        for i in range(len(q["options"])):
            view.add_item(LivePick(game.id, game.index, i))
        embed = discord.Embed(description=clip(f"**{q['stem']}**\n\n{options_block(q)}", 4000), colour=0x9B59B6)
        embed.set_footer(text=f"Only you can see this · ends in about {max(0, int(game.deadline - time.time()))}s")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class LivePick(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:lp:(?P<g>\d+):(?P<i>\d+):(?P<c>\d)"):
    def __init__(self, game_id: int, index: int, choice: int):
        self.game_id, self.index, self.choice = game_id, index, choice
        super().__init__(discord.ui.Button(
            label=LETTERS[choice], style=discord.ButtonStyle.primary, custom_id=f"sb:lp:{game_id}:{index}:{choice}"
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["g"]), int(match["i"]), int(match["c"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        game = live_game(interaction, self.game_id)
        if not game:
            await interaction.response.edit_message(content=ENDED, embed=None, view=None)
            return
        left = game.deadline - time.time()
        uid = interaction.user.id
        if game.index != self.index or game.revealed or left <= 0:
            await interaction.response.edit_message(content="⏰ Time's up for that one.", embed=None, view=None)
            return
        if uid in game.answers:
            await interaction.response.edit_message(
                content=f"You're already locked in on **{LETTERS[game.answers[uid][0]]}**.", embed=None, view=None
            )
            return
        q = game.question
        correct = self.choice == q["correct_index"]
        game.answers[uid] = (self.choice, left)
        game.names[uid] = interaction.user.display_name
        streak = game.streaks.get(uid, 0) + 1 if correct else 0
        game.streaks[uid] = streak
        pts = points_for(correct, left, game.time_limit, streak - 1 if correct else 0)
        game.scores[uid] = game.scores.get(uid, 0) + pts
        interaction.client.store.record_attempt(q["id"], uid, self.choice, correct)  # type: ignore[attr-defined]
        fire = f" · 🔥 {streak} in a row" if streak >= 2 else ""
        verdict = f"✅ Correct! **+{pts}**{fire}" if correct else "❌ Not this time"
        await interaction.response.edit_message(
            content=f"Locked in **{LETTERS[self.choice]}**. {verdict}\nTotal: {game.scores[uid]:,} · answer revealed when time's up.",
            embed=None, view=None,
        )
        asyncio.create_task(bump_counter(game))


class LiveHost(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:lh:(?P<g>\d+):(?P<a>next|reveal|end)"):
    STYLES = {"next": discord.ButtonStyle.primary, "reveal": discord.ButtonStyle.secondary, "end": discord.ButtonStyle.danger}

    def __init__(self, game_id: int, action: str, label: Optional[str] = None):
        self.game_id, self.action = game_id, action
        super().__init__(discord.ui.Button(
            label=label or {"next": "Next ▶", "reveal": "⏭ Reveal", "end": "⏹ End"}[action],
            style=self.STYLES[action], custom_id=f"sb:lh:{game_id}:{action}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["g"]), match["a"])

    async def callback(self, interaction: discord.Interaction) -> None:
        game = live_game(interaction, self.game_id)
        if not game:
            await interaction.response.send_message(ENDED, ephemeral=True)
            return
        if interaction.user.id != game.host_id:
            await interaction.response.send_message("Only the host can do that — hang tight!", ephemeral=True)
            return
        await interaction.response.defer()
        if self.action == "reveal":
            await reveal(game, game.index)
        elif self.action == "next":
            if not game.revealed:
                return
            await game.message.edit(view=live_controls_after_next(game))
            await ask_next(interaction.client, game)
        else:
            if game.message and not game.revealed:
                await reveal(game, game.index)
            await finish(interaction.client, game, ended_early=game.index + 1 < game.total)


def live_controls_after_next(game: LiveGame) -> discord.ui.View:
    """Once the host moves on, the old message keeps only the rating buttons."""
    view = discord.ui.View(timeout=None)
    for item in feedback_items(game.question["id"]):
        view.add_item(item)
    return view


# --- the /quiz picker ----------------------------------------------------------

class QuizPicker(discord.ui.View):
    """Ephemeral panel: subject → question sets → length → time → Solo / Live."""

    def __init__(self, store: Store, guild_id: int, owner: int):
        super().__init__(timeout=900)
        self.store, self.guild_id, self.owner = store, guild_id, owner
        self.sets = list(store.library(guild_id))
        self.subject: Optional[str] = None
        self.chosen: set[int] = {r["id"] for r in self.sets if r["questions"]}
        self.length, self.time_limit = 10, 20
        self.build()

    def visible_sets(self) -> list:
        rows = [r for r in self.sets if r["questions"] and (self.subject is None or r["subject"] == self.subject)]
        return sorted(rows, key=lambda r: r["questions"], reverse=True)[:25]

    def build(self) -> None:
        self.clear_items()
        subjects = sorted({r["subject"] for r in self.sets if r["questions"]})
        subject_opts = [discord.SelectOption(label="All subjects", value="*", emoji="🗂️", default=self.subject is None)]
        subject_opts += [
            discord.SelectOption(label=s.title()[:100], value=s[:100], emoji=quality.subject_emoji(s), default=s == self.subject)
            for s in subjects[:24]
        ]
        sub = discord.ui.Select(placeholder="Subject", options=subject_opts, row=0)
        sub.callback = self.on_subject
        self.add_item(sub)

        rows = self.visible_sets()
        if rows:
            set_opts = [
                discord.SelectOption(
                    label=r["name"][:100], value=str(r["id"]), emoji=quality.subject_emoji(r["subject"]),
                    description=clip(set_summary(r), 100), default=r["id"] in self.chosen,
                )
                for r in rows
            ]
            pick = discord.ui.Select(placeholder="Question sets", options=set_opts, min_values=1, max_values=len(set_opts), row=1)
            pick.callback = self.on_sets
            self.add_item(pick)

        length = discord.ui.Select(row=2, options=[
            discord.SelectOption(label=f"{n} questions", value=str(n), default=n == self.length) for n in LENGTHS
        ])
        length.callback = self.on_length
        self.add_item(length)
        timer = discord.ui.Select(row=3, options=[
            discord.SelectOption(label=f"{t} seconds per question (live)", value=str(t), emoji="⏱️", default=t == self.time_limit)
            for t in TIME_LIMITS
        ])
        timer.callback = self.on_time
        self.add_item(timer)

        solo = discord.ui.Button(label="Solo (private)", emoji="🧑‍🎓", style=discord.ButtonStyle.primary, row=4)
        solo.callback = self.on_solo
        live = discord.ui.Button(label="Live for everyone", emoji="🎮", style=discord.ButtonStyle.success, row=4)
        live.callback = self.on_live
        self.add_item(solo)
        self.add_item(live)

    def selected_ids(self) -> list[int]:
        visible = {r["id"] for r in self.visible_sets()}
        return [i for i in self.chosen if i in visible]

    def embed(self) -> discord.Embed:
        ids = set(self.selected_ids())
        rows = [r for r in self.sets if r["id"] in ids]
        count = sum(r["questions"] for r in rows)
        subject = f"{quality.subject_emoji(self.subject)} {self.subject.title()}" if self.subject else "🗂️ All subjects"
        e = discord.Embed(title="📝 Start a quiz", colour=0x5865F2, description=(
            f"**Subject:** {subject}\n**Sets:** {len(rows)} chosen · {count} questions in the pool\n"
            f"**Length:** {self.length} · **Live timer:** {self.time_limit}s\n\n"
            "Questions are a random mix from the chosen sets. Better-rated ones and real questions "
            "from files come up more often."
        ))
        e.set_footer(text=quality.LEGEND)
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.build()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def on_subject(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        self.subject = None if value == "*" else value
        self.chosen = {r["id"] for r in self.visible_sets()}
        await self.refresh(interaction)

    async def on_sets(self, interaction: discord.Interaction) -> None:
        self.chosen = {int(v) for v in interaction.data["values"]}
        await self.refresh(interaction)

    async def on_length(self, interaction: discord.Interaction) -> None:
        self.length = int(interaction.data["values"][0])
        await self.refresh(interaction)

    async def on_time(self, interaction: discord.Interaction) -> None:
        self.time_limit = int(interaction.data["values"][0])
        await self.refresh(interaction)

    def draw(self, personal: bool) -> list[int]:
        pool = self.store.question_pool(self.selected_ids(), self.owner if personal else None)
        return [q["id"] for q in quality.pick(pool, self.length, random.Random(), personal=personal)]

    async def on_solo(self, interaction: discord.Interaction) -> None:
        ids = self.draw(personal=True)
        if not ids:
            await interaction.response.send_message("No questions in those sets yet.", ephemeral=True)
            return
        self.stop()
        await start_solo(interaction, ids)

    async def on_live(self, interaction: discord.Interaction) -> None:
        ids = self.draw(personal=False)
        if not ids:
            await interaction.response.send_message("No questions in those sets yet.", ephemeral=True)
            return
        self.stop()
        await start_live(interaction, ids, self.time_limit)


def set_summary(r) -> str:
    parts = [f"{r['questions']} questions"]
    counts = [("📄", r["from_file"]), ("🤖", r["ai_answer"]), ("✨", r["ai_written"]), ("⭐", r["favourites"])]
    labels = " ".join(f"{e}{n}" for e, n in counts if n)
    return " · ".join(parts + ([labels] if labels else []))


DYNAMIC_ITEMS = (RateButton, FlagButton, SoloAnswer, SoloNext, LiveJoin, LivePick, LiveHost)
