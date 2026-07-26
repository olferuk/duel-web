"""Chapter tableau layouts (card pyramid structures).

Coordinate system: `row` counts from 0 at the top of the printed diagram.
`x` is measured in half-card widths (a card is 2 units wide), so two cards
touching side by side differ by 2, and a card overlapping the row above is
offset by 1 from each card it covers.

Physical stacking: cards of row r+1 are placed ON TOP of cards of row r.
A card in row r+1 at position x covers the cards of row r at x-1 and x+1
(when such slots exist). A card may be taken only when no untaken card
covers it. Even rows are dealt faceup, odd rows facedown (per the rulebook
diagrams on page 3).

Each chapter deck has 23 cards: 20 are dealt into the tableau and 3 go
facedown to the discard.
"""

from dataclasses import dataclass, field

CARDS_PER_CHAPTER = 23
CARDS_IN_TABLEAU = 20
CARDS_TO_DISCARD = 3


def _pyramid(rows: list[int]) -> list[list[int]]:
    """x-positions for centered rows of the given sizes."""
    return [list(range(-(n - 1), n, 2)) for n in rows]


# Chapter 1: pyramid growing downward, 2/3/4/5/6.
# Chapter 2: inverted pyramid, 6/5/4/3/2.
# Chapter 3: the Ring — 2/3/4/2/4/3/2 with a hole in the middle row.
CHAPTER_ROWS: dict[int, list[list[int]]] = {
    1: _pyramid([2, 3, 4, 5, 6]),
    2: _pyramid([6, 5, 4, 3, 2]),
    3: [*_pyramid([2, 3, 4]), [-2, 2], *_pyramid([4, 3, 2])],
}


@dataclass
class Slot:
    """One position in the chapter tableau."""

    id: int
    row: int
    x: int
    faceup: bool
    covered_by: list[int] = field(default_factory=list)  # slot ids physically on top
    covers: list[int] = field(default_factory=list)  # slot ids underneath


def build_slots(chapter: int) -> list[Slot]:
    rows = CHAPTER_ROWS[chapter]
    slots: list[Slot] = []
    by_pos: dict[tuple[int, int], Slot] = {}
    for r, xs in enumerate(rows):
        for x in xs:
            slot = Slot(id=len(slots), row=r, x=x, faceup=r % 2 == 0)
            slots.append(slot)
            by_pos[r, x] = slot
    for slot in slots:
        for dx in (-1, 1):
            below = by_pos.get((slot.row + 1, slot.x + dx))
            if below is not None:
                slot.covered_by.append(below.id)
                below.covers.append(slot.id)
    return slots
