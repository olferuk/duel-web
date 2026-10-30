"""Alliance tokens: 3 per race, 18 total (from the Player Aid).

`kind`:
- "passive"  — stays in front of the player, modifies future actions;
- "instant"  — one-time effect resolved immediately when gained (Ents,
  Wizards; marked * on the Player Aid).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AllianceToken:
    id: str
    race: str
    kind: str  # "passive" | "instant"
    text_ru: str


TOKENS: list[AllianceToken] = [
    # Elves
    AllianceToken("elves_extra_turn", "elves", "passive", "Play a yellow card: take another turn"),
    AllianceToken(
        "elves_red_any", "elves", "passive", "Red cards: units go to ANY of the 7 regions"
    ),
    AllianceToken("elves_wild_skill", "elves", "passive", "Once per turn: any one skill"),
    # Dwarves
    AllianceToken("dwarves_free_tile", "dwarves", "passive", "Tiles: no extra cost for fortresses"),
    AllianceToken("dwarves_tile_turn", "dwarves", "passive", "Buy a tile: take another turn"),
    AllianceToken("dwarves_green_moves", "dwarves", "passive", "Play a green card: 2 moves"),
    # Hobbits
    AllianceToken("hobbits_eagle", "hobbits", "passive", "Eagle: counts as 1 of the 6 races"),
    AllianceToken(
        "hobbits_blue_unit", "hobbits", "passive", "Play a blue card: a unit in any region"
    ),
    AllianceToken(
        "hobbits_chain_coins", "hobbits", "passive", "Play a card via chain: take 3 coins"
    ),
    # Humans
    AllianceToken("humans_yellow_quest", "humans", "passive", "Play a yellow card: +1 Ring step"),
    AllianceToken(
        "humans_red_extra", "humans", "passive", "Red cards: +1 unit in the chosen region"
    ),
    AllianceToken("humans_double_discard", "humans", "passive", "Discard a card: coins ×2 (2/4/6)"),
    # Ents (instant)
    AllianceToken("ents_extra_turn", "ents", "instant", "Take another turn"),
    AllianceToken(
        "ents_remove_fort", "ents", "instant", "Remove an enemy fortress (it returns to its owner)"
    ),
    AllianceToken("ents_menu3", "ents", "instant", "3 times: remove a unit / enemy −1 coin / move"),
    # Wizards (instant)
    AllianceToken("wizards_quest2", "wizards", "instant", "Advance 2 steps on the Ring Path"),
    AllianceToken(
        "wizards_units2", "wizards", "instant", "2 units: in one region or two different ones"
    ),
    AllianceToken("wizards_discard_play", "wizards", "instant", "Play a discarded card for free"),
]

BY_ID: dict[str, AllianceToken] = {t.id: t for t in TOKENS}
BY_RACE: dict[str, list[AllianceToken]] = {}
for _t in TOKENS:
    BY_RACE.setdefault(_t.race, []).append(_t)
