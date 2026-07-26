"""Bot interface and the non-neural baselines."""

import random

from duel.ai.heuristic import evaluate
from duel.engine.game import Game


class Bot:
    name = "bot"

    def choose(self, game: Game) -> dict:
        raise NotImplementedError

    def new_game(self) -> None:
        """Called before each match (reset per-game caches)."""


class RandomBot(Bot):
    def __init__(self, seed: int = 0, name: str = "random"):
        self.rng = random.Random(seed)
        self.name = name

    def choose(self, game: Game) -> dict:
        return self.rng.choice(game.legal_moves())


class TwoPlyBot(Bot):
    """Maximize eval after the opponent's best greedy reply (2-ply minimax)."""

    def __init__(self, seed: int = 0, name: str = "2ply", weights: dict | None = None):
        self.rng = random.Random(seed)
        self.name = name
        self.weights = weights

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        if len(moves) == 1:
            return moves[0]
        me = game.current
        order = list(moves)
        self.rng.shuffle(order)
        best, best_v = None, -1e18
        for m in order:
            g2 = game.clone()
            g2.apply(m)
            if g2.winner is not None:
                v = evaluate(g2, me, self.weights) * 10
            elif g2.current == me or (g2.pending and g2.pending[0]["player"] == me):
                v = evaluate(g2, me, self.weights)  # extra turn / own pending
            else:
                # opponent picks their best reply
                v = 1e18
                for m2 in g2.legal_moves():
                    g3 = g2.clone()
                    g3.apply(m2)
                    v = min(v, evaluate(g3, me, self.weights))
            if v > best_v:
                best, best_v = m, v
        return best


class GreedyBot(Bot):
    """1-ply afterstate maximization of an evaluation function.

    An 'afterstate' here = the state after the move AND after resolving
    any own pending choices greedily is NOT done — pendings are part of
    the move tree, so evaluation happens right after the single move.
    """

    def __init__(
        self, seed: int = 0, name: str = "greedy", weights: dict | None = None, epsilon: float = 0.0
    ):
        self.rng = random.Random(seed)
        self.name = name
        self.weights = weights
        self.epsilon = epsilon

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        if len(moves) == 1:
            return moves[0]
        if self.epsilon and self.rng.random() < self.epsilon:
            return self.rng.choice(moves)
        me = game.current
        best, best_v = None, -1e9
        order = list(moves)
        self.rng.shuffle(order)  # random tie-breaking
        for m in order:
            g2 = game.clone()
            g2.apply(m)
            v = evaluate(g2, me, self.weights)
            if v > best_v:
                best, best_v = m, v
        return best
