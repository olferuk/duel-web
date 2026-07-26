"""Tableau state: dealing a chapter and taking cards.

Deals the real 23-card chapter deck (see cards.py): 3 random cards go
facedown to the discard, 20 fill the layout slots.
"""

import random

from duel.engine.cards import BY_CHAPTER, Card, card_to_dict
from duel.engine.layout import (
    CARDS_TO_DISCARD,
    Slot,
    build_slots,
)


class Tableau:
    def __init__(self, chapter: int, seed: int | None = None) -> None:
        self.chapter = chapter
        self.slots: list[Slot] = build_slots(chapter)
        rng = random.Random(seed)
        deck: list[Card] = list(BY_CHAPTER[chapter])
        rng.shuffle(deck)
        self.discarded: list[Card] = deck[:CARDS_TO_DISCARD]
        self.cards: dict[int, Card] = dict(
            zip((s.id for s in self.slots), deck[CARDS_TO_DISCARD:], strict=True)
        )
        self.taken: set[int] = set()
        self.revealed: set[int] = {s.id for s in self.slots if s.faceup}

    def is_available(self, slot_id: int) -> bool:
        """A card may be taken when present and not covered by any present card."""
        slot = self.slots[slot_id]
        if slot_id in self.taken:
            return False
        return all(c in self.taken for c in slot.covered_by)

    def available(self) -> list[int]:
        return [s.id for s in self.slots if self.is_available(s.id)]

    def take(self, slot_id: int) -> Card:
        if not self.is_available(slot_id):
            raise ValueError(f"slot {slot_id} is not available")
        self.taken.add(slot_id)
        # Rulebook: end your turn by revealing any cards that are now available.
        for sid in self.available():
            self.revealed.add(sid)
        return self.cards[slot_id]

    def take_any(self, slot_id: int) -> Card:
        """Take a revealed card even if covered (The Shire promo tile)."""
        if slot_id in self.taken or slot_id not in self.revealed:
            raise ValueError(f"slot {slot_id} is not visible")
        self.taken.add(slot_id)
        for sid in self.available():
            self.revealed.add(sid)
        return self.cards[slot_id]

    @property
    def empty(self) -> bool:
        return len(self.taken) == len(self.slots)

    def clone(self) -> "Tableau":
        """Fast copy for search: static structures shared, mutable sets copied."""
        t = object.__new__(Tableau)
        t.chapter = self.chapter
        t.slots = self.slots  # built once, never mutated
        t.discarded = self.discarded
        t.cards = self.cards
        t.taken = set(self.taken)
        t.revealed = set(self.revealed)
        return t

    def to_dict(self) -> dict:
        available = set(self.available())
        return {
            "chapter": self.chapter,
            "remaining": len(self.slots) - len(self.taken),
            "discarded": len(self.discarded),
            "slots": [
                {
                    "id": s.id,
                    "row": s.row,
                    "x": s.x,
                    "faceup": s.faceup,
                    "taken": s.id in self.taken,
                    "available": s.id in available,
                    "revealed": s.id in self.revealed,
                    "card": (
                        card_to_dict(self.cards[s.id])
                        if s.id in self.revealed and s.id not in self.taken
                        else None
                    ),
                }
                for s in self.slots
            ],
        }
