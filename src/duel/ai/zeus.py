"""ZeusAI-style training loop: PUCT self-play + policy/value learning.

Usage: python -m duel.ai.zeus run <generations> [games_per_gen] [sims]
"""

import sys
import time
from pathlib import Path

import numpy as np

from duel.ai.actions import N_ACTIONS, move_to_index
from duel.ai.journal import log_entry
from duel.ai.value_net import MODELS

ZDATA = Path(__file__).resolve().parents[3] / "analysis" / "lab" / "zeusdata"
WINDOW = 3  # replay window in generations


def _selfplay_chunk(args: tuple) -> str:
    gen, n_games, seed0, sims, out = args
    import torch

    torch.set_num_threads(1)
    from duel.ai.puct import PuctBot, PVNet
    from duel.engine.encoding import encode
    from duel.engine.game import Game

    net = PVNet.load(f"pv_gen{gen}")
    obs_l, pi_i, pi_p, zs = [], [], [], []
    for gi in range(n_games):
        bot = PuctBot(net, sims=sims, seed=seed0 + gi, dirichlet=0.25, temp_moves=20)
        bot.new_game()
        g = Game(seed=seed0 + gi)
        recs = []
        steps = 0
        while g.winner is None and steps < 600:
            mv = bot.choose(g)
            if len(g.legal_moves()) > 1 and hasattr(bot, "last_visits"):
                moves, visits = bot.last_visits
                idxs = [move_to_index(m, g) for m in moves]
                probs = visits / visits.sum()
                recs.append((encode(g, 0), idxs, probs))
            g.apply(mv)
            steps += 1
        if g.winner is None:
            continue
        z = 0.0 if g.winner == "draw" else (1.0 if g.winner == 0 else -1.0)
        for obs, idxs, probs in recs:
            obs_l.append(obs)
            pi_i.append(np.asarray(idxs, dtype=np.int16))
            pi_p.append(probs.astype(np.float32))
            zs.append(z)
    ZDATA.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        ZDATA / f"{out}.npz",
        obs=np.stack(obs_l).astype(np.float32),
        z=np.asarray(zs, dtype=np.float32),
        pi_i=np.asarray(pi_i, dtype=object),
        pi_p=np.asarray(pi_p, dtype=object),
        allow_pickle=True,
    )
    return f"{out}: {len(obs_l)} positions / {n_games} games"


def selfplay(gen: int, n_games: int, sims: int, workers: int = 12) -> None:
    from concurrent.futures import ProcessPoolExecutor

    chunk = max(1, n_games // workers)
    jobs = []
    start = 0
    k = 0
    while start < n_games:
        n = min(chunk, n_games - start)
        jobs.append((gen, n, 1_000_000 + gen * 50_000 + start * 20, sims, f"g{gen}_{k:02d}"))
        start += n
        k += 1
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for msg in pool.map(_selfplay_chunk, jobs):
            print(msg, flush=True)


def train(gen: int, epochs: int = 2, sup_replay: bool = False, lr: float = 1e-3) -> float:
    import torch

    from duel.ai.puct import PVNet

    files = []
    for g in range(max(0, gen - WINDOW + 1), gen + 1):
        files += sorted(ZDATA.glob(f"g{g}_*.npz"))
    obs_l, z_l, pi_pairs = [], [], []
    if sup_replay:
        # anti-forgetting: keep the champion supervision in every window
        wdata = Path(__file__).resolve().parents[3] / "analysis" / "lab" / "warmdata"
        for f in sorted(wdata.glob("w_*.npz")):
            d = np.load(f, allow_pickle=True)
            obs_l.append(d["obs"].astype(np.float32))
            z_l.append(0.5 * d["z"] + 0.5 * d["rv"])
            pi_pairs += list(zip(d["pi_i"], d["pi_p"], strict=True))
    for f in files:
        d = np.load(f, allow_pickle=True)
        obs_l.append(d["obs"])
        z_l.append(d["z"])
        pi_pairs += list(zip(d["pi_i"], d["pi_p"], strict=True))
    obs = np.concatenate(obs_l)
    z = np.concatenate(z_l)
    n = len(obs)
    print(f"train on {n} positions from {len(files)} shards", flush=True)

    # dense policy targets (sparse -> dense float16 would be 319*n*2B ~ ok dense f32 on gpu chunks)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    net = PVNet.load(f"pv_gen{gen}")
    net.to(dev)
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    obs_t = torch.from_numpy(obs).to(dev)
    z_t = torch.from_numpy(z).to(dev)
    pi_dense = np.zeros((n, N_ACTIONS), dtype=np.float32)
    for i, (ii, pp) in enumerate(pi_pairs):
        pi_dense[i, ii.astype(np.int32)] = pp
    pi_t = torch.from_numpy(pi_dense).to(dev)

    last = 0.0
    for _ in range(epochs):
        perm = torch.randperm(n, device=dev)
        tot = torch.zeros((), device=dev)
        for i in range(0, n, 2048):
            idx = perm[i : i + 2048]
            opt.zero_grad()
            v, logits = net(obs_t[idx])
            loss_v = torch.nn.functional.mse_loss(v, z_t[idx])
            logp = torch.nn.functional.log_softmax(logits, dim=-1)
            loss_p = -(pi_t[idx] * logp).sum(dim=-1).mean()
            loss = loss_v + loss_p
            loss.backward()
            opt.step()
            tot += loss.detach() * len(idx)
        last = float(tot) / n
    net.cpu()
    net.save(f"pv_gen{gen + 1}")
    return last


def _eval_chunk(args):
    import torch

    torch.set_num_threads(1)
    gen, n, seed0, sims, opponent = args
    from duel.ai.arena import play_game
    from duel.ai.puct import PuctBot, PVNet
    from duel.ai.recorder import make_bot

    net = PVNet.load(f"pv_gen{gen}")
    wa = wb = d = 0
    for i in range(n):
        A = PuctBot(net, sims=sims, seed=seed0 + i, name="zeus")
        B = make_bot(opponent, seed0 + i + 7)
        w = play_game(A, B, seed0 + i) if i % 2 == 0 else play_game(B, A, seed0 + i)
        if i % 2 == 1 and w in (0, 1):
            w = 1 - w
        if w == 0:
            wa += 1
        elif w == 1:
            wb += 1
        else:
            d += 1
    return wa, wb, d


def evaluate(gen: int, opponent: str, n: int = 100, sims: int = 64) -> str:
    import math
    from concurrent.futures import ProcessPoolExecutor

    jobs = [(gen, n // 10, 2_000_000 + gen * 10_000 + k * 700, sims, opponent) for k in range(10)]
    wa = wb = d = 0
    with ProcessPoolExecutor(max_workers=10) as pool:
        for ra, rb, rd in pool.map(_eval_chunk, jobs):
            wa += ra
            wb += rb
            d += rd
    tot = max(wa + wb, 1)
    p = wa / tot
    ci = 1.96 * math.sqrt(p * (1 - p) / tot) * 100
    return f"gen{gen} vs {opponent}: {wa}-{wb} (н:{d}) = {p * 100:.1f}% ±{ci:.1f}"


def run(
    generations: int, games_per_gen: int = 300, sims: int = 64, sup_replay: bool = False
) -> None:
    import torch

    from duel.ai.puct import PVNet

    if not (MODELS / "pv_gen0.pt").exists():
        torch.manual_seed(11)
        PVNet().save("pv_gen0")
        print("initialized pv_gen0", flush=True)
    log_entry(
        "note",
        title=f"ZeusAI-рельсы: старт ({generations} поколений × {games_per_gen} партий, "
        f"{sims} симуляций, PUCT+Dirichlet, replay-окно {WINDOW})",
        text="Policy+value сеть, таргеты политики — распределения визитов, "
        "выбор хода в self-play — сэмплированием по визитам первые 20 ходов.",
    )
    for gen in range(generations):
        t0 = time.time()
        selfplay(gen, games_per_gen, sims)
        loss = train(gen, sup_replay=sup_replay, lr=3e-4 if sup_replay else 1e-3)
        line = evaluate(gen + 1, "mcts150-heur", n=100, sims=sims)
        print(line, flush=True)
        log_entry(
            "note",
            title=f"Zeus gen{gen + 1} готов за {time.time() - t0:.0f} с (loss {loss:.3f})",
            text=line,
        )


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "run":
        run(
            int(sys.argv[2]),
            int(sys.argv[3]) if len(sys.argv) > 3 else 300,
            int(sys.argv[4]) if len(sys.argv) > 4 else 64,
            sup_replay=len(sys.argv) > 5 and sys.argv[5] == "sup",
        )
    elif cmd == "eval":
        print(
            evaluate(int(sys.argv[2]), sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 200)
        )
