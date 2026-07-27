"""Fixed action-space indexing for policy networks.

Every legal move dict maps to one of ACTION_SPACE indices. The mapping is
total for real games (decode goes through legal_moves matching).
"""

from duel.engine.alliances import TOKENS
from duel.engine.cards import CARDS
from duel.engine.game import ADJ, REGION_KEYS
from duel.engine.landmarks import LANDMARKS

TILE_IDS = [lm.id for lm in LANDMARKS]  # 9
TOKEN_IDS = [t.id for t in TOKENS]  # 18
CARD_IDS = [c.id for c in CARDS]  # 69
RACES6 = ["elves", "ents", "hobbits", "humans", "dwarves", "wizards"]
EDGES_DIR = sorted((a, b) for a in REGION_KEYS for b in ADJ[a])  # 22 directed

_OFFSETS: dict[str, int] = {}
_SIZE = 0


def _block(name: str, n: int) -> None:
    global _SIZE
    _OFFSETS[name] = _SIZE
    _SIZE += n


_block("play", 20)
_block("discard", 20)
_block("tile", len(TILE_IDS))
_block("place", 7)
_block("move", len(EDGES_DIR))
_block("kill", 7)
_block("raze", 7)
_block("pick_token", len(TOKEN_IDS))
_block("pick_race", 6)
_block("discard_play", len(CARD_IDS))
_block("strip_grey", len(CARD_IDS))
_block("shire_pick", 20)
_block("grond_target", 7)
_block("retreat", 7)
_block("ents_kill", 7)
_block("ents_coin", 1)
_block("ents_move", len(EDGES_DIR))
_block("skip", 1)
_block("extra", 2)  # optional extra turn from the quest track: decline / take

N_ACTIONS = _SIZE  # 321 (append-only: old policy heads are zero-padded on load)

_REGION_IDX = {r: i for i, r in enumerate(REGION_KEYS)}
_EDGE_IDX = {e: i for i, e in enumerate(EDGES_DIR)}
_TILE_IDX = {t: i for i, t in enumerate(TILE_IDS)}
_TOKEN_IDX = {t: i for i, t in enumerate(TOKEN_IDS)}
_CARD_IDX = {c: i for i, c in enumerate(CARD_IDS)}
_RACE_IDX = {r: i for i, r in enumerate(RACES6)}


def move_to_index(move: dict, game) -> int:
    t = move["type"]
    if t == "play":
        return _OFFSETS["play"] + move["slot"]
    if t == "discard":
        return _OFFSETS["discard"] + move["slot"]
    if t == "tile":
        return _OFFSETS["tile"] + _TILE_IDX[move["tile"]]
    if t == "place":
        return _OFFSETS["place"] + _REGION_IDX[move["region"]]
    if t == "move":
        return _OFFSETS["move"] + _EDGE_IDX[(move["from"], move["to"])]
    if t == "kill":
        return _OFFSETS["kill"] + _REGION_IDX[move["region"]]
    if t == "raze":
        return _OFFSETS["raze"] + _REGION_IDX[move["region"]]
    if t == "pick_token":
        return _OFFSETS["pick_token"] + _TOKEN_IDX[move["token"]]
    if t == "pick_race":
        return _OFFSETS["pick_race"] + _RACE_IDX[move["race"]]
    if t == "discard_play":
        return _OFFSETS["discard_play"] + _CARD_IDX[game.discard_open[move["index"]].id]
    if t == "strip_grey":
        card = game.players[1 - game.current].played[move["index"]]
        return _OFFSETS["strip_grey"] + _CARD_IDX[card.id]
    if t == "shire_pick":
        return _OFFSETS["shire_pick"] + move["slot"]
    if t == "grond_target":
        return _OFFSETS["grond_target"] + _REGION_IDX[move["region"]]
    if t == "retreat":
        return _OFFSETS["retreat"] + _REGION_IDX[move["to"]]
    if t == "ents_kill":
        return _OFFSETS["ents_kill"] + _REGION_IDX[move["region"]]
    if t == "ents_coin":
        return _OFFSETS["ents_coin"]
    if t == "ents_move":
        return _OFFSETS["ents_move"] + _EDGE_IDX[(move["from"], move["to"])]
    if t == "skip":
        return _OFFSETS["skip"]
    if t == "extra":
        return _OFFSETS["extra"] + int(move["take"])
    raise ValueError(f"unmapped move {move}")


def legal_indices(game) -> tuple[list[dict], list[int]]:
    moves = game.legal_moves()
    return moves, [move_to_index(m, game) for m in moves]
