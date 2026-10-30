"""Static board data: the 7 regions of Middle-earth.

`pos` are map coordinates in a 100x52 box (landscape, roughly the real
board's aspect ratio), eyeballed from the rulebook photos — used only for
drawing the UI.

Adjacency verified with the owner (board in hand): lindon-enedwaith absent,
enedwaith-rhovanion PRESENT (fixed 2026-07-28 — bots before this date trained
on the wrong graph), rhovanion-mordor ABSENT (fixed 2026-08-29 — bots before
this date trained with a phantom road into Mordor).
"""

# Neat 3-2-2 grid (rows y=9/26/43): reads like a diagram since we don't
# draw the real map art anyway.
REGIONS: list[dict] = [
    {"key": "lindon", "name": "Lindon", "pos": (16, 9)},
    {"key": "arnor", "name": "Arnor", "pos": (50, 9)},
    {"key": "rhovanion", "name": "Rhovanion", "pos": (84, 9)},
    {"key": "enedwaith", "name": "Enedwaith", "pos": (33, 26)},
    {"key": "rohan", "name": "Rohan", "pos": (67, 26)},
    {"key": "gondor", "name": "Gondor", "pos": (42, 43)},
    {"key": "mordor", "name": "Mordor", "pos": (76, 43)},
]

EDGES: list[tuple[str, str]] = [
    ("lindon", "arnor"),
    ("arnor", "enedwaith"),
    ("arnor", "rhovanion"),
    ("rhovanion", "rohan"),
    # rhovanion-mordor УБРАНО 2026-08-29 (владелец + арт поля: дороги нет; в Мордор
    # только через Рохан и Гондор). Индекс ребра в пространстве действий сохранён
    # (см. ai/actions.py EDGES_DIR) — старые политики совместимы.
    ("enedwaith", "rohan"),
    ("enedwaith", "rhovanion"),  # правка владельца 2026-07-28: соединены!
    ("enedwaith", "gondor"),
    ("rohan", "gondor"),
    ("rohan", "mordor"),
    ("gondor", "mordor"),
]

RACES: list[dict] = [
    {"key": "elves", "name": "Elves"},
    {"key": "ents", "name": "Ents"},
    {"key": "hobbits", "name": "Hobbits"},
    {"key": "humans", "name": "Humans"},
    {"key": "dwarves", "name": "Dwarves"},
    {"key": "wizards", "name": "Wizards"},
]
