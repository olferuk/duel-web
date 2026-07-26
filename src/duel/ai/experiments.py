"""Staged overnight experiments. Run: python -m duel.ai.experiments <stage>.

Every stage journals its hypothesis, matches, ELO updates and conclusions
to analysis/lab/journal.jsonl (rendered to report.html).
"""

import sys

from duel.ai.arena import Ladder, run_match_and_log
from duel.ai.bots import GreedyBot, RandomBot
from duel.ai.journal import log_entry
from duel.ai.mcts import MctsBot
from duel.ai.value_net import NetBot, ValueNet


def baseline_bots() -> dict:
    return {
        "random": RandomBot(seed=101),
        "greedy": GreedyBot(seed=102),
        "greedy-quest": GreedyBot(
            seed=103,
            name="greedy-quest",
            weights={"quest": 2.2, "races": 0.7, "regions": 0.7, "material": 0.25, "tempo": 0.1},
        ),
        "greedy-war": GreedyBot(
            seed=104,
            name="greedy-war",
            weights={"quest": 0.7, "races": 0.7, "regions": 2.2, "material": 0.25, "tempo": 0.4},
        ),
        "greedy-races": GreedyBot(
            seed=105,
            name="greedy-races",
            weights={"quest": 0.7, "races": 2.2, "regions": 0.7, "material": 0.3, "tempo": 0.1},
        ),
    }


def stage1() -> None:
    log_entry(
        "note",
        title="Стадия 1: базовые боты",
        text="Гипотеза: жадная эвристика сильно бьёт случайного; специализированные версии "
        "(гонка Кольца / война / расы) покажут, какая стратегия доминирует. "
        "MCTS с эвристикой в листьях должен обойти чистый 1-ply greedy.",
    )
    ladder = Ladder()
    bots = baseline_bots()
    fast = list(bots.values())
    for i, a in enumerate(fast):
        for b in fast[i + 1 :]:
            run_match_and_log(ladder, a, b, 30, seed0=1000 + i * 100)
    ladder.publish()

    mcts_h = MctsBot(sims=150, seed=106, name="mcts150-heur", leaf="heuristic")
    mcts_r = MctsBot(sims=100, seed=107, name="mcts100-roll", leaf="rollout")
    for m, n_games in ((mcts_h, 14), (mcts_r, 10)):
        for op in ("greedy", "random"):
            run_match_and_log(ladder, m, bots[op], n_games, seed0=2000)
    run_match_and_log(ladder, mcts_h, mcts_r, 10, seed0=2100)
    ladder.publish()
    log_entry(
        "note",
        title="Стадия 1 завершена",
        mood="ok",
        text="Смотри таблицу ELO выше — она определяет соперников для нейросети.",
    )


def stage2() -> None:
    from duel.ai.train import generate_selfplay, train_net

    log_entry(
        "note",
        title="Стадия 2: первая нейросеть (v1)",
        text="Гипотеза: value-сеть (1168→512→256→1), обученная на исходах self-play жадного "
        "бота с ε=0.15, обыграет своего учителя — она видит целостную картину состояния, "
        "а не сумму слагаемых эвристики.",
    )
    teacher = GreedyBot(seed=201, name="teacher", epsilon=0.15)
    x, y = generate_selfplay(teacher, n_games=900, seed0=50_000)
    log_entry("note", title="Данные готовы", text=f"{len(x)} примеров из 900 партий.")
    net = ValueNet()
    train_net(net, x, y, epochs=5, model_name="v1")
    net.save("v1")

    ladder = Ladder()
    v1 = NetBot(net, name="net-v1")
    bots = baseline_bots()
    run_match_and_log(ladder, v1, bots["greedy"], 40, seed0=3000)
    run_match_and_log(ladder, v1, bots["greedy-quest"], 30, seed0=3100)
    run_match_and_log(ladder, v1, bots["random"], 20, seed0=3200)
    run_match_and_log(
        ladder,
        v1,
        MctsBot(sims=150, seed=202, name="mcts150-heur", leaf="heuristic"),
        12,
        seed0=3300,
    )
    ladder.publish()


def stage3() -> None:
    """Iterated self-play: vN+1 learns from vN's games."""
    from duel.ai.train import generate_selfplay, train_net

    prev_name = sys.argv[2] if len(sys.argv) > 2 else "v1"
    new_name = sys.argv[3] if len(sys.argv) > 3 else "v2"
    games = int(sys.argv[4]) if len(sys.argv) > 4 else 700
    log_entry(
        "note",
        title=f"Стадия 3: {new_name} учится на партиях {prev_name}",
        text=f"Гипотеза: итерация self-play ({games} партий, ε=0.1) поднимет силу.",
    )
    prev = ValueNet.load(prev_name)
    gen_bot = NetBot(prev, name=f"{prev_name}-gen", epsilon=0.1, seed=301)
    x, y = generate_selfplay(gen_bot, n_games=games, seed0=60_000)
    log_entry("note", title="Данные готовы", text=f"{len(x)} примеров из {games} партий.")
    net = ValueNet.load(prev_name)  # warm start
    train_net(net, x, y, epochs=4, model_name=new_name)
    net.save(new_name)

    ladder = Ladder()
    fresh = NetBot(net, name=f"net-{new_name}")
    prev_bot = NetBot(prev, name=f"net-{prev_name}")
    run_match_and_log(ladder, fresh, prev_bot, 40, seed0=4000)
    run_match_and_log(ladder, fresh, GreedyBot(seed=302), 40, seed0=4100)
    ladder.publish()


def stage_mcts_net() -> None:
    """MCTS with a value net in the leaves vs plain net and heuristic MCTS."""
    from duel.engine.encoding import encode

    model = sys.argv[2] if len(sys.argv) > 2 else "v1"
    sims = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    net = ValueNet.load(model)
    log_entry(
        "note",
        title=f"Стадия MCTS+{model} ({sims} симуляций)",
        text="Гипотеза: поиск поверх value-сети сильнее чистой 1-ply сети.",
    )

    def eval_p0(state) -> float:
        return float(net.values(encode(state, 0)[None, :])[0])

    mcts_net = MctsBot(sims=sims, seed=401, name=f"mcts{sims}-{model}", eval_fn=eval_p0)
    ladder = Ladder()
    run_match_and_log(ladder, mcts_net, NetBot(net, name=f"net-{model}"), 16, seed0=5000)
    run_match_and_log(ladder, mcts_net, GreedyBot(seed=402), 16, seed0=5100)
    ladder.publish()


def eval_vs_pool(bot, n_fast: int = 30, n_slow: int = 10, seed0: int = 9000) -> None:
    """Matches against the whole baseline pool + ELO refit."""
    from duel.ai.arena import recompute_elo

    ladder = Ladder()
    bots = baseline_bots()
    run_match_and_log(ladder, bot, bots["greedy"], n_fast, seed0=seed0)
    run_match_and_log(ladder, bot, bots["greedy-quest"], n_fast, seed0=seed0 + 100)
    run_match_and_log(ladder, bot, bots["random"], 10, seed0=seed0 + 200)
    run_match_and_log(
        ladder,
        bot,
        MctsBot(sims=150, seed=901, name="mcts150-heur", leaf="heuristic"),
        n_slow,
        seed0=seed0 + 300,
    )
    run_match_and_log(
        ladder,
        bot,
        MctsBot(sims=100, seed=902, name="mcts100-roll", leaf="rollout"),
        n_slow,
        seed0=seed0 + 400,
    )
    recompute_elo().publish()


def stage4() -> None:
    """Champion attempt: bigger net, mixed data sources, more games."""
    import numpy as np

    from duel.ai.train import generate_selfplay, train_net

    base = sys.argv[2] if len(sys.argv) > 2 else "v2"
    games = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
    log_entry(
        "note",
        title=f"Стадия 4: чемпион (глубокая сеть, смешанные данные, база {base})",
        text=f"Гипотеза: сеть 1024-512-256 на смеси greedy- и net-self-play ({games} партий) "
        "обобщит лучше, чем узкая v1/v2 на одном источнике.",
    )
    prev = ValueNet.load(base)
    xs, ys = [], []
    x1, y1 = generate_selfplay(
        NetBot(prev, name="gen-net", epsilon=0.1, seed=501), n_games=games // 2, seed0=70_000
    )
    x2, y2 = generate_selfplay(GreedyBot(seed=502, epsilon=0.15), n_games=games // 2, seed0=80_000)
    xs = np.concatenate([x1, x2])
    ys = np.concatenate([y1, y2])
    log_entry("note", title="Данные готовы", text=f"{len(xs)} примеров из {games} партий.")
    net = ValueNet(hidden=(1024, 512, 256))
    train_net(net, xs, ys, epochs=6, model_name="champion")
    net.save("champion")
    eval_vs_pool(NetBot(net, name="net-champion"), seed0=10_000)


def stage_fixes() -> None:
    """Three hypotheses to fix the weak v1: discounted targets, bootstrap, hybrid."""
    from duel.ai.train import generate_selfplay, train_net

    log_entry(
        "note",
        title="Стадия «лечение v1»: три гипотезы",
        text="v1 проиграла учителю 7-30. Пробуем: (а) дисконт меток γ=0.985 — ранние ходы "
        "не должны получать полный ±1; (б) бутстрап: v2 на партиях самой v1; "
        "(в) гибрид: сеть + эвристика поровну.",
    )
    ladder = Ladder()

    # (a) discounted targets on fresh greedy data
    teacher = GreedyBot(seed=601, name="teacher", epsilon=0.15)
    x, y = generate_selfplay(teacher, n_games=900, seed0=90_000, gamma=0.985)
    net_d = ValueNet()
    train_net(net_d, x, y, epochs=5, model_name="v1d-discount")
    net_d.save("v1d")
    run_match_and_log(ladder, NetBot(net_d, name="net-v1d"), GreedyBot(seed=602), 40, seed0=11_000)

    # (b) bootstrap v2 from v1's own games
    v1 = ValueNet.load("v1")
    x2, y2 = generate_selfplay(
        NetBot(v1, name="v1-gen", epsilon=0.1, seed=603), n_games=600, seed0=95_000, gamma=0.985
    )
    net_b = ValueNet.load("v1")
    train_net(net_b, x2, y2, epochs=4, model_name="v2-bootstrap")
    net_b.save("v2")
    run_match_and_log(ladder, NetBot(net_b, name="net-v2"), GreedyBot(seed=604), 40, seed0=12_000)

    # (c) hybrid: net value + heuristic, equal weight
    from duel.ai.heuristic import evaluate as heval
    from duel.engine.encoding import encode as enc

    class HybridBot(GreedyBot):
        def __init__(self, net, name, seed):
            super().__init__(seed=seed, name=name)
            self.net = net

        def choose(self, game):
            import numpy as np

            moves = game.legal_moves()
            if len(moves) == 1:
                return moves[0]
            me = game.current
            afters = []
            for m in moves:
                g2 = game.clone()
                g2.apply(m)
                afters.append(g2)
            obs = np.stack([enc(g2, me) for g2 in afters])
            vals = self.net.values(obs)
            best_i, best_v = 0, -1e18
            for i, g2 in enumerate(afters):
                v = float(vals[i]) + heval(g2, me)
                if g2.winner is not None:
                    v += 100.0 if g2.winner == me else (0.0 if g2.winner == "draw" else -100.0)
                if v > best_v:
                    best_i, best_v = i, v
            return moves[best_i]

    hybrid = HybridBot(net_d, name="hybrid-v1d", seed=605)
    run_match_and_log(ladder, hybrid, GreedyBot(seed=606), 40, seed0=13_000)
    run_match_and_log(
        ladder,
        hybrid,
        MctsBot(sims=150, seed=607, name="mcts150-heur", leaf="heuristic"),
        12,
        seed0=13_500,
    )
    from duel.ai.arena import recompute_elo

    recompute_elo().publish()
    log_entry("note", title="Стадия «лечение v1» завершена", text="Итоги в матчах выше.")


def stage_search() -> None:
    """How does search depth scale? MCTS sims 50/150/400 + 2-ply minimax."""
    from duel.ai.arena import recompute_elo
    from duel.ai.bots import TwoPlyBot

    log_entry(
        "note",
        title="Стадия «поиск»: масштабирование MCTS и 2-ply",
        text="Гипотезы: (а) сила MCTS растёт с числом симуляций; (б) 2-ply minimax "
        "(учёт лучшего ответа соперника) сильнее 1-ply greedy при той же эвристике.",
    )
    ladder = Ladder()
    greedy = GreedyBot(seed=701)
    twoply = TwoPlyBot(seed=702)
    m50 = MctsBot(sims=50, seed=703, name="mcts50-heur", leaf="heuristic")
    m150 = MctsBot(sims=150, seed=704, name="mcts150-heur", leaf="heuristic")
    m400 = MctsBot(sims=400, seed=705, name="mcts400-heur", leaf="heuristic")
    run_match_and_log(ladder, twoply, greedy, 30, seed0=14_000)
    run_match_and_log(ladder, m50, greedy, 16, seed0=14_100)
    run_match_and_log(ladder, m400, m150, 12, seed0=14_200)
    run_match_and_log(ladder, m400, greedy, 12, seed0=14_300)
    run_match_and_log(ladder, m400, twoply, 12, seed0=14_400)
    run_match_and_log(ladder, m150, twoply, 16, seed0=14_500)
    recompute_elo().publish()
    log_entry("note", title="Стадия «поиск» завершена", text="Итоги в матчах выше.")


def stage_imitation() -> None:
    """Learn the value function from a STRONG teacher: mcts-heur self-play."""
    from duel.ai.arena import recompute_elo
    from duel.ai.train import generate_selfplay, train_net
    from duel.engine.encoding import encode

    games = int(sys.argv[2]) if len(sys.argv) > 2 else 260
    sims = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    log_entry(
        "note",
        title=f"Стадия «имитация»: сеть на партиях mcts{sims}-heur ({games} игр)",
        text="Гипотеза: качество данных важнее количества. Сеть, обученная на партиях "
        "сильного поискового бота, ранжирует состояния лучше, чем на партиях greedy. "
        "Проверяем и как 1-ply бот, и в листьях MCTS.",
    )
    teacher = MctsBot(sims=sims, seed=801, name="mcts-teacher", leaf="heuristic")
    x, y = generate_selfplay(teacher, n_games=games, seed0=100_000, gamma=0.985)
    log_entry("note", title="Данные готовы", text=f"{len(x)} примеров из {games} партий.")
    net = ValueNet()
    train_net(net, x, y, epochs=6, model_name="v3-imitation")
    net.save("v3")

    ladder = Ladder()
    run_match_and_log(ladder, NetBot(net, name="net-v3"), GreedyBot(seed=802), 40, seed0=15_000)
    run_match_and_log(
        ladder,
        NetBot(net, name="net-v3"),
        MctsBot(sims=150, seed=803, name="mcts150-heur", leaf="heuristic"),
        14,
        seed0=15_100,
    )

    def eval_p0(state) -> float:
        return float(net.values(encode(state, 0)[None, :])[0])

    mcts_net = MctsBot(sims=120, seed=804, name="mcts120-v3", eval_fn=eval_p0)
    run_match_and_log(ladder, mcts_net, GreedyBot(seed=805), 16, seed0=15_200)
    run_match_and_log(
        ladder,
        mcts_net,
        MctsBot(sims=150, seed=806, name="mcts150-heur", leaf="heuristic"),
        12,
        seed0=15_300,
    )
    recompute_elo().publish()
    log_entry("note", title="Стадия «имитация» завершена", text="Итоги выше.")


def stage_recipe_b() -> None:
    """Distillation control + broad-coverage value net."""
    import numpy as np

    from duel.ai.arena import recompute_elo
    from duel.ai.bots import TwoPlyBot
    from duel.ai.heuristic import evaluate as heval
    from duel.ai.train import generate_selfplay, train_net
    from duel.engine.encoding import encode
    from duel.engine.game import Game

    log_entry(
        "note",
        title="Стадия «рецепт Б»: дистилляция + широкое покрытие",
        text="Диагноз v1/v2: переобучение на узком распределении (V=0.19 на позиции с 6/7 "
        "регионов, corr с эвристикой 0.27). Контроль: сеть-дистиллят эвристики должна "
        "играть как greedy — иначе баг в конвейере. Лечение: микс random+greedy+2ply "
        "партий без дисконта, сэмпл через ход.",
    )
    # --- (a) distillation control ---
    import random as _r

    rng = _r.Random(7)
    xs, ys = [], []
    for seed in range(500):
        g = Game(seed=200_000 + seed)
        while g.winner is None:
            g.apply(rng.choice(g.legal_moves()))
            if g.winner is None and rng.random() < 0.5:
                for p in (0, 1):
                    xs.append(encode(g, p))
                    ys.append(heval(g, p))
    xd = np.stack(xs)
    yd = np.asarray(ys, dtype=np.float32)
    distill = ValueNet()
    train_net(distill, xd, yd, epochs=5, model_name="distill-control")
    distill.save("distill")
    ladder = Ladder()
    res = run_match_and_log(
        ladder, NetBot(distill, name="net-distill"), GreedyBot(seed=811), 40, seed0=16_000
    )
    verdict = (
        "конвейер чист — дело в метках"
        if res["wins_a"] >= 15
        else "ПОДОЗРЕНИЕ НА БАГ в конвейере NetBot/encode"
    )
    log_entry(
        "note",
        title=f"Дистиллят: {res['wins_a']}-{res['wins_b']} против greedy",
        text=verdict,
        mood="ok" if res["wins_a"] >= 15 else "fail",
    )

    # --- (b) broad-coverage value net ---
    x1, y1 = generate_selfplay(RandomBot(seed=812), n_games=400, seed0=210_000, sample_every=2)
    x2, y2 = generate_selfplay(
        GreedyBot(seed=813, epsilon=0.15), n_games=600, seed0=220_000, sample_every=2
    )
    x3, y3 = generate_selfplay(TwoPlyBot(seed=814), n_games=150, seed0=230_000, sample_every=2)
    x = np.concatenate([x1, x2, x3])
    y = np.concatenate([y1, y2, y3])
    log_entry(
        "note",
        title="Данные готовы",
        text=f"{len(x)} примеров: 400 random + 600 greedy + 150 2ply партий.",
    )
    net = ValueNet()
    train_net(net, x, y, epochs=6, model_name="v4-broad")
    net.save("v4")
    run_match_and_log(ladder, NetBot(net, name="net-v4"), GreedyBot(seed=815), 40, seed0=17_000)
    run_match_and_log(ladder, NetBot(net, name="net-v4"), TwoPlyBot(seed=816), 30, seed0=17_100)
    run_match_and_log(
        ladder,
        NetBot(net, name="net-v4"),
        MctsBot(sims=150, seed=817, name="mcts150-heur", leaf="heuristic"),
        14,
        seed0=17_200,
    )
    recompute_elo().publish()
    log_entry("note", title="Стадия «рецепт Б» завершена", text="Итоги выше.")


def _tune_candidate(args: tuple) -> tuple[dict, int, int]:
    """Worker: candidate weights vs default greedy and 2ply."""
    import torch as _torch

    from duel.ai.arena import play_match
    from duel.ai.bots import TwoPlyBot

    _torch.set_num_threads(1)
    weights, seed = args
    cand = GreedyBot(seed=seed, name="cand", weights=weights)
    r1 = play_match(cand, GreedyBot(seed=seed + 1), 24, seed0=seed * 37)
    r2 = play_match(cand, TwoPlyBot(seed=seed + 2), 12, seed0=seed * 41)
    wins = r1["wins_a"] + r2["wins_a"]
    total = r1["n"] + r2["n"] - r1["draws"] - r2["draws"]
    return weights, wins, total


def stage_tune() -> None:
    """Random search over heuristic weights, parallel over CPU cores."""
    import random as _r
    from concurrent.futures import ProcessPoolExecutor

    from duel.ai.heuristic import DEFAULT_WEIGHTS

    n_cand = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    workers = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    log_entry(
        "note",
        title=f"Стадия «тюнинг»: случайный поиск весов эвристики ({n_cand} кандидатов)",
        text="Гипотеза: дефолтные веса не оптимальны; лучший кандидат станет новой базой "
        "и усилит и greedy, и MCTS (через листья). Каждый кандидат: 24 игры vs greedy "
        "+ 12 vs 2ply, параллельно на пуле процессов.",
    )
    rng = _r.Random(999)
    cands = []
    for i in range(n_cand):
        w = {k: max(0.02, v * rng.uniform(0.35, 2.8)) for k, v in DEFAULT_WEIGHTS.items()}
        cands.append((w, 20_000 + i * 100))
    results = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for w, wins, total in pool.map(_tune_candidate, cands):
            results.append((wins / max(total, 1), wins, total, w))
    results.sort(reverse=True, key=lambda t: t[0])
    lines = [
        f"{r[0] * 100:.0f}% ({r[1]}/{r[2]}) — " + ", ".join(f"{k}={v:.2f}" for k, v in r[3].items())
        for r in results[:5]
    ]
    log_entry(
        "note",
        title=f"Тюнинг завершён, лучший винрейт {results[0][0] * 100:.0f}%",
        text="Топ-5:<br>" + "<br>".join(lines),
        mood="ok",
    )
    import json as _json
    from pathlib import Path

    Path("analysis/lab/best_weights.json").write_text(_json.dumps(results[0][3]))


def _amplify_chunk(args: tuple) -> tuple:
    """Worker: play games, label sampled states with MCTS root values."""
    import numpy as np
    import torch as _torch

    from duel.engine.encoding import encode
    from duel.engine.game import Game

    _torch.set_num_threads(1)
    n_games, seed0, sims, model = args[:4]
    actor_kind = args[4] if len(args) > 4 else ("net" if model else "greedy")
    import random as _r

    eval_fn = None
    if model:
        from duel.ai.value_net import ValueNet

        net = ValueNet.load(model)

        def eval_fn(state):
            return float(net.values(encode(state, 0)[None, :])[0])

    labeler = MctsBot(sims=sims, seed=seed0, leaf="heuristic", eval_fn=eval_fn)
    if actor_kind == "net" and model:
        from duel.ai.value_net import NetBot as _NetBot

        actor = _NetBot(net, name="actor", epsilon=0.12, seed=seed0 + 1)
    elif actor_kind == "2ply":
        from duel.ai.bots import TwoPlyBot as _TwoPly

        actor = _TwoPly(seed=seed0 + 1)
    else:
        actor = GreedyBot(seed=seed0 + 1, epsilon=0.15)
    _ = _r  # rng kept for future stochastic sampling
    xs, ys = [], []
    for gi in range(n_games):
        g = Game(seed=seed0 + gi)
        step = 0
        while g.winner is None and step < 600:
            g.apply(actor.choose(g))
            step += 1
            if g.winner is None and step % 2 == 0:
                v = labeler.root_value(g)
                xs.append(encode(g, 0))
                ys.append(v)
                xs.append(encode(g, 1))
                ys.append(-v)
    return np.stack(xs), np.asarray(ys, dtype=np.float32)


def stage_amplify() -> None:
    """AlphaZero-style value amplification: net learns MCTS root values."""
    import numpy as np

    from duel.ai.arena import recompute_elo
    from duel.ai.bots import TwoPlyBot
    from duel.ai.train import train_net
    from duel.engine.encoding import encode

    games = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    sims = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    base_model = sys.argv[4] if len(sys.argv) > 4 else ""
    out_name = sys.argv[5] if len(sys.argv) > 5 else "v5"
    workers = 10
    log_entry(
        "note",
        title=f"Стадия «амплификация» → {out_name}: сеть учится на оценках корня MCTS{sims}",
        text=f"Дистиллят доказал: конвейер чист, виноваты шумные метки-исходы. Теперь метка "
        f"состояния = оценка корня MCTS ({sims} симуляций) — «эвристика, улучшенная поиском». "
        f"{games} партий, состояния через ход, старт с весов дистиллята."
        + (f" Листья MCTS — сеть {base_model}." if base_model else ""),
    )
    from concurrent.futures import ProcessPoolExecutor

    mixed = len(sys.argv) > 6 and sys.argv[6] == "mixed"
    kinds = ["net", "net", "greedy", "2ply"] if mixed else [None]
    chunk = max(1, games // workers)
    jobs = []
    start = 0
    ki = 0
    while start < games:
        n = min(chunk, games - start)
        kind = kinds[ki % len(kinds)] if mixed else None
        job = (n, 300_000 + start * 10, sims, base_model)
        jobs.append((*job, kind) if kind else job)
        start += n
        ki += 1
    xs, ys = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for x, y in pool.map(_amplify_chunk, jobs):
            xs.append(x)
            ys.append(y)
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    log_entry("note", title="Данные готовы", text=f"{len(x)} примеров (метки MCTS{sims}).")
    warm = base_model or "distill"
    net = ValueNet.load(warm)
    train_net(net, x, y, epochs=4, lr=5e-4, model_name=out_name)
    net.save(out_name)

    ladder = Ladder()
    nb = NetBot(net, name=f"net-{out_name}")
    if base_model:
        prev_nb = NetBot(ValueNet.load(base_model), name=f"net-{base_model}")
        run_match_and_log(ladder, nb, prev_nb, 60, seed0=30_500)
    run_match_and_log(ladder, nb, GreedyBot(seed=941), 60, seed0=31_000)
    run_match_and_log(ladder, nb, TwoPlyBot(seed=942), 40, seed0=31_500)
    run_match_and_log(
        ladder,
        nb,
        MctsBot(sims=150, seed=943, name="mcts150-heur", leaf="heuristic"),
        16,
        seed0=32_000,
    )

    def eval_p0(state) -> float:
        return float(net.values(encode(state, 0)[None, :])[0])

    mnet = MctsBot(sims=120, seed=944, name=f"mcts120-{out_name}", eval_fn=eval_p0)
    run_match_and_log(
        ladder,
        mnet,
        MctsBot(sims=150, seed=945, name="mcts150-heur", leaf="heuristic"),
        16,
        seed0=32_500,
    )
    recompute_elo().publish()
    log_entry("note", title=f"Стадия «амплификация {out_name}» завершена", text="Итоги выше.")


def stage_final() -> None:
    """Grand final: round-robin of every notable bot, fresh ELO refit."""
    from duel.ai.arena import recompute_elo
    from duel.ai.bots import TwoPlyBot
    from duel.engine.encoding import encode

    best = sys.argv[2] if len(sys.argv) > 2 else "v6"
    log_entry(
        "note",
        title=f"ФИНАЛ: гранд-турнир (лучшая сеть: {best})",
        text="Все ключевые боты, круговой турнир, итоговый пересчёт ELO.",
    )
    net_best = ValueNet.load(best)
    net_v5 = ValueNet.load("v5")

    def eval_best(state) -> float:
        return float(net_best.values(encode(state, 0)[None, :])[0])

    ladder = Ladder()
    fast = [
        RandomBot(seed=971),
        GreedyBot(seed=972),
        TwoPlyBot(seed=973),
        NetBot(net_v5, name="net-v5"),
        NetBot(net_best, name=f"net-{best}"),
    ]
    for i, a in enumerate(fast):
        for b in fast[i + 1 :]:
            n = 20 if isinstance(a, RandomBot) or isinstance(b, RandomBot) else 50
            run_match_and_log(ladder, a, b, n, seed0=40_000 + i * 500)
    slow = [
        MctsBot(sims=150, seed=974, name="mcts150-heur", leaf="heuristic"),
        MctsBot(sims=120, seed=975, name=f"mcts120-{best}", eval_fn=eval_best),
        MctsBot(sims=300, seed=976, name=f"mcts300-{best}", eval_fn=eval_best),
    ]
    for m in slow[:2]:
        for op in (fast[1], fast[2], fast[4]):
            run_match_and_log(ladder, m, op, 16, seed0=42_000)
    run_match_and_log(ladder, slow[1], slow[0], 20, seed0=43_000)
    run_match_and_log(ladder, slow[2], slow[0], 16, seed0=43_500)
    run_match_and_log(ladder, slow[2], fast[4], 16, seed0=43_700)
    final = recompute_elo()
    final.publish()
    rows = sorted(final.ratings.items(), key=lambda kv: -kv[1])
    champion = rows[0][0]
    log_entry(
        "note",
        title=f"🏆 Чемпион ночи: {champion} ({final.ratings[champion]:.0f} ELO)",
        mood="ok",
        text="Финальная таблица выше. " + ", ".join(f"{n}: {r:.0f}" for n, r in rows[:6]),
    )


def _tactics_chunk(args: tuple) -> list[dict]:
    """Worker: champion self-play games -> per-game stat records."""
    import torch as _torch

    from duel.engine.cards import CardType
    from duel.engine.encoding import encode
    from duel.engine.game import Game

    _torch.set_num_threads(1)
    n_games, seed0, model, sims = args
    from duel.ai.value_net import ValueNet

    net = ValueNet.load(model)

    def ev(state):
        return float(net.values(encode(state, 0)[None, :])[0])

    records = []
    for gi in range(n_games):
        bot = MctsBot(sims=sims, seed=seed0 + gi, eval_fn=ev)
        g = Game(seed=seed0 + gi)
        steps = 0
        while g.winner is None and steps < 600:
            g.apply(bot.choose(g))
            steps += 1
        if g.winner is None:
            continue
        rec = {"winner": g.winner, "reason": g.win_reason, "moves": steps}
        for i, pl in enumerate(g.players):
            tag = "w" if g.winner == i else ("d" if g.winner == "draw" else "l")
            counts = {str(t): 0 for t in CardType}
            for c in pl.played:
                counts[str(c.type)] += 1
            rec[f"p{i}"] = {
                "role": tag,
                "cards": counts,
                "races": len(pl.race_counts),
                "race_list": sorted(pl.race_counts),
                "tokens": len(pl.tokens),
                "token_list": list(pl.tokens),
                "landmarks": list(pl.landmarks),
                "presence": g.presence_count(i),
                "coins": pl.coins,
                "quest": (g.quest.frodo - 14) if i == 0 else g.quest.nazgul_progress,
                "forts": g.forts_on_board(i),
            }
        records.append(rec)
    return records


def stage_tactics() -> None:
    """What does strong play look like? Champion self-play statistics."""
    from concurrent.futures import ProcessPoolExecutor

    model = sys.argv[2] if len(sys.argv) > 2 else "v8"
    games = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    sims = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    log_entry(
        "note",
        title=f"Стадия «тактика»: {games} партий чемпиона (mcts{sims}-{model}) против себя",
        text="Исходная цель проекта: понять, какая тактика сильнее. Считаем по партиям "
        "чемпиона: чем выигрывают, что драфтят победители, сколько рас/жетонов/регионов.",
    )
    jobs = [(max(1, games // 10), 500_000 + k * 1000, model, sims) for k in range(10)]
    records = []
    with ProcessPoolExecutor(max_workers=10) as pool:
        for chunk in pool.map(_tactics_chunk, jobs):
            records.extend(chunk)

    from collections import Counter

    reasons = Counter(r["reason"] for r in records)
    total = len(records)
    saur_wins = sum(1 for r in records if r["winner"] == 1)
    fell_wins = sum(1 for r in records if r["winner"] == 0)
    avg_moves = sum(r["moves"] for r in records) / total

    def side_stats(role: str) -> dict:
        picked = [r[f"p{i}"] for r in records for i in (0, 1) if r[f"p{i}"]["role"] == role]
        n = max(len(picked), 1)
        cards = Counter()
        for p in picked:
            cards.update(p["cards"])
        return {
            "races": sum(p["races"] for p in picked) / n,
            "tokens": sum(p["tokens"] for p in picked) / n,
            "presence": sum(p["presence"] for p in picked) / n,
            "quest": sum(p["quest"] for p in picked) / n,
            "forts": sum(p["forts"] for p in picked) / n,
            "cards": {k: round(v / n, 2) for k, v in cards.items()},
        }

    def detail_stats(role: str) -> tuple[Counter, Counter, Counter]:
        lms: Counter = Counter()
        races_c: Counter = Counter()
        toks: Counter = Counter()
        for r in records:
            for i in (0, 1):
                if r[f"p{i}"]["role"] == role:
                    lms.update(r[f"p{i}"].get("landmarks", []))
                    races_c.update(r[f"p{i}"].get("race_list", []))
                    toks.update(r[f"p{i}"].get("token_list", []))
        return lms, races_c, toks

    w_lm, w_races, w_toks = detail_stats("w")
    l_lm, l_races, _l_toks = detail_stats("l")
    w, lo = side_stats("w"), side_stats("l")
    lines = [
        f"Партий: {total}, средняя длина {avg_moves:.0f} ходов. "
        f"Победы: Братство {fell_wins}, Саурон {saur_wins}.",
        "Причины побед: "
        + ", ".join(f"{k}: {v} ({v / total * 100:.0f}%)" for k, v in reasons.most_common()),
        f"Победители в среднем: рас {w['races']:.1f}, жетонов {w['tokens']:.1f}, "
        f"регионов {w['presence']:.1f}, шагов Кольца {w['quest']:.1f}, крепостей {w['forts']:.1f}.",
        f"Проигравшие: рас {lo['races']:.1f}, жетонов {lo['tokens']:.1f}, "
        f"регионов {lo['presence']:.1f}, шагов Кольца {lo['quest']:.1f}, "
        f"крепостей {lo['forts']:.1f}.",
        f"Карты победителей (в среднем): {w['cards']}",
        f"Карты проигравших: {lo['cards']}",
        "Тайлы победителей: " + ", ".join(f"{k}×{v}" for k, v in w_lm.most_common()),
        "Тайлы проигравших: " + ", ".join(f"{k}×{v}" for k, v in l_lm.most_common()),
        "Расы победителей: " + ", ".join(f"{k}×{v}" for k, v in w_races.most_common()),
        "Расы проигравших: " + ", ".join(f"{k}×{v}" for k, v in l_races.most_common()),
        "Жетоны победителей: " + ", ".join(f"{k}×{v}" for k, v in w_toks.most_common(8)),
    ]
    import json as _json
    from pathlib import Path

    Path("analysis/lab/tactics.json").write_text(
        _json.dumps(records, ensure_ascii=False), encoding="utf-8"
    )
    log_entry("note", title="Тактика сильной игры — статистика", mood="ok", text="<br>".join(lines))


STAGES = {
    "stage1": stage1,
    "stage2": stage2,
    "stage3": stage3,
    "mcts_net": stage_mcts_net,
    "stage4": stage4,
    "fixes": stage_fixes,
    "search": stage_search,
    "imitation": stage_imitation,
    "recipe_b": stage_recipe_b,
    "tune": stage_tune,
    "amplify": stage_amplify,
    "final": stage_final,
    "tactics": stage_tactics,
}

if __name__ == "__main__":
    STAGES[sys.argv[1]]()
