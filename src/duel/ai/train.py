"""Self-play data generation and value-net training."""

import time

import numpy as np
import torch
from torch import nn

from duel.ai.bots import Bot
from duel.ai.journal import log_entry
from duel.ai.value_net import ValueNet
from duel.engine.encoding import encode
from duel.engine.game import Game


def generate_selfplay(
    bot: Bot,
    n_games: int,
    seed0: int = 0,
    sample_every: int = 1,
    gamma: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Play bot-vs-itself games; collect (obs from p's perspective, outcome for p).

    gamma < 1 discounts targets toward 0 for early states: an opening move
    carries little information about the final outcome, so its label is
    shrunk by gamma^(moves_remaining).
    """
    xs: list[np.ndarray] = []
    ys: list[float] = []
    for gi in range(n_games):
        g = Game(seed=seed0 + gi)
        states: list[np.ndarray] = []
        persp: list[int] = []
        steps: list[int] = []
        step = 0
        while g.winner is None and step < 600:
            move = bot.choose(g)
            g.apply(move)
            step += 1
            if step % sample_every == 0 and g.winner is None:
                for p in (0, 1):
                    states.append(encode(g, p))
                    persp.append(p)
                    steps.append(step)
        if g.winner is None:
            continue
        total = step
        for obs, p, t in zip(states, persp, steps, strict=True):
            y = 0.0 if g.winner == "draw" else 1.0 if g.winner == p else -1.0
            if gamma < 1.0:
                y *= gamma ** (total - t)
            xs.append(obs)
            ys.append(y)
    return np.stack(xs), np.asarray(ys, dtype=np.float32)


def _selfplay_chunk(args: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Worker: build the bot from a picklable factory and play a chunk."""
    make_bot, n_games, seed0, sample_every, gamma = args
    torch.set_num_threads(1)
    bot = make_bot()
    return generate_selfplay(bot, n_games, seed0=seed0, sample_every=sample_every, gamma=gamma)


def generate_selfplay_parallel(
    make_bot,
    n_games: int,
    seed0: int = 0,
    sample_every: int = 1,
    gamma: float = 1.0,
    workers: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Fan self-play out over processes. `make_bot` must be picklable."""
    from concurrent.futures import ProcessPoolExecutor

    chunk = max(1, n_games // workers)
    jobs = []
    start = 0
    while start < n_games:
        n = min(chunk, n_games - start)
        jobs.append((make_bot, n, seed0 + start, sample_every, gamma))
        start += n
    xs, ys = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for x, y in pool.map(_selfplay_chunk, jobs):
            xs.append(x)
            ys.append(y)
    return np.concatenate(xs), np.concatenate(ys)


def train_net(
    net: ValueNet,
    x: np.ndarray,
    y: np.ndarray,
    epochs: int = 4,
    batch: int = 512,
    lr: float = 1e-3,
    model_name: str = "net",
) -> float:
    t0 = time.perf_counter()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if dev == "cuda" and batch < 2048:
        batch = 4096  # small batches starve the GPU
    net.to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    xt = torch.from_numpy(x).to(dev)
    yt = torch.from_numpy(y).to(dev)
    n = len(xt)
    last = 0.0
    net.train()
    for _ in range(epochs):
        perm = torch.randperm(n, device=dev)
        total = 0.0
        for i in range(0, n, batch):
            idx = perm[i : i + batch]
            opt.zero_grad()
            pred = net(xt[idx])
            loss = loss_fn(pred, yt[idx])
            loss.backward()
            opt.step()
            total += loss.detach() * len(idx)
        last = float(total) / n
    net.cpu()
    log_entry(
        "train",
        model=model_name,
        samples=n,
        loss=round(last, 4),
        epochs=epochs,
        secs=round(time.perf_counter() - t0, 1),
    )
    return last
