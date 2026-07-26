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
    AllianceToken(
        "elves_extra_turn", "elves", "passive", "Сыграв жёлтую карту — сделай ещё один ход"
    ),
    AllianceToken(
        "elves_red_any", "elves", "passive", "Красные карты: юниты в ЛЮБОЙ из 7 регионов"
    ),
    AllianceToken("elves_wild_skill", "elves", "passive", "Раз в ход — любой один навык"),
    # Dwarves
    AllianceToken("dwarves_free_tile", "dwarves", "passive", "Тайлы: без доплаты за свои крепости"),
    AllianceToken("dwarves_tile_turn", "dwarves", "passive", "Купив тайл — сделай ещё один ход"),
    AllianceToken(
        "dwarves_green_moves", "dwarves", "passive", "Сыграв зелёную карту — 2 перемещения"
    ),
    # Hobbits
    AllianceToken("hobbits_eagle", "hobbits", "passive", "Орёл: считается 1 из 6 рас для победы"),
    AllianceToken(
        "hobbits_blue_unit", "hobbits", "passive", "Сыграв синюю карту — юнит в любой регион"
    ),
    AllianceToken(
        "hobbits_chain_coins", "hobbits", "passive", "Сыграв карту по цепочке — возьми 3 монеты"
    ),
    # Humans
    AllianceToken(
        "humans_yellow_quest", "humans", "passive", "Сыграв жёлтую карту — +1 шаг Кольца"
    ),
    AllianceToken(
        "humans_red_extra", "humans", "passive", "Красные карты: +1 юнит в выбранный регион"
    ),
    AllianceToken("humans_double_discard", "humans", "passive", "Сброс карты: монеты ×2 (2/4/6)"),
    # Ents (instant)
    AllianceToken("ents_extra_turn", "ents", "instant", "Сделай ещё один ход"),
    AllianceToken(
        "ents_remove_fort", "ents", "instant", "Убери вражескую крепость (вернётся владельцу)"
    ),
    AllianceToken(
        "ents_menu3", "ents", "instant", "3 раза: убрать юнита / враг −1 монета / перемещение"
    ),
    # Wizards (instant)
    AllianceToken("wizards_quest2", "wizards", "instant", "Пройди 2 шага по Пути Кольца"),
    AllianceToken(
        "wizards_units2", "wizards", "instant", "2 юнита: в один регион или в два разных"
    ),
    AllianceToken("wizards_discard_play", "wizards", "instant", "Сыграй карту из сброса бесплатно"),
]

BY_ID: dict[str, AllianceToken] = {t.id: t for t in TOKENS}
BY_RACE: dict[str, list[AllianceToken]] = {}
for _t in TOKENS:
    BY_RACE.setdefault(_t.race, []).append(_t)
