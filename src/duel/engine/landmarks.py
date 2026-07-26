"""Landmark tiles: 7 base + 2 promo (The Shire, Grond).

Costs read from the owner's photo of the tiles (rules/IMG_5058.HEIC);
effects from the Player Aid. Every tile also has a surcharge: +1 Coin per
fortress you already have on the board (Dwarves token 1 ignores it).

The Shire uniquely places NO fortress. Promo tiles are shuffled into the
draw stack after the initial 3 tiles are revealed.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Landmark:
    id: str
    name_ru: str
    region: str | None  # fortress placed here (None for The Shire)
    cost: tuple[str, ...]  # skill symbols
    units: int = 0  # units placed in `region` along with the fortress
    coins: int = 0  # coins taken from reserve
    movements: int = 0  # board movements to complete
    quest_steps: int = 0  # advance own character
    effect: str | None = None  # unique scripted effect key
    promo: bool = False


LANDMARKS: list[Landmark] = [
    Landmark(
        id="barad_dur",
        name_ru="Барад-Дур",
        region="mordor",
        cost=("Heart", "Heart", "Heart", "Crown", "Crown", "Book"),
        effect="play_from_discard",
    ),
    Landmark(
        id="bree",
        name_ru="Бри",
        region="arnor",
        cost=("Fist", "Fist", "Fist", "Heart", "Heart", "Crown"),
        units=2,
        movements=2,
    ),
    Landmark(
        id="erebor",
        name_ru="Эребор",
        region="rhovanion",
        cost=("Face", "Fist", "Fist", "Heart", "Crown", "Book"),
        coins=5,
        movements=1,
    ),
    Landmark(
        id="grey_havens",
        name_ru="Серые Гавани",
        region="lindon",
        cost=("Fist", "Fist", "Fist", "Crown", "Crown", "Book"),
        effect="grey_havens_tokens",
    ),
    Landmark(
        id="helms_deep",
        name_ru="Хельмова Падь",
        region="rohan",
        cost=("Face", "Face", "Face", "Crown", "Crown", "Book"),
        units=3,
    ),
    Landmark(
        id="isengard",
        name_ru="Изенгард",
        region="enedwaith",
        cost=("Face", "Face", "Heart", "Heart", "Heart", "Book"),
        quest_steps=1,
        effect="discard_opp_grey",
    ),
    Landmark(
        id="minas_tirith",
        name_ru="Минас Тирит",
        region="gondor",
        cost=("Face", "Face", "Face", "Fist", "Book", "Book"),
        units=1,
        quest_steps=2,
    ),
    Landmark(
        id="shire",
        name_ru="Шир",
        region=None,
        cost=("Face", "Fist", "Heart", "Heart", "Book", "Book"),
        effect="shire_play_visible",
        promo=True,
    ),
    Landmark(
        id="grond",
        name_ru="Гронд",
        region=None,  # region chosen dynamically (where the enemy fortress was)
        cost=("Face", "Face", "Fist", "Fist", "Heart", "Crown"),
        effect="grond_assault",
        promo=True,
    ),
]

BY_ID: dict[str, Landmark] = {lm.id: lm for lm in LANDMARKS}


def landmark_to_dict(lm: Landmark) -> dict:
    return {
        "id": lm.id,
        "name": lm.name_ru,
        "region": lm.region,
        "cost": list(lm.cost),
        "units": lm.units,
        "coins": lm.coins,
        "movements": lm.movements,
        "quest_steps": lm.quest_steps,
        "effect": lm.effect,
        "promo": lm.promo,
    }
