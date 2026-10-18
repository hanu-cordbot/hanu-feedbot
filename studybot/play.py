"""Quiz front end: the /quiz settings panel, private solo runs and Quizizz-style live games.

Questions are drawn as Quizizz-style cards (see cards.py) unless the player turns cards off.

Solo runs are ephemeral, so only the player sees questions, picks and results. Their
state (including settings, picks and when the current question was shown) lives in the
quiz_runs table and buttons carry the run id, so a solo quiz survives a bot restart.

Live games work like Quizizz's shared screen plus each player's phone. The public message
is the shared screen: the question card, a countdown and "🙋 N answered", with no answer
buttons and no counts that could spoil the answer. ✋ Answer opens a private popup (the
player's "phone") showing the card with that player's own score and rank. After the
timer (or the host's ⏭) the public card reveals the answer, how many picked each tile and
a leaderboard, and 📊 My result shows each player their own pick, points and rank.
Live state is in memory.
"""
import asyncio
import io
import itertools
import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Optional

import discord

from . import cards, quality
from .db import Store
from .render import FIELD_LIMIT, LETTERS, add_teaching_fields, clip, teaching_parts

log = logging.getLogger(__name__)

LENGTHS = (5, 10, 15, 20, 25, 30, 40, 50, 0)  # 0 = every question in the pool
TIMERS = (0, 5, 10, 15, 20, 30, 45, 60, 90, 120)  # 0 = no timer (solo only)
LIVE_DEFAULT_TIMER = 20
COUNTER_EDIT_GAP = 2.0  # seconds between public "N answered" edits (rate limits)
SOLO_GRACE = 1.5  # seconds of slack for the solo timer (button round trip)
CARD = "card.png"
PURPLE = 0x8C52FF
# Starting from the clock means ids from before a restart never collide with new games.
_game_ids = itertools.count(int(time.time()))


def store_of(interaction: discord.Interaction) -> Store:
    return interaction.client.store  # type: ignore[attr-defined]


# --- settings ------------------------------------------------------------------

ORDERS = {
    "smart": ("🧠", "Smart mix", "Better-rated and missed questions come up more"),
    "random": ("🎲", "Random", "Any order, every question equally likely"),
    "file": ("📑", "In file order", "Start to finish, as uploaded"),
}
SOURCES = {
    "all": ("🗂️", "All questions", "From files, AI-answered and AI-written"),
    "file": ("📄", "Only answers from the file", "Skips 🤖 AI-suggested answers and ✨ AI-written questions"),
    "no_ai_written": ("📄", "Skip AI-written questions", "Keeps 📄 and 🤖, skips ✨"),
}


@dataclass
class QuizSettings:
    length: int = 10
    timer: int = 20
    order: str = "smart"
    sources: str = "all"
    shuffle: bool = False
    show_answers: bool = True
    leaderboard: bool = True
    speed: bool = True
    streak: bool = True
    cards: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "QuizSettings":
        names = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in (data or {}).items() if k in names})
        if s.order not in ORDERS:
            s.order = "smart"
        if s.sources not in SOURCES:
            s.sources = "all"
        return s

    @property
    def live_timer(self) -> int:
        return self.timer or LIVE_DEFAULT_TIMER


# (attribute, title, explanation) for the on/off switches in the panel.
TOGGLES = (
    ("shuffle", "🔀 Shuffle answer choices", "Mixes A/B/C/D every time. Leave off for questions like \"all of the above\"."),
    ("show_answers", "👀 Show answer after each question", "Solo. Off: you see every answer in a review at the end."),
    ("leaderboard", "🏆 Leaderboard after each question", "Live. Off: scores only appear on the final podium."),
    ("speed", "⚡ Faster answers score more", "Live. 500–1,000 points by speed. Off: every right answer is 1,000."),
    ("streak", "🔥 Streak bonus", "Live. +50 for each answer in a row, up to +250."),
    ("cards", "🖼️ Quizizz-style cards", "Draws each question as a picture. Off: plain text, lighter on data."),
)


def filter_sources(pool: list[dict], sources: str) -> list[dict]:
    if sources == "file":
        return [q for q in pool if quality.source_label(q) == "📄"]
    if sources == "no_ai_written":
        return [q for q in pool if quality.source_label(q) != "✨"]
    return pool


def choose_questions(pool: list[dict], s: QuizSettings, rng: random.Random, personal: bool) -> list[dict]:
    pool = filter_sources(pool, s.sources)
    n = len(pool) if s.length == 0 else min(s.length, len(pool))
    if s.order == "file":
        return sorted(pool, key=lambda q: q["id"])[:n]
    if s.order == "random":
        return rng.sample(pool, n)
    return quality.pick(pool, n, rng, personal=personal)


def option_order(n_options: int, shuffle: bool, seed: str) -> list[int]:
    """Displayed tile -> stored option index. Seeded, so the same question shows the same order after a restart."""
    order = list(range(n_options))
    if shuffle:
        random.Random(seed).shuffle(order)
    return order


# --- drawing helpers -----------------------------------------------------------

def card_file(png: bytes) -> discord.File:
    return discord.File(io.BytesIO(png), filename=CARD)


async def draw(fn, *args, **kwargs) -> Optional[bytes]:
    """Renders a card off the event loop. A drawing failure falls back to text instead of breaking the quiz."""
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Exception:
        log.exception("Card rendering failed")
        return None


def text_options(q: dict, order: list[int], correct: Optional[int] = None, chosen: Optional[int] = None) -> str:
    lines = []
    for shown, stored in enumerate(order):
        mark = ""
        if correct is not None:
            mark = "✅ " if shown == correct else ("❌ " if shown == chosen else "▫️ ")
        lines.append(f"{mark}{cards.TILE_EMOJI[shown]} **{LETTERS[shown]}.** {q['options'][stored]}")
    return "\n".join(lines)


def long_text(q: dict) -> bool:
    """Cards shrink text to fit; when it would get tiny, the text goes in the embed too."""
    return len(q["stem"]) > 320 or any(len(o) > 140 for o in q["options"])


def question_body(q: dict, order: list[int], with_card: bool) -> str:
    if with_card and not long_text(q):
        return ""
    return clip(f"**{q['stem']}**\n\n{text_options(q, order)}", 3800)


def answer_buttons(make, n: int) -> list[discord.ui.Item]:
    return [make(i) for i in range(n)]


def styled(label_index: int, custom_id: str) -> discord.ui.Button:
    return discord.ui.Button(
        label=LETTERS[label_index], emoji=cards.TILE_EMOJI[label_index], style=discord.ButtonStyle.secondary,
        custom_id=custom_id,
    )


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
# Solo uses Discord's newer message layout, so the /quiz panel itself turns into the quiz:
# one private message from settings to final score.

def run_settings(run: dict) -> QuizSettings:
    return QuizSettings.from_dict(run.get("settings"))


def run_order(run: dict, q: dict, pos: int) -> list[int]:
    return option_order(len(q["options"]), run_settings(run).shuffle, f"solo:{run['id']}:{pos}")


def solo_layout(colour: int, parts: list, files: list[discord.File]) -> discord.ui.LayoutView:
    """`parts` are strings (text blocks), "card" (the drawn card, if any) or lists of buttons (one row each)."""
    view = discord.ui.LayoutView(timeout=None)
    children: list[discord.ui.Item] = []
    for part in parts:
        if part == "card":
            if files:
                children.append(discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{CARD}")))
        elif isinstance(part, list):
            if part:
                children.append(discord.ui.ActionRow(*part))
        elif part:
            children.append(discord.ui.TextDisplay(clip(part, 3500)))
    view.add_item(discord.ui.Container(*children, accent_colour=colour))
    return view


async def solo_question(store: Store, run: dict) -> tuple[discord.ui.LayoutView, list[discord.File]]:
    pos = run["position"]
    total = len(run["question_ids"])
    q = store.get_question(run["question_ids"][pos])
    s = run_settings(run)
    order = run_order(run, q, pos)
    now = time.time()
    store.mark_asked(run["id"], now)
    png = await draw(cards.question_card, q, pos + 1, total, order=order, right=f"{run['correct']} correct",
                     timer=f"{s.timer}s" if s.timer else None) if s.cards else None
    files = [card_file(png)] if png else []
    header = f"### Question {pos + 1} of {total}"
    if s.timer:
        header += f" · ⏱️ time's up <t:{int(now + s.timer)}:R>"
    buttons = answer_buttons(lambda i: SoloAnswer(run["id"], pos, i), len(order))
    rows = [buttons[:5], buttons[5:]]
    parts = [header, "card", question_body(q, order, png is not None), *rows,
             f"-# {quality.labels(q)} · only you can see this"]
    return solo_layout(PURPLE, parts, files), files


async def solo_summary(store: Store, run: dict) -> tuple[discord.ui.LayoutView, list[discord.File]]:
    total, right = len(run["question_ids"]), run["correct"]
    pct = round(100 * right / total) if total else 0
    medal = "🏆" if pct >= 90 else "🎉" if pct >= 70 else "💪"
    s = run_settings(run)
    lines = []
    if not s.show_answers:
        for i, qid in enumerate(run["question_ids"]):
            q = store.get_question(qid)
            pick = run["picks"][i] if i < len(run["picks"]) else None
            ok = pick == q["correct_index"]
            yours = "⏰ no answer" if pick is None else clip(q["options"][pick], 60)
            fix = "" if ok else f" → **{clip(q['options'][q['correct_index']], 80)}**"
            lines.append(f"{'✅' if ok else '❌'} {clip(q['stem'], 90)}\n  you: {yours}{fix}")
    png = await draw(cards.score_card, right, total) if s.cards else None
    files = [card_file(png)] if png else []
    parts = [f"## {medal} {right}/{total} correct ({pct}%)", "card", "\n".join(lines),
             "-# Run `/quiz` again for a fresh mix. Questions you missed come up more often."]
    return solo_layout(0xFEE75C, parts, files), files


async def start_solo(interaction: discord.Interaction, question_ids: list[int], settings: QuizSettings) -> None:
    store = store_of(interaction)
    run = store.get_run(store.create_run(interaction.user.id, question_ids, settings.to_dict()))
    view, files = await solo_question(store, run)
    await interaction.response.edit_message(view=view, attachments=files)


class SoloAnswer(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:sa:(?P<r>\d+):(?P<p>\d+):(?P<c>\d)"):
    def __init__(self, run_id: int, pos: int, choice: int):
        self.run_id, self.pos, self.choice = run_id, pos, choice
        super().__init__(styled(choice, f"sb:sa:{run_id}:{pos}:{choice}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["r"]), int(match["p"]), int(match["c"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        store = store_of(interaction)
        run = store.get_run(self.run_id)
        if not run or run["user_id"] != interaction.user.id:
            await interaction.response.send_message("This isn't your quiz. Start one with `/quiz`.", ephemeral=True,
                                                    delete_after=8)
            return
        s = run_settings(run)
        q = store.get_question(run["question_ids"][self.pos])
        order = run_order(run, q, self.pos)
        stored = order[self.choice]
        late = bool(s.timer) and time.time() - (run.get("asked_at") or 0) > s.timer + SOLO_GRACE
        correct = stored == q["correct_index"] and not late
        if not store.advance_run(self.run_id, self.pos, correct, None if late else stored):
            await interaction.response.send_message("You already answered that one.", ephemeral=True, delete_after=5)
            return
        if not late:
            store.record_attempt(q["id"], interaction.user.id, stored, correct)
        total = len(run["question_ids"])
        number = self.pos + 1
        controls = [SoloNext(self.run_id, self.pos + 1 >= total), *feedback_items(q["id"])]

        if not s.show_answers:
            note = "⏰ Too slow — that one counts as missed." if late else f"🔒 Locked in **{LETTERS[self.choice]}**."
            view = solo_layout(PURPLE, [f"### Question {number} of {total}", note + " Answers are shown at the end.",
                                        controls], [])
            await interaction.response.edit_message(view=view, attachments=[])
            return

        verdict = "⏰ Too slow" if late else ("Correct!" if correct else "Not quite")
        shown_correct = order.index(q["correct_index"])
        png = await draw(cards.reveal_card, q, number, total, order=order, chosen=self.choice, banner=verdict,
                         right=f"{run['correct'] + int(correct)} correct") if s.cards else None
        files = [card_file(png)] if png else []
        body = "" if png and not long_text(q) else f"**{q['stem']}**\n\n" + text_options(q, order, shown_correct, self.choice)
        teaching = "\n".join(f"**{name}**\n{value}" for name, value in teaching_parts(q, stored))
        parts = [f"### Question {number} of {total} — {verdict}", "card", body, teaching, controls,
                 f"-# {quality.labels(q)} · was this a good question? 👍 👎 🚩"]
        view = solo_layout(0x57F287 if correct else 0xED4245, parts, files)
        await interaction.response.edit_message(view=view, attachments=files)


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
            await interaction.response.send_message("This isn't your quiz. Start one with `/quiz`.", ephemeral=True,
                                                    delete_after=8)
            return
        if run["position"] >= len(run["question_ids"]):
            view, files = await solo_summary(store, run)
        else:
            view, files = await solo_question(store, run)
        await interaction.response.edit_message(view=view, attachments=files)


# --- live (everyone) -----------------------------------------------------------
# The whole game is one public message, edited in place: question → reveal → next question → podium.
# A/B/C/D sit right on it. Discord shows a click only to the person clicking, so everyone can
# answer at once without anyone seeing anyone else's pick. Each click gets a private text reply
# (pick, points, rank), and those replies are deleted when the answer is revealed.

@dataclass
class LiveGame:
    id: int
    host_id: int
    channel: discord.abc.Messageable
    question_ids: list[int]
    time_limit: int
    settings: QuizSettings = field(default_factory=QuizSettings)
    host_name: str = "the host"
    index: int = -1
    question: Optional[dict] = None
    order: list[int] = field(default_factory=list)  # displayed tile -> stored option index
    card: Optional[bytes] = None
    message: Optional[discord.Message] = None
    deadline: float = 0.0
    revealed: bool = False
    answers: dict[int, tuple[int, float]] = field(default_factory=dict)  # user -> (displayed choice, seconds left)
    gained: dict[int, int] = field(default_factory=dict)  # user -> points on the current question
    scores: dict[int, int] = field(default_factory=dict)
    streaks: dict[int, int] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    receipts: list[discord.Interaction] = field(default_factory=list)  # private replies to delete later
    timer: Optional[asyncio.Task] = None
    counter_pending: bool = False
    last_counter_edit: float = 0.0

    @property
    def total(self) -> int:
        return len(self.question_ids)

    @property
    def shown_correct(self) -> int:
        return self.order.index(self.question["correct_index"])

    def rank(self, uid: int) -> tuple[int, int]:
        """(place, players) by score; ties share a place."""
        mine = self.scores.get(uid, 0)
        return 1 + sum(1 for v in self.scores.values() if v > mine), max(1, len(self.scores))


def points_for(correct: bool, seconds_left: float, time_limit: int, streak: int,
               speed: bool = True, streak_bonus: bool = True) -> int:
    """Quizizz-style: 500–1000 for a correct answer depending on speed, plus a streak bonus."""
    if not correct:
        return 0
    base = 500 + round(500 * max(0.0, min(1.0, seconds_left / time_limit))) if speed else 1000
    return base + (min(streak, 5) * 50 if streak_bonus else 0)


def leaderboard(game: LiveGame, limit: int = 5) -> str:
    ranked = sorted(game.scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    medals = ["🥇", "🥈", "🥉"]
    return "\n".join(
        f"{medals[i] if i < 3 else f'`{i + 1}.`'} {game.names.get(uid, 'someone')} — **{pts:,}**"
        for i, (uid, pts) in enumerate(ranked)
    ) or "Nobody has scored yet."


def live_header(game: LiveGame) -> str:
    rules = [f"{game.total} questions", f"{game.time_limit}s each",
             "faster = more points" if game.settings.speed else "1,000 per right answer"]
    if game.settings.streak:
        rules.append("🔥 streak bonus")
    return f"🎮 **Live quiz** hosted by **{game.host_name}** · {' · '.join(rules)}"


def live_question_embed(game: LiveGame) -> discord.Embed:
    q = game.question
    embed = discord.Embed(
        title=f"🎮 Question {game.index + 1} of {game.total}",
        description=question_body(q, game.order, game.card is not None),
        colour=PURPLE,
    )
    embed.add_field(name="​", value=f"🙋 **{len(game.answers)}** answered · ⏱️ ends <t:{int(game.deadline)}:R>", inline=False)
    embed.set_footer(text=f"{quality.labels(q)} · Tap a letter: only you see your pick")
    if game.card:
        embed.set_image(url=f"attachment://{CARD}")
    return embed


def live_counts(game: LiveGame) -> list[int]:
    counts = [0] * len(game.order)
    for choice, _ in game.answers.values():
        counts[choice] += 1
    return counts


def live_reveal_embed(game: LiveGame, with_card: bool) -> discord.Embed:
    q = game.question
    counts = live_counts(game)
    correct = game.shown_correct
    embed = discord.Embed(
        title=f"🎮 Question {game.index + 1} of {game.total} — answer: {LETTERS[correct]}",
        colour=0x57F287,
    )
    if not with_card or long_text(q):
        lines = []
        n = max(1, len(game.answers))
        for shown, stored in enumerate(game.order):
            bar = "▰" * round(8 * counts[shown] / n) + "▱" * (8 - round(8 * counts[shown] / n))
            mark = "✅" if shown == correct else "▫️"
            lines.append(f"{mark} {cards.TILE_EMOJI[shown]} **{LETTERS[shown]}.** {q['options'][stored]}\n{bar} {counts[shown]}")
        embed.description = clip(f"**{q['stem']}**\n\n" + "\n".join(lines), 3800)
    embed.add_field(name="Results", value=f"{counts[correct]}/{len(game.answers)} got it right", inline=False)
    add_teaching_fields(embed, q)
    if game.settings.leaderboard:
        embed.add_field(name="Leaderboard", value=clip(leaderboard(game), FIELD_LIMIT), inline=False)
    embed.set_footer(text=quality.labels(q) + " · 📊 My result shows your own pick and rank")
    if with_card:
        embed.set_image(url=f"attachment://{CARD}")
    return embed


def live_controls(game: LiveGame, revealed: bool) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    if revealed:
        last = game.index + 1 >= game.total
        view.add_item(LiveMine(game.id, game.index))
        view.add_item(LiveHost(game.id, "next", "🏁 Final results" if last else "Next ▶"))
        view.add_item(LiveHost(game.id, "end", "⏹ End"))
        for item in feedback_items(game.question["id"]):
            view.add_item(item)
    else:
        for item in answer_buttons(lambda i: LiveAnswer(game.id, game.index, i), len(game.order)):
            view.add_item(item)
        view.add_item(LiveHost(game.id, "reveal", "⏭ Reveal"))
        view.add_item(LiveHost(game.id, "end", "⏹ End"))
    return view


# A live game posts in the channel as the bot itself, which slash commands alone don't need.
LIVE_PERMISSIONS = {
    "view_channel": "View Channel", "send_messages": "Send Messages", "embed_links": "Embed Links",
    "attach_files": "Attach Files", "read_message_history": "Read Message History",
}


def missing_live_permissions(perms: Optional[discord.Permissions]) -> list[str]:
    if perms is None:
        return []
    return [label for attr, label in LIVE_PERMISSIONS.items() if not getattr(perms, attr, False)]


def permission_help(missing: list[str]) -> str:
    return (
        f"⚠️ I can't run a live game in this channel: I'm missing **{', '.join(missing)}** here.\n"
        "Fix: right-click the channel → **Edit Channel** → **Permissions** → add the bot (or its role) and allow "
        f"{', '.join(missing)}. Or start the live game in a channel I can post in. Solo quizzes work anywhere."
    )


async def start_live(interaction: discord.Interaction, question_ids: list[int], settings: QuizSettings) -> None:
    bot = interaction.client
    game = LiveGame(next(_game_ids), interaction.user.id, interaction.channel, question_ids, settings.live_timer,
                    settings, host_name=interaction.user.display_name)
    await interaction.response.edit_message(view=started_panel("🎮 **Live game starting** in the channel…"))
    bot.live_games[game.id] = game  # type: ignore[attr-defined]
    try:
        await ask_next(bot, game)
    except discord.Forbidden:
        bot.live_games.pop(game.id, None)  # type: ignore[attr-defined]
        if game.timer:
            game.timer.cancel()
        await interaction.edit_original_response(view=started_panel(permission_help(list(LIVE_PERMISSIONS.values()))))
        return
    # The game message is all anyone needs now; the private settings panel goes away.
    try:
        await interaction.delete_original_response()
    except discord.HTTPException:
        pass


async def show(game: LiveGame, **kw) -> None:
    """Posts the game message the first time, then edits that same message."""
    if game.message is None:
        game.message = await game.channel.send(content=live_header(game), **kw)
    else:
        edited = await game.message.edit(**kw)
        game.message = edited or game.message


async def clean_receipts(game: LiveGame) -> None:
    """Deletes the private replies from this round (interaction tokens last 15 minutes, so this is in time)."""
    receipts, game.receipts = game.receipts, []
    await asyncio.gather(*(i.delete_original_response() for i in receipts), return_exceptions=True)


async def ask_next(bot, game: LiveGame) -> None:
    game.index += 1
    if game.index >= game.total:
        await finish(bot, game)
        return
    await clean_receipts(game)
    game.question = bot.store.get_question(game.question_ids[game.index])
    game.order = option_order(len(game.question["options"]), game.settings.shuffle, f"live:{game.id}:{game.index}")
    game.answers, game.gained, game.revealed = {}, {}, False
    game.card = await draw(cards.question_card, game.question, game.index + 1, game.total, order=game.order,
                           timer=f"{game.time_limit}s") if game.settings.cards else None
    game.deadline = time.time() + game.time_limit
    await show(game, embed=live_question_embed(game), view=live_controls(game, False),
               attachments=[card_file(game.card)] if game.card else [])
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
    png = await draw(cards.reveal_card, game.question, game.index + 1, game.total, order=game.order,
                     counts=live_counts(game), banner=f"Answer: {LETTERS[game.shown_correct]}") if game.settings.cards else None
    try:
        await show(game, embed=live_reveal_embed(game, png is not None), view=live_controls(game, True),
                   attachments=[card_file(png)] if png else [])
    except discord.HTTPException:
        log.exception("Couldn't reveal live question")
    await clean_receipts(game)


async def finish(bot, game: LiveGame, ended_early: bool = False) -> None:
    bot.live_games.pop(game.id, None)
    if game.timer and game.timer is not asyncio.current_task():
        game.timer.cancel()
    await clean_receipts(game)
    ranked = sorted(game.scores.items(), key=lambda kv: kv[1], reverse=True)
    podium = "\n".join(
        f"{['🥇', '🥈', '🥉'][i]} **{game.names.get(uid, 'someone')}** — {pts:,}" for i, (uid, pts) in enumerate(ranked[:3])
    )
    rest = ", ".join(f"{game.names.get(uid, 'someone')} {pts:,}" for uid, pts in ranked[3:])
    title = "🏁 Game over" + (" (ended early)" if ended_early else "")
    embed = discord.Embed(title=title, description=podium or "Nobody answered this time.", colour=0xFEE75C)
    if rest:
        embed.add_field(name="Everyone else", value=clip(rest, FIELD_LIMIT), inline=False)
    embed.set_footer(text="Start another with /quiz")
    files = []
    if game.settings.cards:
        png = await draw(cards.podium_card, [(game.names.get(uid, "someone"), pts) for uid, pts in ranked],
                         "Game over" + (" (ended early)" if ended_early else ""))
        if png:
            embed.set_image(url=f"attachment://{CARD}")
            files.append(card_file(png))
    await show(game, embed=embed, view=None, attachments=files)


async def bump_counter(game: LiveGame) -> None:
    """Updates "🙋 N answered" at most once every COUNTER_EDIT_GAP seconds, without re-uploading the card."""
    if game.counter_pending:
        return
    game.counter_pending = True
    try:
        await asyncio.sleep(max(0.0, game.last_counter_edit + COUNTER_EDIT_GAP - time.monotonic()))
        if not game.revealed and game.message:
            embed = live_question_embed(game)
            # The message already holds the card; point at its uploaded copy instead of sending it again.
            sent = getattr(game.message, "embeds", None)
            if game.card and sent and sent[0].image and sent[0].image.url:
                embed.set_image(url=sent[0].image.url)
            await game.message.edit(embed=embed)
            game.last_counter_edit = time.monotonic()
    except discord.HTTPException:
        pass
    finally:
        game.counter_pending = False


def live_game(interaction: discord.Interaction, game_id: int) -> Optional[LiveGame]:
    return interaction.client.live_games.get(game_id)  # type: ignore[attr-defined]


ENDED = "This live game has ended. Start a new one with `/quiz`."


async def private_note(interaction: discord.Interaction, text: str, seconds: float = 6) -> None:
    await interaction.response.send_message(text, ephemeral=True, delete_after=seconds)


class LiveAnswer(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:la:(?P<g>\d+):(?P<i>\d+):(?P<c>\d)"):
    """A/B/C/D on the public message. The click and the reply are private to the player."""

    def __init__(self, game_id: int, index: int, choice: int):
        self.game_id, self.index, self.choice = game_id, index, choice
        super().__init__(styled(choice, f"sb:la:{game_id}:{index}:{choice}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["g"]), int(match["i"]), int(match["c"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        game = live_game(interaction, self.game_id)
        if not game:
            await private_note(interaction, ENDED)
            return
        left = game.deadline - time.time()
        uid = interaction.user.id
        if game.index != self.index or game.revealed or left <= 0:
            await private_note(interaction, "⏰ Time's up for that one.")
            return
        if uid in game.answers:
            await private_note(interaction, f"You're already locked in on **{LETTERS[game.answers[uid][0]]}**.")
            return
        q = game.question
        stored = game.order[self.choice]
        correct = stored == q["correct_index"]
        game.answers[uid] = (self.choice, left)
        game.names[uid] = interaction.user.display_name
        streak = game.streaks.get(uid, 0) + 1 if correct else 0
        game.streaks[uid] = streak
        s = game.settings
        pts = points_for(correct, left, game.time_limit, streak - 1 if correct else 0, s.speed, s.streak)
        game.gained[uid] = pts
        game.scores[uid] = game.scores.get(uid, 0) + pts
        interaction.client.store.record_attempt(q["id"], uid, stored, correct)  # type: ignore[attr-defined]
        fire = f" · 🔥 {streak} in a row" if streak >= 2 else ""
        verdict = f"✅ **+{pts}**{fire}" if correct else "❌ no points"
        place, players = game.rank(uid)
        await interaction.response.send_message(
            f"🔒 Locked in **{LETTERS[self.choice]}** · {verdict} · total **{game.scores[uid]:,}** · #{place} of {players}",
            ephemeral=True,
        )
        game.receipts.append(interaction)
        asyncio.create_task(bump_counter(game))


class LiveMine(discord.ui.DynamicItem[discord.ui.Button], template=r"sb:lm:(?P<g>\d+):(?P<i>\d+)"):
    """📊 My result on a revealed question: your own pick, points and rank, privately."""

    def __init__(self, game_id: int, index: int):
        self.game_id, self.index = game_id, index
        super().__init__(discord.ui.Button(
            label="My result", emoji="📊", style=discord.ButtonStyle.primary, custom_id=f"sb:lm:{game_id}:{index}"
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match[str]):
        return cls(int(match["g"]), int(match["i"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        game = live_game(interaction, self.game_id)
        if not game:
            await private_note(interaction, ENDED)
            return
        if game.index != self.index:
            await private_note(interaction, "The game has moved on.")
            return
        uid = interaction.user.id
        pick = game.answers.get(uid)
        if pick is None:
            line = "You didn't answer this one."
        else:
            pts = game.gained.get(uid, 0)
            line = f"You picked **{LETTERS[pick[0]]}** · " + (f"✅ +{pts}" if pts else "❌ no points")
        place, players = game.rank(uid)
        streak = game.streaks.get(uid, 0)
        line += f" · total **{game.scores.get(uid, 0):,}** · #{place} of {players}" + (f" · 🔥 {streak}" if streak >= 2 else "")
        await interaction.response.send_message(line, ephemeral=True)
        game.receipts.append(interaction)


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
            await private_note(interaction, ENDED)
            return
        if interaction.user.id != game.host_id:
            await private_note(interaction, "Only the host can do that — hang tight!")
            return
        await interaction.response.defer()
        if self.action == "reveal":
            await reveal(game, game.index)
        elif self.action == "next":
            if game.revealed:
                await ask_next(interaction.client, game)
        else:
            await finish(interaction.client, game, ended_early=game.index + 1 < game.total)


# --- the /quiz settings panel --------------------------------------------------

def started_panel(text: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(discord.ui.Container(discord.ui.TextDisplay(text), accent_colour=PURPLE))
    return view


class QuizPicker(discord.ui.LayoutView):
    """Ephemeral settings panel, laid out like Quizizz's game settings: what to play, then how."""

    def __init__(self, store: Store, guild_id: int, owner: int):
        super().__init__(timeout=900)
        self.store, self.guild_id, self.owner = store, guild_id, owner
        self.sets = list(store.library(guild_id))
        self.settings = QuizSettings.from_dict(store.get_prefs(owner))
        self.subject: Optional[str] = None
        self.chosen: set[int] = {r["id"] for r in self.sets if r["questions"]}
        self.build()

    def visible_sets(self) -> list:
        rows = [r for r in self.sets if r["questions"] and (self.subject is None or r["subject"] == self.subject)]
        return sorted(rows, key=lambda r: r["questions"], reverse=True)[:25]

    def selected_ids(self) -> list[int]:
        visible = {r["id"] for r in self.visible_sets()}
        return [i for i in self.chosen if i in visible]

    def pool_size(self) -> int:
        return len(filter_sources(self.store.question_pool(self.selected_ids()), self.settings.sources))

    def _select(self, callback, options: list[discord.SelectOption], placeholder: str, **kw) -> discord.ui.ActionRow:
        sel = discord.ui.Select(placeholder=placeholder, options=options, **kw)
        sel.callback = callback
        return discord.ui.ActionRow(sel)

    def _toggle(self, attr: str) -> discord.ui.Button:
        on = getattr(self.settings, attr)
        btn = discord.ui.Button(label="On" if on else "Off", style=discord.ButtonStyle.success if on else discord.ButtonStyle.secondary)

        async def flip(interaction: discord.Interaction) -> None:
            setattr(self.settings, attr, not getattr(self.settings, attr))
            await self.refresh(interaction)

        btn.callback = flip
        return btn

    def summary(self) -> str:
        s = self.settings
        ids = set(self.selected_ids())
        rows = [r for r in self.sets if r["id"] in ids]
        pool = self.pool_size()
        subject = f"{quality.subject_emoji(self.subject)} {self.subject.title()}" if self.subject else "🗂️ All subjects"
        length = "every question" if s.length == 0 else f"{min(s.length, pool)} questions"
        timer = f"{s.timer}s timer" if s.timer else f"no timer solo · {LIVE_DEFAULT_TIMER}s live"
        return (f"## 🎯 Start a quiz\n{subject} · **{len(rows)}** sets · **{pool}** questions in the pool\n"
                f"Playing **{length}** · {ORDERS[s.order][1].lower()} · {timer}")

    def build(self) -> None:
        self.clear_items()
        s = self.settings
        subjects = sorted({r["subject"] for r in self.sets if r["questions"]})
        subject_opts = [discord.SelectOption(label="All subjects", value="*", emoji="🗂️", default=self.subject is None)]
        subject_opts += [
            discord.SelectOption(label=x.title()[:100], value=x[:100], emoji=quality.subject_emoji(x), default=x == self.subject)
            for x in subjects[:24]
        ]
        children: list[discord.ui.Item] = [
            discord.ui.TextDisplay(self.summary() + "\n### 📚 What to play"),
            self._select(self.on_subject, subject_opts, "Subject"),
        ]
        rows = self.visible_sets()
        if rows:
            set_opts = [
                discord.SelectOption(
                    label=r["name"][:100], value=str(r["id"]), emoji=quality.subject_emoji(r["subject"]),
                    description=clip(set_summary(r), 100), default=r["id"] in self.chosen,
                )
                for r in rows
            ]
            children.append(self._select(self.on_sets, set_opts, "Question sets", min_values=1, max_values=len(set_opts)))
        children.append(self._select(self.on_sources, [
            discord.SelectOption(label=label, value=key, emoji=emoji, description=desc, default=key == s.sources)
            for key, (emoji, label, desc) in SOURCES.items()
        ], "Which questions"))
        children.append(self._select(self.on_order, [
            discord.SelectOption(label=label, value=key, emoji=emoji, description=desc, default=key == s.order)
            for key, (emoji, label, desc) in ORDERS.items()
        ], "Order"))
        children.append(self._select(self.on_length, [
            discord.SelectOption(label="Every question" if n == 0 else f"{n} questions", value=str(n), emoji="🔢",
                                 default=n == s.length)
            for n in LENGTHS
        ], "Length"))
        children.append(self._select(self.on_timer, [
            discord.SelectOption(
                label="No timer" if t == 0 else f"{t} seconds per question", value=str(t), emoji="⏱️",
                description=f"Solo only; live games use {LIVE_DEFAULT_TIMER}s" if t == 0 else None, default=t == s.timer,
            )
            for t in TIMERS
        ], "Timer"))
        children.append(discord.ui.Separator())
        children.append(discord.ui.TextDisplay("### 🎛️ Options"))
        for attr, title, desc in TOGGLES:
            children.append(discord.ui.Section(f"**{title}**\n-# {desc}", accessory=self._toggle(attr)))
        children.append(discord.ui.Separator())
        solo = discord.ui.Button(label="Solo (private)", emoji="🧑‍🎓", style=discord.ButtonStyle.primary)
        solo.callback = self.on_solo
        live = discord.ui.Button(label="Live for everyone", emoji="🎮", style=discord.ButtonStyle.success)
        live.callback = self.on_live
        children.append(discord.ui.ActionRow(solo, live))
        self.add_item(discord.ui.Container(*children, accent_colour=PURPLE))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.store.set_prefs(self.owner, self.settings.to_dict())
        self.build()
        await interaction.response.edit_message(view=self)

    async def on_subject(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        self.subject = None if value == "*" else value
        self.chosen = {r["id"] for r in self.visible_sets()}
        await self.refresh(interaction)

    async def on_sets(self, interaction: discord.Interaction) -> None:
        self.chosen = {int(v) for v in interaction.data["values"]}
        await self.refresh(interaction)

    async def on_sources(self, interaction: discord.Interaction) -> None:
        self.settings.sources = interaction.data["values"][0]
        await self.refresh(interaction)

    async def on_order(self, interaction: discord.Interaction) -> None:
        self.settings.order = interaction.data["values"][0]
        await self.refresh(interaction)

    async def on_length(self, interaction: discord.Interaction) -> None:
        self.settings.length = int(interaction.data["values"][0])
        await self.refresh(interaction)

    async def on_timer(self, interaction: discord.Interaction) -> None:
        self.settings.timer = int(interaction.data["values"][0])
        await self.refresh(interaction)

    def draw(self, personal: bool) -> list[int]:
        pool = self.store.question_pool(self.selected_ids(), self.owner if personal else None)
        return [q["id"] for q in choose_questions(pool, self.settings, random.Random(), personal)]

    async def on_solo(self, interaction: discord.Interaction) -> None:
        ids = self.draw(personal=True)
        if not ids:
            await interaction.response.send_message("No questions match those settings yet.", ephemeral=True)
            return
        self.stop()
        await start_solo(interaction, ids, self.settings)

    async def on_live(self, interaction: discord.Interaction) -> None:
        missing = missing_live_permissions(getattr(interaction, "app_permissions", None))
        if missing:
            await interaction.response.send_message(permission_help(missing), ephemeral=True)
            return
        ids = self.draw(personal=False)
        if not ids:
            await interaction.response.send_message("No questions match those settings yet.", ephemeral=True)
            return
        self.stop()
        await start_live(interaction, ids, self.settings)


def set_summary(r) -> str:
    parts = [f"{r['questions']} questions"]
    counts = [("📄", r["from_file"]), ("🤖", r["ai_answer"]), ("✨", r["ai_written"]), ("⭐", r["favourites"])]
    labels = " ".join(f"{e}{n}" for e, n in counts if n)
    return " · ".join(parts + ([labels] if labels else []))


DYNAMIC_ITEMS = (RateButton, FlagButton, SoloAnswer, SoloNext, LiveAnswer, LiveMine, LiveHost)
