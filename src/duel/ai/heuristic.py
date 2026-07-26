"""Hand-crafted evaluation of a game state for one player.

Returns a score roughly in [-1, 1]: +1 = certain win for `p`.
Weights are a parameter so the arena can test variants.
"""

from duel.engine.game import REGION_KEYS, Game
from duel.engine.quest import FRODO_START, HALF_STEPS

DEFAULT_WEIGHTS = {
    "quest": 1.0,  # own quest progress race
    "races": 1.0,  # distinct race symbols
    "regions": 1.0,  # board presence
    "material": 0.25,  # coins, skills, links, tokens
    "tempo": 0.15,  # units on board, forts
}


def _own_progress(game: Game, p: int) -> int:
    return game.quest.frodo - FRODO_START if p == 0 else game.quest.nazgul_progress


def _victory_scores(game: Game, p: int) -> tuple[float, float, float]:
    quest = _own_progress(game, p) / HALF_STEPS
    races = game.players[p].race_symbols_for_victory() / 6
    regions = game.presence_count(p) / 7
    return quest, races, regions


def _material(game: Game, p: int) -> float:
    pl = game.players[p]
    agg = pl._aggregates()
    return (
        min(pl.coins, 12) / 12 * 0.4
        + min(agg["skill_syms"], 10) / 10 * 0.35
        + len(agg["links"]) / 8 * 0.1
        + len(pl.tokens) / 4 * 0.15
    )


def _tempo(game: Game, p: int) -> float:
    units = sum(game.board_units[r][p] for r in REGION_KEYS)
    forts = game.forts_on_board(p)
    return min(units, 10) / 10 * 0.6 + min(forts, 3) / 3 * 0.4


def evaluate(game: Game, p: int, weights: dict | None = None) -> float:
    if game.winner is not None:
        if game.winner == "draw":
            return 0.0
        return 1.0 if game.winner == p else -1.0
    w = weights or DEFAULT_WEIGHTS
    o = 1 - p
    mq, mr, mg = _victory_scores(game, p)
    oq, or_, og = _victory_scores(game, o)

    def sharp(x: float) -> float:
        """Progress toward a victory matters more the closer it is."""
        return x * x

    mine = max(sharp(mq), sharp(mr), sharp(mg)) + 0.35 * (sharp(mq) + sharp(mr) + sharp(mg))
    theirs = max(sharp(oq), sharp(or_), sharp(og)) + 0.35 * (sharp(oq) + sharp(or_) + sharp(og))
    score = (
        w["quest"] * (sharp(mq) - sharp(oq))
        + w["races"] * (sharp(mr) - sharp(or_))
        + w["regions"] * (sharp(mg) - sharp(og))
        + w["material"] * (_material(game, p) - _material(game, o))
        + w["tempo"] * (_tempo(game, p) - _tempo(game, o))
        + 0.5 * (mine - theirs)
    )
    return max(-0.99, min(0.99, score / 3))
