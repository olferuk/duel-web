"""Personality bots: honest search with a value bias toward a play style.

The bias is added INSIDE the leaf evaluation, so the search builds coherent
plans around the preference (an aggressor prepares invasions, not random
attacks). Both players in the bot's imagination share the bias — that is the
classic "style assumption" and it is fine for a style bot.

Metrics are normalized to ~[0, 1] and applied as a p0-minus-p1 difference,
so the same eval works whichever seat the bot occupies.
"""

from duel.engine.encoding import encode
from duel.engine.game import REGION_KEYS, Game


def _quest_metric(g: Game, p: int) -> float:
    prog = (g.quest.frodo - 14) if p == 0 else g.quest.nazgul_progress
    return prog / 14.0


def _war_metric(g: Game, p: int) -> float:
    units = sum(g.board_units[r][p] for r in REGION_KEYS)
    forts = sum(g.board_forts[r][p] for r in REGION_KEYS)
    return min(1.0, (units + 1.6 * forts) / 12.0)


def _races_metric(g: Game, p: int) -> float:
    return g.players[p].race_symbols_for_victory() / 6.0


def _coins_metric(g: Game, p: int) -> float:
    return min(g.players[p].coins, 16) / 16.0


def _presence_metric(g: Game, p: int) -> float:
    return sum(
        1 for r in REGION_KEYS if g.board_units[r][p] > 0 or g.board_forts[r][p] > 0
    ) / 7.0


def _chains_metric(g: Game, p: int) -> float:
    return min(len(g.players[p].links), 8) / 8.0


def _deny_races_metric(g: Game, p: int) -> float:
    # «души чужие союзы»: моя метрика — НЕхватка рас у соперника
    return 1.0 - g.players[1 - p].race_symbols_for_victory() / 6.0


PROFILES = {
    "frodo": _quest_metric,
    "witch_king": _war_metric,
    "galadriel": _races_metric,
    "gollum": _coins_metric,
    "presence": _presence_metric,
    "chains": _chains_metric,
    "deny": _deny_races_metric,
}


def personality_eval(net, profile: str, lam: float = 0.25):
    """Leaf eval: net value (p0 view) + lam * (metric(p0) - metric(p1))."""
    metric = PROFILES[profile]

    def ev(state: Game) -> float:
        base = float(net.values(encode(state, 0)[None, :])[0])
        return base + lam * (metric(state, 0) - metric(state, 1))

    return ev
