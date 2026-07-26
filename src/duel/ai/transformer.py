"""Value transformer over component tokens (ZeusAI-style, scaled to our data)."""

import numpy as np
import torch
from torch import nn

from duel.ai.value_net import MODELS
from duel.engine.tokens import N_TOKENS, TOKEN_TYPES, F


class TValueNet(nn.Module):
    def __init__(self, d_model: int = 128, heads: int = 4, layers: int = 3):
        super().__init__()
        self.proj = nn.Linear(F, d_model)
        self.type_emb = nn.Embedding(8, d_model)
        self.pos_emb = nn.Embedding(N_TOKENS, d_model)
        enc = nn.TransformerEncoderLayer(
            d_model, heads, dim_feedforward=d_model * 4, batch_first=True, dropout=0.0
        )
        self.encoder = nn.TransformerEncoder(enc, layers)
        self.head = nn.Sequential(nn.Linear(d_model, 64), nn.ReLU(), nn.Linear(64, 1), nn.Tanh())
        self.register_buffer("types", torch.from_numpy(TOKEN_TYPES))
        self.register_buffer("pos", torch.arange(N_TOKENS))
        self.cfg = (d_model, heads, layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # x: (B, N_TOKENS, F)
        h = self.proj(x) + self.type_emb(self.types) + self.pos_emb(self.pos)
        h = self.encoder(h)
        return self.head(h.mean(dim=1)).squeeze(-1)

    @torch.no_grad()
    def values(self, tok_batch: np.ndarray) -> np.ndarray:
        self.eval()
        dev = next(self.parameters()).device
        t = torch.from_numpy(tok_batch).to(dev)
        return self(t).cpu().numpy()

    def save(self, name: str) -> None:
        MODELS.mkdir(parents=True, exist_ok=True)
        state = {k: v.cpu() for k, v in self.state_dict().items()}
        torch.save({"state": state, "cfg": self.cfg, "kind": "tvalue"}, MODELS / f"{name}.pt")

    @staticmethod
    def load(name: str) -> "TValueNet":
        data = torch.load(MODELS / f"{name}.pt", weights_only=True)
        net = TValueNet(*data["cfg"])
        net.load_state_dict(data["state"])
        return net
