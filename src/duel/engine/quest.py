"""Quest of the Ring track.

Two identical 14-step halves (verified against the rulebook photo, p6):

    start . . coin . . unit . . extra_turn . . destroy_fortress . [half end]

Physically the Nazgûl's strip is dragged along by Frodo's strip: when Frodo
& Sam move, the whole Nazgûl half-track slides with them, so the gap between
the characters NEVER grows. Only the Nazgûl's own movement closes it.
Being dragged does not traverse spaces, so it triggers no bonuses.

Model:
- ``frodo``: global position on the fixed half, 14 (the One Ring) .. 28
  (Mount Doom).
- ``nazgul_progress``: steps the Nazgûl has made on his own strip, 0..14.
  The gap to Frodo is ``14 - nazgul_progress``; his global position is
  ``frodo - gap``.

Bonuses trigger when a character reaches OR passes a bonus space of his own
strip. Victory: Frodo reaches Mount Doom -> Fellowship; the Nazgûl closes
the gap to 0 (catches Frodo) -> Sauron.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Space(StrEnum):
    EMPTY = "empty"
    COIN = "coin"  # take 1 Coin from the reserve
    UNIT = "unit"  # place 1 of your Units in any region
    EXTRA_TURN = "extra_turn"  # take another turn
    DESTROY_FORTRESS = "destroy_fortress"  # remove 1 enemy Fortress
    RING = "ring"  # Frodo & Sam's starting space (end of the Nazgûl's half)
    DOOM = "doom"  # Mount Doom


HALF: list[Space] = [
    Space.EMPTY,  # start of the half
    Space.EMPTY,
    Space.EMPTY,
    Space.COIN,
    Space.EMPTY,
    Space.EMPTY,
    Space.UNIT,
    Space.EMPTY,
    Space.EMPTY,
    Space.EXTRA_TURN,
    Space.EMPTY,
    Space.EMPTY,
    Space.DESTROY_FORTRESS,
    Space.EMPTY,
]

HALF_STEPS = 14  # steps from the start of a half to its final space

# The Nazgûl's strip: his 14 steps end on the space where Frodo currently is.
NAZGUL_STRIP: list[Space] = [*HALF, Space.RING]
# Frodo's fixed half: the One Ring .. Mount Doom (global positions 14..28).
FRODO_STRIP: list[Space] = [Space.RING, *HALF[1:], Space.DOOM]

FRODO_START = 14
DOOM = FRODO_START + HALF_STEPS  # 28

BONUS_SPACES = {Space.COIN, Space.UNIT, Space.EXTRA_TURN, Space.DESTROY_FORTRESS}


@dataclass
class QuestState:
    frodo: int = FRODO_START  # global position, 14..28
    nazgul_progress: int = 0  # own steps made, 0..14
    winner: str | None = None  # "fellowship" | "sauron"
    log: list[str] = field(default_factory=list)

    @property
    def gap(self) -> int:
        return HALF_STEPS - self.nazgul_progress

    @property
    def nazgul_global(self) -> int:
        return self.frodo - self.gap

    def advance(self, who: str, steps: int) -> list[Space]:
        """Move a character forward, collecting reach-or-pass bonuses.

        Frodo stops at Mount Doom (extra steps are wasted) and drags the
        Nazgûl's strip along. The Nazgûl stops when he catches Frodo.
        Returns the bonuses triggered.
        """
        if self.winner is not None:
            raise ValueError("game already over")

        if who == "frodo":
            pos = self.frodo - FRODO_START
            target = min(pos + steps, HALF_STEPS)
            strip = FRODO_STRIP
        elif who == "nazgul":
            pos = self.nazgul_progress
            target = min(pos + steps, HALF_STEPS)
            strip = NAZGUL_STRIP
        else:
            raise ValueError(f"unknown character {who!r}")

        bonuses = [strip[p] for p in range(pos + 1, target + 1) if strip[p] in BONUS_SPACES]

        if who == "frodo":
            self.frodo = FRODO_START + target
            if self.frodo == DOOM:
                self.winner = "fellowship"
        else:
            self.nazgul_progress = target
            if self.gap == 0:
                self.winner = "sauron"
        return bonuses

    def to_dict(self) -> dict:
        return {
            "frodo_strip": [str(s) for s in FRODO_STRIP],
            "nazgul_strip": [str(s) for s in NAZGUL_STRIP],
            "frodo": self.frodo,
            "nazgul_progress": self.nazgul_progress,
            "nazgul_global": self.nazgul_global,
            "gap": self.gap,
            "strip_offset": self.frodo - FRODO_START,
            "winner": self.winner,
            "log": self.log,
        }
