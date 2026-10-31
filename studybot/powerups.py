"""Quizizz-style power-ups for live games: what each one does, who gets one, and how they change a score.

Players earn a random power-up on their first answer of the game and for every EARN_EVERY right answers in a
row, and hold up to MAX_HELD. They use them privately from the ⚡ button on the game message. Quizizz doesn't
publish exact numbers, so the values here follow how its power-ups are commonly described.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

# key: (emoji, name, what it does)
CATALOGUE: dict[str, tuple[str, str, str]] = {
    "fifty": ("🌗", "50-50", "Removes two wrong answers, just for you"),
    "eraser": ("🧽", "Eraser", "Removes one wrong answer, just for you"),
    "immunity": ("🛡️", "Immunity", "A second try if your first pick is wrong"),
    "freeze": ("⏸️", "Time Freeze", "Stops your clock: you score as if you answered right now"),
    "double": ("✌️", "2x", "Double points on this question"),
    "jeopardy": ("🎲", "Double Jeopardy", "Right: double points. Wrong: lose what you'd have won"),
    "streak_saver": ("🔒", "Streak Saver", "A wrong answer here won't break your streak"),
    "streak_boost": ("📈", "Streak Booster", "+2 on your streak right now"),
    "power_play": ("⚡", "Power Play", "+50% points for everyone on this question"),
    "supersonic": ("🚀", "Supersonic", "+50% on your next 3 right answers"),
    "gift": ("🎁", "Gift", "800 points for a random other player"),
}
# These only make sense before you've locked in an answer on the current question.
BEFORE_ANSWER = {"fifty", "eraser", "immunity", "freeze", "double", "jeopardy", "streak_saver"}
MAX_HELD = 3
EARN_EVERY = 3
GIFT_POINTS = 800
SUPERSONIC_ANSWERS = 3
STREAK_BOOST = 2


def label(key: str) -> str:
    emoji, name, _ = CATALOGUE[key]
    return f"{emoji} {name}"


@dataclass
class Powers:
    """One player's power-ups in one game."""
    held: list[str] = field(default_factory=list)
    active: set[str] = field(default_factory=set)   # used on the current question
    removed: set[int] = field(default_factory=set)  # displayed answer tiles erased for this player
    frozen_left: Optional[float] = None
    supersonic: int = 0
    started: bool = False                           # got the starter power-up

    def new_question(self) -> None:
        self.active.clear()
        self.removed.clear()
        self.frozen_left = None


def award(p: Powers, rng: random.Random) -> Optional[str]:
    if len(p.held) >= MAX_HELD:
        return None
    key = rng.choice(list(CATALOGUE))
    p.held.append(key)
    return key


def earned_after_answer(p: Powers, correct: bool, streak: int, rng: random.Random) -> Optional[str]:
    """The starter power-up on a player's first answer, then one per EARN_EVERY right in a row."""
    if not p.started:
        p.started = True
        return award(p, rng)
    if correct and streak and streak % EARN_EVERY == 0:
        return award(p, rng)
    return None


def erase(p: Powers, n_options: int, correct: int, count: int, rng: random.Random) -> list[int]:
    """Removes up to `count` wrong tiles but always leaves at least one wrong answer standing."""
    wrong = [i for i in range(n_options) if i != correct and i not in p.removed]
    take = min(count, len(wrong) - 1)
    if take <= 0:
        return []
    gone = rng.sample(wrong, take)
    p.removed.update(gone)
    return sorted(gone)


def effective_left(p: Powers, seconds_left: float) -> float:
    return max(seconds_left, p.frozen_left) if p.frozen_left is not None else seconds_left


def adjust(points: int, correct: bool, p: Powers, power_play: bool, right_value: int) -> tuple[int, list[str]]:
    """Applies active power-ups to a scored answer. `right_value` is what a right answer would have earned
    (Double Jeopardy takes that away on a wrong one). Returns (points, short notes for the player)."""
    notes: list[str] = []
    if not correct:
        if "jeopardy" in p.active:
            notes.append("🎲 Double Jeopardy")
            return -right_value, notes
        return 0, notes
    mult = 1.0
    if "double" in p.active:
        mult *= 2
        notes.append("✌️ 2x")
    if "jeopardy" in p.active:
        mult *= 2
        notes.append("🎲 2x")
    if power_play:
        mult *= 1.5
        notes.append("⚡ +50%")
    if p.supersonic > 0:
        p.supersonic -= 1
        mult *= 1.5
        notes.append("🚀 +50%")
    if "freeze" in p.active:
        notes.append("⏸️ frozen clock")
    return round(points * mult), notes


def refuse_reason(key: str, p: Powers, answered: bool, power_play_on: bool, n_wrong_left: int,
                  others: int) -> Optional[str]:
    """Why this power-up can't be used right now, or None if it can."""
    if key not in p.held:
        return "You don't have that one."
    if key in p.active:
        return "That's already on for this question."
    if key in BEFORE_ANSWER and answered:
        return "Use that one before you pick an answer."
    if key in ("double", "jeopardy") and ({"double", "jeopardy"} & p.active):
        return "2x and Double Jeopardy don't stack."
    if key == "fifty" and n_wrong_left < 2:
        return "Not enough wrong answers left to remove two."
    if key == "eraser" and n_wrong_left < 2:
        return "Only one wrong answer is left."
    if key == "power_play" and power_play_on:
        return "Someone already used Power Play on this question."
    if key == "gift" and others == 0:
        return "Nobody else is playing yet. Keep it for later."
    return None
