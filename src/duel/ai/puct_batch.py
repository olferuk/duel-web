"""Batched-leaf PUCT: K descents with virtual visits, one net call per batch.

Same tree policy as PuctBot; only leaf evaluation/expansion is batched, so it
works with any object exposing PVNet's `infer(obs) -> (values, logits)` —
including a GPU inference client (duel.ai.gpu_server).
"""

import numpy as np

from duel.ai.actions import legal_indices
from duel.ai.puct import PuctBot, _Node, _terminal_value
from duel.engine.encoding import encode
from duel.engine.game import Game


class BatchPuctBot(PuctBot):
    def __init__(self, *args, batch: int = 8, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch = batch

    def _descend(self, root: _Node):
        """Select to a leaf, adding virtual visits (n) along the way."""
        import math

        node = root
        path: list[tuple[_Node, int]] = []
        while True:
            if node.moves is None or node.state.winner is not None:
                return node, path
            sign = 1.0 if node.state.current == 0 else -1.0
            sqrt_n = math.sqrt(node.n.sum() + 1)
            q = np.where(node.n > 0, sign * node.w / np.maximum(node.n, 1), 0.0)
            u = q + self.c * node.p * sqrt_n / (1 + node.n)
            k = int(np.argmax(u))
            path.append((node, k))
            node.n[k] += 1  # virtual visit: diverts the next descent in this batch
            child = node.children.get(k)
            if child is None:
                gs = node.state.clone()
                gs.apply(node.moves[k])
                child = _Node(gs)
                node.children[k] = child
            node = child

    @staticmethod
    def _expand_from(leaf: _Node, moves: list, idxs: np.ndarray, logits: np.ndarray) -> None:
        lg = logits[idxs]
        lg = lg - lg.max()
        pri = np.exp(lg)
        pri /= pri.sum()
        leaf.moves = moves
        leaf.p = pri
        leaf.n = np.zeros(len(moves), dtype=np.int32)
        leaf.w = np.zeros(len(moves), dtype=np.float64)

    def _run_sims(self, root: _Node, sims: int) -> None:
        done = 0
        while done < sims:
            kbatch = min(self.batch, sims - done)
            pend: dict[int, tuple[_Node, list]] = {}
            legal: dict[int, tuple[list, np.ndarray]] = {}
            order: list[int] = []
            for _ in range(kbatch):
                leaf, path = self._descend(root)
                key = id(leaf)
                if key not in pend:
                    pend[key] = (leaf, [])
                    order.append(key)
                    if leaf.state.winner is None and leaf.moves is None:
                        moves, idxs = legal_indices(leaf.state)
                        legal[key] = (moves, np.asarray(idxs))
                pend[key][1].append(path)
            to_eval = [key for key in order if key in legal]
            if to_eval:
                obs = np.stack([encode(pend[key][0].state, 0) for key in to_eval])
                vs, logits = self.net.infer(obs)
            vi = 0
            for key in order:
                leaf, paths = pend[key]
                if leaf.state.winner is not None:
                    value = _terminal_value(leaf.state)
                elif key in legal:
                    value = float(vs[vi])
                    self._expand_from(leaf, *legal[key], logits[vi])
                    vi += 1
                else:  # already-expanded node reached as "leaf" — cannot happen
                    value = 0.0
                for path in paths:
                    for parent, k in path:
                        parent.w[k] += value  # n was counted during descent
            done += kbatch

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        self.ply += 1
        if len(moves) == 1:
            return moves[0]
        root = _Node(game.clone())
        # root expansion: single (non-batched) infer
        PuctBot._expand(self, root)
        if self.dirichlet > 0 and root.p is not None and len(root.p) > 1:
            noise = self.np_rng.dirichlet([0.3] * len(root.p))
            root.p = (1 - self.dirichlet) * root.p + self.dirichlet * noise
        self._run_sims(root, self.sims)
        visits = root.n.astype(np.float64)
        if self.ply <= self.temp_moves:
            probs = visits / visits.sum()
            k = int(self.np_rng.choice(len(probs), p=probs))
        else:
            k = int(np.argmax(visits))
        self.last_visits = (root.moves, visits)
        return root.moves[k]
