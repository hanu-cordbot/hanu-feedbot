"""/library: browse subjects and their question sets, and organise them.

A subject holds any number of question sets. From here you can add files to a subject
(➕ opens a form with a file upload, so no slash-command options to remember), start a
new subject, and move or rename a set. Everything goes through the same pipeline as
/upload (StudyCog.ingest_file).
"""
from collections import OrderedDict
from typing import TYPE_CHECKING, Optional

import discord

from . import export, quality
from .play import PURPLE, set_summary
from .render import clip

if TYPE_CHECKING:
    from .bot import StudyCog

MAX_SUBJECTS = 9  # sections shown in full; Discord allows 40 components per message
MAX_FILES = 10
NEW_PER_FILE, NEW_NAMED = "*file", "*named"


def grouped(rows) -> "OrderedDict[str, list]":
    by_subject: OrderedDict[str, list] = OrderedDict()
    for r in rows:
        by_subject.setdefault(r["subject"], []).append(r)
    return by_subject


def subject_title(subject: str) -> str:
    return f"{quality.subject_emoji(subject)} {subject.title()}"


class LibraryPanel(discord.ui.LayoutView):
    def __init__(self, cog: "StudyCog", guild_id: int, owner: int):
        super().__init__(timeout=900)
        self.cog, self.store, self.guild_id, self.owner = cog, cog.store, guild_id, owner
        self.build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner

    def build(self) -> None:
        self.clear_items()
        rows = list(self.store.library(self.guild_id))
        subjects = grouped(rows)
        total = sum(r["questions"] for r in rows)
        children: list[discord.ui.Item] = [discord.ui.TextDisplay(
            f"## 📚 Library\n**{len(subjects)}** subjects · **{len(rows)}** question sets · **{total}** questions\n"
            f"-# {quality.LEGEND}"
        )]
        if not rows:
            children.append(discord.ui.TextDisplay("Nothing here yet. Press **🗂️ New subject** and add your first files."))
        for subject, sets in list(subjects.items())[:MAX_SUBJECTS]:
            lines = [f"- **{r['name']}** · {set_summary(r)}" for r in sets[:12]]
            if len(sets) > 12:
                lines.append(f"- …and {len(sets) - 12} more")
            add = discord.ui.Button(label="Add files", emoji="➕", style=discord.ButtonStyle.secondary)
            add.callback = self._add_files(subject)
            children.append(discord.ui.Section(clip(f"### {subject_title(subject)}\n" + "\n".join(lines), 1500), accessory=add))
        extra = list(subjects)[MAX_SUBJECTS:]
        if extra:
            children.append(discord.ui.TextDisplay(
                "-# Also: " + ", ".join(subject_title(s) for s in extra) + ". Use a set's menu below, or `/upload subject:`."
            ))
        children.append(discord.ui.Separator())
        if rows:
            options = [
                discord.SelectOption(label=r["name"][:100], value=str(r["id"]), emoji=quality.subject_emoji(r["subject"]),
                                     description=clip(f"{r['subject'].title()} · {set_summary(r)}", 100))
                for r in rows[:25]
            ]
            pick = discord.ui.Select(placeholder="✏️ Move, rename or add files to a set…", options=options)
            pick.callback = self._open_set
            children.append(discord.ui.ActionRow(pick))
        new = discord.ui.Button(label="New subject", emoji="🗂️", style=discord.ButtonStyle.primary)
        new.callback = self._new_subject
        children.append(discord.ui.ActionRow(new))
        self.add_item(discord.ui.Container(*children, accent_colour=PURPLE))

    def _add_files(self, subject: str):
        async def callback(interaction: discord.Interaction) -> None:
            await interaction.response.send_modal(AddFilesModal(self.cog, self.guild_id, subject))
        return callback

    async def _new_subject(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddFilesModal(self.cog, self.guild_id, None))

    async def _open_set(self, interaction: discord.Interaction) -> None:
        deck_id = int(interaction.data["values"][0])
        await interaction.response.edit_message(view=SetPanel(self.cog, self.guild_id, self.owner, deck_id))


class SetPanel(discord.ui.LayoutView):
    """One question set: move it to another subject, rename it, or add files to it."""

    def __init__(self, cog: "StudyCog", guild_id: int, owner: int, deck_id: int):
        super().__init__(timeout=900)
        self.cog, self.store, self.guild_id, self.owner, self.deck_id = cog, cog.store, guild_id, owner, deck_id
        self.build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner

    def build(self) -> None:
        self.clear_items()
        row = next((r for r in self.store.library(self.guild_id) if r["id"] == self.deck_id), None)
        if row is None:
            self.add_item(discord.ui.Container(discord.ui.TextDisplay("That set no longer exists."), accent_colour=PURPLE))
            return
        self.name, self.subject = row["name"], row["subject"]
        subjects = [s for s in self.store.subjects(self.guild_id) if s != self.subject][:23]
        move_opts = [discord.SelectOption(label=s.title()[:100], value=s[:100], emoji=quality.subject_emoji(s)) for s in subjects]
        move_opts.append(discord.SelectOption(label="New subject…", value="*new", emoji="➕"))
        move = discord.ui.Select(placeholder=f"🗂️ Move to another subject (now: {self.subject.title()})"[:150], options=move_opts)
        move.callback = self._move
        rename = discord.ui.Button(label="Rename", emoji="✏️", style=discord.ButtonStyle.secondary)
        rename.callback = self._rename
        add = discord.ui.Button(label="Add files", emoji="➕", style=discord.ButtonStyle.primary)
        add.callback = self._add
        back = discord.ui.Button(label="Back to library", emoji="⬅️", style=discord.ButtonStyle.secondary)
        back.callback = self._back
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(f"## {quality.subject_emoji(self.subject)} {self.name}\n"
                                   f"In **{self.subject.title()}** · {set_summary(row)}"),
            discord.ui.ActionRow(move),
            discord.ui.ActionRow(add, rename, back),
            accent_colour=PURPLE,
        ))

    async def _move(self, interaction: discord.Interaction) -> None:
        value = interaction.data["values"][0]
        if value == "*new":
            await interaction.response.send_modal(TextModal(
                "New subject", "Subject name", "e.g. tư tưởng hồ chí minh", "", self._apply_subject))
            return
        await self._apply_subject(interaction, value)

    async def _apply_subject(self, interaction: discord.Interaction, subject: str) -> None:
        self.store.set_deck_subject(self.deck_id, subject)
        self.build()
        await interaction.response.edit_message(view=self)

    async def _rename(self, interaction: discord.Interaction) -> None:
        async def apply(inter: discord.Interaction, name: str) -> None:
            if not self.store.rename_deck(self.deck_id, name):
                await inter.response.send_message(f"There's already a set called **{name}**.", ephemeral=True)
                return
            self.build()
            await inter.response.edit_message(view=self)

        await interaction.response.send_modal(TextModal("Rename set", "New name", "", self.name, apply))

    async def _add(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(AddFilesModal(self.cog, self.guild_id, self.subject, preset=self.name))

    async def _back(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=LibraryPanel(self.cog, self.guild_id, self.owner))


class TextModal(discord.ui.Modal):
    def __init__(self, title: str, label: str, placeholder: str, default: str, on_value):
        super().__init__(title=title)
        self.on_value = on_value
        self.field = discord.ui.TextInput(label=label, placeholder=placeholder or None, default=default or None,
                                          max_length=80)
        self.add_item(self.field)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        value = self.field.value.strip()
        if not value:
            await interaction.response.send_message("That can't be empty.", ephemeral=True)
            return
        await self.on_value(interaction, value)


class AddFilesModal(discord.ui.Modal):
    """Drop files into a subject: each goes into an existing set, one new set, or a set per file."""

    def __init__(self, cog: "StudyCog", guild_id: int, subject: Optional[str], preset: Optional[str] = None):
        super().__init__(title=clip(f"Add files to {subject.title()}" if subject else "New subject", 45))
        self.cog, self.guild_id, self.subject = cog, guild_id, subject
        self.subject_input: Optional[discord.ui.TextInput] = None
        if subject is None:
            self.subject_input = discord.ui.TextInput(placeholder="e.g. tư tưởng hồ chí minh", max_length=60)
            self.add_item(discord.ui.Label(text="Subject name", component=self.subject_input))
        self.files = discord.ui.FileUpload(min_values=1, max_values=MAX_FILES)
        self.add_item(discord.ui.Label(
            text="Files", description="Up to 10 · PDF, Word, PowerPoint, text, JSON, photos", component=self.files,
        ))
        sets = [r for r in cog.store.library(guild_id) if subject and r["subject"] == subject][:23]
        options = [
            discord.SelectOption(label="A new set for each file", value=NEW_PER_FILE, emoji="🆕",
                                 description="Named after the file", default=preset is None),
            discord.SelectOption(label="One new set, named below", value=NEW_NAMED, emoji="🏷️"),
        ] + [
            discord.SelectOption(label=r["name"][:100], value=r["name"][:100], emoji="📚",
                                 description=clip(set_summary(r), 100), default=r["name"] == preset)
            for r in sets
        ]
        self.target = discord.ui.Select(options=options)
        self.add_item(discord.ui.Label(text="Put them in", component=self.target))
        self.set_name = discord.ui.TextInput(placeholder="e.g. week 1-13 review", required=False, max_length=80)
        self.add_item(discord.ui.Label(text="New set name", description="Only for “one new set”", component=self.set_name))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        subject = self.subject or (self.subject_input.value.strip().lower() if self.subject_input else "") or "general"
        target = self.target.values[0] if self.target.values else NEW_PER_FILE
        attachments = list(self.files.values)
        if target == NEW_NAMED:
            deck: Optional[str] = self.set_name.value.strip() or export.slugify(attachments[0].filename.rsplit(".", 1)[0])
        elif target == NEW_PER_FILE:
            deck = None
        else:
            deck = target
        await interaction.response.defer(thinking=True)
        for att in attachments:
            text, view = await self.cog.ingest_file(
                self.guild_id, interaction.user.id, att.filename, await att.read(), deck, subject
            )
            await interaction.followup.send(text, **({"view": view} if view else {}))


async def open_library(cog: "StudyCog", interaction: discord.Interaction) -> None:
    await interaction.response.send_message(view=LibraryPanel(cog, interaction.guild_id, interaction.user.id), ephemeral=True)

