"""Batched-leaf MCTS: collect K leaves per pass (virtual visits), evaluate as
one net batch. Same tree policy as MctsBot; only leaf evaluation is batched.

Virtual visit = node.n incremented during descent, so concurrent selections in
one pass diverge; backprop then adds only w (n already counted).
"""

import numpy as np

from duel.ai.mcts import MctsBot, _Node, _terminal_value
from duel.engine.game import Game


class BatchMctsBot(MctsBot):
    def __init__(self, *args, net=None, batch: int = 8, **kwargs):
        super().__init__(*args, **kwargs)
        self.net = net
        self.batch = batch

    def _batch_values(self, states: list[Game]) -> np.ndarray:
        from duel.engine.encoding import encode

        obs = np.stack([encode(s, 0) for s in states])
        return self.net.values(obs)

    def _select_leaf(self, root: _Node):
        """Descend with virtual visits; returns (leaf, path, terminal_value|None)."""
        import math

        node = root
        path: list[_Node] = []
        while node.state.winner is None:
            if node.untried:
                idx = node.untried.pop(self.rng.randrange(len(node.untried)))
                child_state = node.state.clone()
                child_state.apply(node.moves[idx])
                child = _Node(child_state)
                node.children[idx] = child
                node.n += 1
                path.append(node)
                child.n += 1
                path.append(child)
                if child.state.winner is not None:
                    return child, path, _terminal_value(child.state)
                return child, path, None
            if not node.children:  # no legal moves, not terminal: stalled state
                node.n += 1
                path.append(node)
                return node, path, 0.0
            sign = 1.0 if node.state.current == 0 else -1.0
            logn = math.log(node.n + 1)
            best_idx, best_u = -1, -1e18
            for idx, ch in node.children.items():
                u = sign * ch.w / (ch.n + 1e-9) + self.c * math.sqrt(logn / (ch.n + 1e-9))
                if u > best_u:
                    best_idx, best_u = idx, u
            node.n += 1
            path.append(node)
            node = node.children[best_idx]
        node.n += 1
        path.append(node)
        return node, path, _terminal_value(node.state)

    def _run(self, root: _Node, sims: int) -> None:
        done = 0
        while done < sims:
            k = min(self.batch, sims - done)
            pending = []
            eval_states = []
            for _ in range(k):
                leaf, path, tval = self._select_leaf(root)
                pending.append((path, tval))
                if tval is None:
                    eval_states.append(leaf.state)
            vals = self._batch_values(eval_states) if eval_states else []
            vi = 0
            for path, tval in pending:
                if tval is None:
                    tval = float(vals[vi])
                    vi += 1
                for node in path:
                    node.w += tval
            done += k

    def root_value(self, game: Game) -> float:
        from duel.ai.mcts import _terminal_value

        root = _Node(game.clone())
        if not root.moves:
            return _terminal_value(game)
        self._run(root, self.sims)
        return root.w / max(root.n, 1)

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        if len(moves) == 1:
            self.last_visits = None
            return moves[0]
        root = _Node(game.clone())
        self._run(root, self.sims)
        visits = [root.children[i].n if i in root.children else 0 for i in range(len(root.moves))]
        self.last_visits = (root.moves, visits)
        self.last_root_value = root.w / max(root.n, 1)
        best = max(root.children.items(), key=lambda kv: kv[1].n)
        return root.moves[best[0]]
