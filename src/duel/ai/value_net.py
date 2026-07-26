"""PyTorch value network over the 1168-feature encoding.

V(encode(state, p)) estimates the final outcome for player p in [-1, 1].
"""

from pathlib import Path

import numpy as np
import torch
from torch import nn

from duel.ai.bots import Bot
from duel.engine.encoding import OBS_SIZE, encode
from duel.engine.game import Game

MODELS = Path(__file__).resolve().parents[3] / "analysis" / "lab" / "models"

torch.set_num_threads(4)


class ValueNet(nn.Module):
    def __init__(
        self,
        hidden: tuple[int, ...] = (512, 256),
        in_size: int | None = None,
        in_mask: np.ndarray | None = None,
    ):
        super().__init__()
        layers: list[nn.Module] = []
        prev = in_size or OBS_SIZE
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.ReLU()]
            prev = h
        layers += [nn.Linear(prev, 1), nn.Tanh()]
        self.net = nn.Sequential(*layers)
        self.hidden = hidden
        mask_t = (
            torch.from_numpy(in_mask.astype("float32"))
            if in_mask is not None
            else torch.ones(in_size or OBS_SIZE)
        )
        self.register_buffer("in_mask", mask_t)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x * self.in_mask).squeeze(-1)

    @torch.no_grad()
    def values(self, obs_batch: np.ndarray) -> np.ndarray:
        self.eval()
        first = self.net[0]
        if obs_batch.shape[-1] > first.in_features:
            # older model trained on a feature prefix — newer features appended
            obs_batch = obs_batch[..., : first.in_features]
        dev = first.weight.device
        t = torch.from_numpy(obs_batch).to(dev)
        return self(t).cpu().numpy()

    def to_gpu(self) -> "ValueNet":
        if torch.cuda.is_available():
            self.cuda()
        return self

    def to_cpu(self) -> "ValueNet":
        self.cpu()
        return self

    def save(self, name: str) -> Path:
        MODELS.mkdir(parents=True, exist_ok=True)
        path = MODELS / f"{name}.pt"
        state = {k: v.cpu() for k, v in self.state_dict().items()}
        torch.save({"state": state, "hidden": self.hidden}, path)  # in_mask rides in state
        return path

    @staticmethod
    def load(name: str) -> "ValueNet":
        data = torch.load(MODELS / f"{name}.pt", weights_only=True)
        in_size = data["state"]["net.0.weight"].shape[1]
        net = ValueNet(tuple(data["hidden"]), in_size=in_size)
        if "in_mask" not in data["state"]:  # legacy checkpoints
            data["state"]["in_mask"] = torch.ones(in_size)
        net.load_state_dict(data["state"])
        return net


class NetBot(Bot):
    """Greedy afterstate maximization using a value net (batched forward)."""

    def __init__(self, net: ValueNet, name: str = "net", epsilon: float = 0.0, seed: int = 0):
        import random

        self.net = net
        self.name = name
        self.epsilon = epsilon
        self.rng = random.Random(seed)

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        if len(moves) == 1:
            return moves[0]
        if self.epsilon and self.rng.random() < self.epsilon:
            return self.rng.choice(moves)
        me = game.current
        obs = np.empty((len(moves), OBS_SIZE), dtype=np.float32)
        terminal_bonus = np.zeros(len(moves), dtype=np.float32)
        for i, m in enumerate(moves):
            g2 = game.clone()
            g2.apply(m)
            obs[i] = encode(g2, me)
            if g2.winner is not None:
                if g2.winner == me:
                    terminal_bonus[i] = 100.0
                elif g2.winner == "draw":
                    terminal_bonus[i] = 0.0
                else:
                    terminal_bonus[i] = -100.0
        vals = self.net.values(obs) + terminal_bonus
        return moves[int(np.argmax(vals))]
