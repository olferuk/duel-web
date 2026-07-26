"""Static board data: the 7 regions of Middle-earth.

`pos` are map coordinates in a 100x52 box (landscape, roughly the real
board's aspect ratio), eyeballed from the rulebook photos — used only for
drawing the UI.

Adjacency: lindon-enedwaith removed per the owner (board in hand); the rest
still to be re-verified against the real central board.
"""

# Neat 3-2-2 grid (rows y=9/26/43): reads like a diagram since we don't
# draw the real map art anyway.
REGIONS: list[dict] = [
    {"key": "lindon", "name": "Линдон", "pos": (16, 9)},
    {"key": "arnor", "name": "Арнор", "pos": (50, 9)},
    {"key": "rhovanion", "name": "Рованион", "pos": (84, 9)},
    {"key": "enedwaith", "name": "Энедвайт", "pos": (33, 26)},
    {"key": "rohan", "name": "Рохан", "pos": (67, 26)},
    {"key": "gondor", "name": "Гондор", "pos": (42, 43)},
    {"key": "mordor", "name": "Мордор", "pos": (76, 43)},
]

EDGES: list[tuple[str, str]] = [
    ("lindon", "arnor"),
    ("arnor", "enedwaith"),
    ("arnor", "rhovanion"),
    ("rhovanion", "rohan"),
    ("rhovanion", "mordor"),
    ("enedwaith", "rohan"),
    ("enedwaith", "gondor"),
    ("rohan", "gondor"),
    ("rohan", "mordor"),
    ("gondor", "mordor"),
]

RACES: list[dict] = [
    {"key": "elves", "name": "Эльфы"},
    {"key": "ents", "name": "Энты"},
    {"key": "hobbits", "name": "Хоббиты"},
    {"key": "humans", "name": "Люди"},
    {"key": "dwarves", "name": "Гномы"},
    {"key": "wizards", "name": "Волшебники"},
]
