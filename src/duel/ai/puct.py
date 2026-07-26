"""PUCT search with policy priors + value net (AlphaZero/ZeusAI style)."""

import math
import random

import numpy as np
import torch
from torch import nn

from duel.ai.actions import N_ACTIONS, legal_indices
from duel.ai.bots import Bot
from duel.ai.value_net import MODELS
from duel.engine.encoding import OBS_SIZE, encode
from duel.engine.game import Game


class PVNet(nn.Module):
    """Shared trunk, value head (tanh) + policy head (logits over N_ACTIONS)."""

    def __init__(self, trunk: tuple[int, ...] = (768, 512), in_size: int | None = None):
        super().__init__()
        prev = in_size or OBS_SIZE
        layers: list[nn.Module] = []
        for h in trunk:
            layers += [nn.Linear(prev, h), nn.ReLU()]
            prev = h
        self.trunk = nn.Sequential(*layers)
        self.value_head = nn.Sequential(nn.Linear(prev, 1), nn.Tanh())
        self.policy_head = nn.Linear(prev, N_ACTIONS)
        self.trunk_sizes = trunk

    def forward(self, x: torch.Tensor):
        h = self.trunk(x)
        return self.value_head(h).squeeze(-1), self.policy_head(h)

    @torch.no_grad()
    def infer(self, obs: np.ndarray):
        self.eval()
        dev = next(self.parameters()).device
        t = torch.from_numpy(obs).to(dev)
        v, logits = self(t)
        return v.cpu().numpy(), logits.cpu().numpy()

    def save(self, name: str) -> None:
        MODELS.mkdir(parents=True, exist_ok=True)
        state = {k: v.cpu() for k, v in self.state_dict().items()}
        torch.save({"state": state, "trunk": self.trunk_sizes}, MODELS / f"{name}.pt")

    @staticmethod
    def load(name: str) -> "PVNet":
        data = torch.load(MODELS / f"{name}.pt", weights_only=True)
        state = data["state"]
        in_size = state["trunk.0.weight"].shape[1]
        net = PVNet(tuple(data["trunk"]), in_size=in_size)
        # action space is append-only: pad old policy heads with zeros
        old_n = state["policy_head.weight"].shape[0]
        if old_n < N_ACTIONS:
            pad = N_ACTIONS - old_n
            w = state["policy_head.weight"]
            state["policy_head.weight"] = torch.cat([w, torch.zeros(pad, w.shape[1])])
            state["policy_head.bias"] = torch.cat([state["policy_head.bias"], torch.zeros(pad)])
        net.load_state_dict(state)
        return net


class _Node:
    __slots__ = ("children", "moves", "n", "p", "state", "value", "w")

    def __init__(self, state: Game):
        self.state = state
        self.moves: list | None = None  # lazily expanded
        self.children: dict[int, _Node] = {}
        self.p: np.ndarray | None = None  # priors over move list
        self.n: np.ndarray | None = None
        self.w: np.ndarray | None = None
        self.value = 0.0


def _terminal_value(g: Game) -> float:
    if g.winner == "draw":
        return 0.0
    return 1.0 if g.winner == 0 else -1.0


class PuctBot(Bot):
    def __init__(
        self,
        net: PVNet,
        sims: int = 64,
        c_puct: float = 1.5,
        seed: int = 0,
        name: str = "puct",
        dirichlet: float = 0.0,  # eps for root noise (self-play: 0.25)
        temp_moves: int = 0,  # sample by visits for the first N plies
        gumbel_m: int = 0,  # >0 enables Gumbel root selection with top-m
    ):
        self.gumbel_m = gumbel_m
        self.net = net
        self.sims = sims
        self.c = c_puct
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.name = name
        self.dirichlet = dirichlet
        self.temp_moves = temp_moves
        self.ply = 0

    def new_game(self) -> None:
        self.ply = 0

    # -------- core search --------
    def _expand(self, node: _Node) -> float:
        """Evaluate leaf: set priors over legal moves, return value (p0 view)."""
        g = node.state
        if g.winner is not None:
            return _terminal_value(g)
        moves, idxs = legal_indices(g)
        obs = encode(g, 0)  # absolute perspective for value sign consistency
        v, logits = self.net.infer(obs[None, :])
        lg = logits[0][idxs]
        lg = lg - lg.max()
        pri = np.exp(lg)
        pri /= pri.sum()
        node.moves = moves
        node.p = pri
        node.n = np.zeros(len(moves), dtype=np.int32)
        node.w = np.zeros(len(moves), dtype=np.float64)
        return float(v[0])

    def _simulate(self, node: _Node) -> float:
        path: list[tuple[_Node, int]] = []
        while True:
            if node.moves is None:  # leaf
                value = self._expand(node)
                break
            if node.state.winner is not None:
                value = _terminal_value(node.state)
                break
            sign = 1.0 if node.state.current == 0 else -1.0
            sqrt_n = math.sqrt(node.n.sum() + 1)
            q = np.where(node.n > 0, sign * node.w / np.maximum(node.n, 1), 0.0)
            u = q + self.c * node.p * sqrt_n / (1 + node.n)
            k = int(np.argmax(u))
            path.append((node, k))
            child = node.children.get(k)
            if child is None:
                gs = node.state.clone()
                gs.apply(node.moves[k])
                child = _Node(gs)
                node.children[k] = child
            node = child
        for parent, k in path:
            parent.n[k] += 1
            parent.w[k] += value
        return value

    def _root_gumbel(self, game: Game) -> dict:
        """Gumbel AlphaZero root: top-m by logits+Gumbel, sequential halving.

        Guarantees policy improvement with tiny simulation budgets.
        """
        root = _Node(game.clone())
        self._expand(root)
        n_moves = len(root.moves)
        m = min(self.gumbel_m, n_moves)
        logp = np.log(np.maximum(root.p, 1e-12))
        # Gumbel noise implements SAMPLING from the improved policy — that is
        # exploration machinery for self-play only; competitive play is argmax
        explore = self.dirichlet > 0 or self.ply <= self.temp_moves
        gumbel = self.np_rng.gumbel(size=n_moves) if explore else np.zeros(n_moves)
        order = np.argsort(-(logp + gumbel))
        cand = list(order[:m])
        sign = 1.0 if game.current == 0 else -1.0
        budget = self.sims
        phases = max(1, math.ceil(math.log2(max(m, 2))))
        phase_no = 0
        while len(cand) > 1 and budget > 0:
            phase_no += 1
            remaining_phases = max(1, phases - phase_no + 1)
            per_cand = max(1, (budget // remaining_phases) // len(cand))
            for k in cand:
                for _ in range(min(per_cand, budget)):
                    child = root.children.get(k)
                    if child is None:
                        gs = root.state.clone()
                        gs.apply(root.moves[k])
                        child = _Node(gs)
                        root.children[k] = child
                    v = self._simulate(child)
                    root.n[k] += 1
                    root.w[k] += v
                    budget -= 1
            q = np.array([sign * root.w[k] / max(root.n[k], 1) for k in cand])
            # sigma grows with visit counts (Gumbel-AZ style): trust Q more
            # as estimates sharpen
            sigma = 1.0 + 0.15 * max(root.n[k] for k in cand)
            score = logp[cand] + gumbel[cand] + sigma * q
            keep = max(1, len(cand) // 2)
            cand = [cand[i] for i in np.argsort(-score)[:keep]]
        k = cand[0]
        self.last_visits = (root.moves, np.maximum(root.n.astype(np.float64), 1e-9))
        return root.moves[k]

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        self.ply += 1
        if len(moves) == 1:
            return moves[0]
        if getattr(self, "gumbel_m", 0):
            return self._root_gumbel(game)
        root = _Node(game.clone())
        self._expand(root)
        if self.dirichlet > 0 and root.p is not None and len(root.p) > 1:
            noise = self.np_rng.dirichlet([0.3] * len(root.p))
            root.p = (1 - self.dirichlet) * root.p + self.dirichlet * noise
        for _ in range(self.sims):
            self._simulate(root)
        visits = root.n.astype(np.float64)
        if self.ply <= self.temp_moves:
            probs = visits / visits.sum()
            k = int(self.np_rng.choice(len(probs), p=probs))
        else:
            k = int(np.argmax(visits))
        self.last_visits = (root.moves, visits)  # for training targets
        return root.moves[k]
