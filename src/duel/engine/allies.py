"""DLC Allies: 14 карт союзников (7 на фракцию).

Только данные — эффекты живут в game.py, как и для лэндмарков.
Тексты сверены с официальными памятками игроков (см. planning/allies/spec.md).

У каждой карты два эффекта: enter (цена 1 жетон Силы, раскрывает карту из руки)
и exit (цена 2 жетона, доступен только после enter, карта уходит из игры).
"""

from dataclasses import dataclass

FELLOWSHIP, SAURON = 0, 1


@dataclass(frozen=True)
class Ally:
    id: str
    side: int
    name_ru: str
    name_en: str
    enter_ru: str
    exit_ru: str


ALLIES: list[Ally] = [
    # ---------- Братство ----------
    Ally(
        id="tom_bombadil",
        side=FELLOWSHIP,
        name_ru="Tom Bombadil",
        name_en="Tom Bombadil",
        enter_ru=(
            "Place a used Power token on the Nazgûl. Your opponent must "
            "spend 1 Ring track step to remove this token "
            "before they can move on the track."
        ),
        exit_ru=(
            "Place 2 used Power tokens on the Nazgûl. Your opponent spends "
            "1 step per token before they can move."
        ),
    ),
    Ally(
        id="goldberry",
        side=FELLOWSHIP,
        name_ru="Goldberry",
        name_en="Goldberry",
        enter_ru="Take 3 coins from the supply.",
        exit_ru="Take 5 coins from the supply AND your opponent loses 2 coins, if able.",
    ),
    Ally(
        id="boromir",
        side=FELLOWSHIP,
        name_ru="Boromir",
        name_en="Boromir",
        enter_ru="Remove 1 enemy unit from any region.",
        exit_ru="Remove all enemy units from any one region.",
    ),
    Ally(
        id="arwen",
        side=FELLOWSHIP,
        name_ru="Arwen",
        name_en="Arwen",
        enter_ru=(
            "Take a random card from the discard and play it for free. "
            "Card backs are visible, so you choose the chapter."
        ),
        exit_ru="Look through the discard, choose a card and play it for free.",
    ),
    Ally(
        id="elrond",
        side=FELLOWSHIP,
        name_ru="Elrond",
        name_en="Elrond",
        enter_ru=(
            "Choose a race: Dwarves, Humans, Elves or Hobbits. Take the top "
            "Alliance token of that race. Its effect applies."
        ),
        exit_ru=(
            "Choose a race: Wizards or Ents. Take the top Alliance token "
            "of that race. Its effect applies."
        ),
    ),
    Ally(
        id="faramir",
        side=FELLOWSHIP,
        name_ru="Faramir",
        name_en="Faramir",
        enter_ru="Discard 1 available card from the center.",
        exit_ru=(
            "Discard 1 available card, reveal any cards that become available, then "
            "discard 1 more available card."
        ),
    ),
    Ally(
        id="lobelia",
        side=FELLOWSHIP,
        name_ru="Lobelia Sackville-Baggins",
        name_en="Lobelia Sackville-Baggins",
        enter_ru="Place 1 unit in any region and make 1 move.",
        exit_ru=(
            "Place 2 units in one region or 1 unit in each of two regions. "
            "Also make 2 moves."
        ),
    ),
    # ---------- Саурон ----------
    Ally(
        id="witch_king",
        side=SAURON,
        name_ru="Witch-king",
        name_en="Witch-King",
        enter_ru="Move the Nazgûl 1 space OR place 1 unit in any region.",
        exit_ru="Move the Nazgûl 1 space AND place 1 unit in any region.",
    ),
    Ally(
        id="shelob",
        side=SAURON,
        name_ru="Shelob",
        name_en="Shelob",
        enter_ru=(
            "Place a used Power token on any Alliance token stack. "
            "For the rest of the game your opponent cannot draw from it or look at it."
        ),
        exit_ru="Discard 1 Alliance token from your opponent's area.",
    ),
    Ally(
        id="uruk_hai_chief",
        side=SAURON,
        name_ru="Uruk-hai Chief",
        name_en="Uruk-Hai Chief",
        enter_ru=(
            "Place a used Power token on an available landmark. "
            "Your opponent cannot take it."
        ),
        exit_ru="Take an available landmark and build it for free.",
    ),
    Ally(
        id="balrog",
        side=SAURON,
        name_ru="Balrog",
        name_en="Balrog",
        enter_ru=(
            "Place a used Power token on a link between two regions. "
            "Your opponent can no longer move along it."
        ),
        exit_ru=(
            "Apply the enter effect with one of the used tokens AND remove, "
            "if possible, 1 enemy unit from both regions of that link."
        ),
    ),
    Ally(
        id="warg",
        side=SAURON,
        name_ru="Warg",
        name_en="Warg",
        enter_ru=(
            "Pick a random unrevealed enemy ally. Your opponent reveals it at once "
            "with no token spent and no enter effect (the effect is lost)."
        ),
        exit_ru=(
            "Choose a revealed enemy ally. Use its exit effect "
            "for your benefit without removing the card (your opponent can still use it)."
        ),
    ),
    Ally(
        id="cave_troll",
        side=SAURON,
        name_ru="Cave Troll",
        name_en="Cave-Troll",
        enter_ru="Discard 1 grey card from your opponent's area.",
        exit_ru="Move 1 grey card from your opponent's area to yours.",
    ),
    Ally(
        id="grima",
        side=SAURON,
        name_ru="Gríma",
        name_en="Gríma",
        enter_ru=(
            "Choose an available card. Instead of taking a turn, your opponent must take it "
            "and play it OR discard it for coins equal to the chapter number."
        ),
        exit_ru=(
            "Choose an available card. Instead of taking a turn, your opponent must take it "
            "and discard it for coins equal to the chapter number."
        ),
    ),
]

BY_ID: dict[str, Ally] = {a.id: a for a in ALLIES}
BY_SIDE: dict[int, list[str]] = {
    FELLOWSHIP: [a.id for a in ALLIES if a.side == FELLOWSHIP],
    SAURON: [a.id for a in ALLIES if a.side == SAURON],
}


def ally_to_dict(a: Ally) -> dict:
    return {
        "id": a.id,
        "side": a.side,
        "name": a.name_ru,
        "name_en": a.name_en,
        "enter": a.enter_ru,
        "exit": a.exit_ru,
    }
