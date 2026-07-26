"""The 69 chapter cards, parsed from the owner's spreadsheet (rules/Cards.csv).

Spreadsheet conventions (as explained by the owner):
- "Science" rows are the green Race cards (7WD habit); the race is in the
  "Science Effect" column: Pipe=Hobbits, Hammer=Dwarves, Horn=Humans,
  Flask=Elves, Leaf=Ents, Palantir=Wizards.
- "Resource" rows are the grey Skill cards; "Gives Resource" holds either a
  single skill, "2 Face" (count + skill), or choices like "Crown OR Book"
  (one per turn, player's choice).
- Cost cells hold skill symbols and/or "N Coin".
- Purple "Guild" cards (chapter 3 only): Movements apply to your own units;
  Coins Lost and Casualties hit the opponent.
- "Linden" is a typo for Lindon.
"""

import csv
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_CSV = Path(__file__).parent / "data" / "cards.csv"


class CardType(StrEnum):
    GREY = "grey"  # skills ("Resource")
    YELLOW = "yellow"  # coins ("Gold")
    GREEN = "green"  # races ("Science")
    BLUE = "blue"  # quest of the Ring ("Ring")
    RED = "red"  # units ("War")
    PURPLE = "purple"  # maneuvers, chapter 3 only ("Guild")


TYPE_BY_SHEET_NAME = {
    "Resource": CardType.GREY,
    "Gold": CardType.YELLOW,
    "Science": CardType.GREEN,
    "Ring": CardType.BLUE,
    "War": CardType.RED,
    "Guild": CardType.PURPLE,
}

SKILLS = {"Face", "Fist", "Heart", "Crown", "Book"}
RACE_BY_SYMBOL = {
    "Pipe": "hobbits",
    "Hammer": "dwarves",
    "Horn": "humans",
    "Flask": "elves",
    "Leaf": "ents",
    "Palantir": "wizards",
}
REGION_FIX = {"Linden": "lindon"}


@dataclass(frozen=True)
class Card:
    id: str
    chapter: int
    type: CardType
    cost_skills: tuple[str, ...] = ()
    cost_coins: int = 0
    takes_link: str | None = None
    gives_link: str | None = None
    race: str | None = None  # green
    coins: int = 0  # yellow
    skills: tuple[str, ...] = ()  # grey: fixed symbols gained
    skills_choice: tuple[str, ...] = ()  # grey: one-of symbols
    quest_steps: int = 0  # blue
    troops: int = 0  # red
    destinations: tuple[str, ...] = ()  # red: choose one of two
    movements: int = 0  # purple: own unit moves
    opp_coins_lost: int = 0  # purple: opponent loses coins
    casualties: int = 0  # purple: remove enemy units

    def free(self) -> bool:
        return not self.cost_skills and self.cost_coins == 0


def _parse_cost(cells: list[str]) -> tuple[tuple[str, ...], int]:
    skills: list[str] = []
    coins = 0
    for cell in cells:
        cell = cell.strip()
        if not cell:
            continue
        if cell.endswith("Coin"):
            coins += int(cell.split()[0])
        elif cell in SKILLS:
            skills.append(cell)
        else:
            raise ValueError(f"unknown cost cell {cell!r}")
    return tuple(skills), coins


def _parse_gives_resource(cell: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Returns (fixed skills, choice skills)."""
    cell = cell.strip()
    if not cell:
        return (), ()
    if " OR " in cell:
        options = tuple(p.strip() for p in cell.split(" OR "))
        assert all(o in SKILLS for o in options), cell
        return (), options
    parts = cell.split()
    if len(parts) == 2:  # "2 Face"
        return (parts[1],) * int(parts[0]), ()
    assert cell in SKILLS, cell
    return (cell,), ()


def _load() -> list[Card]:
    cards: list[Card] = []
    counters: dict[int, int] = {1: 0, 2: 0, 3: 0}
    with _CSV.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row.get("Epoch", "").strip():
                continue
            chapter = int(row["Epoch"])
            counters[chapter] += 1
            ctype = TYPE_BY_SHEET_NAME[row["Card Name"].strip()]
            cost_skills, cost_coins = _parse_cost([row[f"Cost {i}"] for i in range(1, 6)])
            skills, skills_choice = _parse_gives_resource(row["Gives Resource"])
            race_sym = row["Science Effect"].strip()
            dests = tuple(
                REGION_FIX.get(d, d).lower()
                for d in (row["Destination 1"].strip(), row["Destination 2"].strip())
                if d
            )
            cards.append(
                Card(
                    id=f"c{chapter}_{counters[chapter]:02d}",
                    chapter=chapter,
                    type=ctype,
                    cost_skills=cost_skills,
                    cost_coins=cost_coins,
                    takes_link=row["Takes Link"].strip() or None,
                    gives_link=row["Gives Link"].strip() or None,
                    race=RACE_BY_SYMBOL[race_sym] if race_sym else None,
                    coins=int(row["Gives Money"] or 0),
                    skills=skills,
                    skills_choice=skills_choice,
                    quest_steps=int(row["Quest Steps"] or 0),
                    troops=int(row["# Troops"] or 0),
                    destinations=dests,
                    movements=int(row["Movements"] or 0),
                    opp_coins_lost=int(row["Coins Lost"] or 0),
                    casualties=int(row["Casualties"] or 0),
                )
            )
    return cards


CARDS: list[Card] = _load()
BY_CHAPTER: dict[int, list[Card]] = {ch: [c for c in CARDS if c.chapter == ch] for ch in (1, 2, 3)}


def card_to_dict(c: Card) -> dict:
    return {
        "id": c.id,
        "chapter": c.chapter,
        "type": str(c.type),
        "cost_skills": list(c.cost_skills),
        "cost_coins": c.cost_coins,
        "takes_link": c.takes_link,
        "gives_link": c.gives_link,
        "race": c.race,
        "coins": c.coins,
        "skills": list(c.skills),
        "skills_choice": list(c.skills_choice),
        "quest_steps": c.quest_steps,
        "troops": c.troops,
        "destinations": list(c.destinations),
        "movements": c.movements,
        "opp_coins_lost": c.opp_coins_lost,
        "casualties": c.casualties,
    }
