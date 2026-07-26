"""Full-telemetry game recorder for exploratory data analysis.

Records every move (who, what, cost, chain), per-turn state snapshots
(coins, presence, races, quest, supply, board), optional value-net
evaluation of every position, and the final outcome. Games are written as
JSONL shards (one game per line) under analysis/lab/data/.

Bot specs are picklable strings so recording parallelizes over processes:
  "random" | "greedy" | "greedy:0.1" (epsilon) | "2ply"
  | "mcts150-heur" | "mctsN-MODEL" (net leaves, e.g. "mcts120-v8")
  | "net-MODEL"
"""

import gzip
import json
import time
from pathlib import Path

from duel.engine.cards import CardType
from duel.engine.game import REGION_KEYS, Game
from duel.engine.landmarks import BY_ID as LM_BY_ID

DATA = Path(__file__).resolve().parents[3] / "analysis" / "lab" / "data"


def make_bot(spec: str, seed: int):
    import re

    if spec == "random":
        from duel.ai.bots import RandomBot

        return RandomBot(seed=seed)
    if spec.startswith("greedy"):
        from duel.ai.bots import GreedyBot

        eps = float(spec.split(":")[1]) if ":" in spec else 0.0
        return GreedyBot(seed=seed, epsilon=eps)
    if spec == "2ply":
        from duel.ai.bots import TwoPlyBot

        return TwoPlyBot(seed=seed)
    if spec == "mcts150-heur":
        from duel.ai.mcts import MctsBot

        return MctsBot(sims=150, seed=seed, leaf="heuristic")
    if m := re.fullmatch(r"mcts(\d+)-(\w+)", spec):
        from duel.ai.mcts import MctsBot
        from duel.ai.value_net import ValueNet
        from duel.engine.encoding import encode

        net = ValueNet.load(m.group(2))

        def ev(state):
            return float(net.values(encode(state, 0)[None, :])[0])

        return MctsBot(sims=int(m.group(1)), seed=seed, eval_fn=ev)
    if spec.startswith("net-"):
        from duel.ai.value_net import NetBot, ValueNet

        return NetBot(ValueNet.load(spec[4:]), name=spec, seed=seed)
    raise ValueError(f"unknown bot spec {spec}")


def _move_record(g: Game, move: dict, actor: int) -> dict:
    rec = {"p": actor, "t": move.get("type"), "turn": g.turn_no, "ch": g.chapter}
    if move.get("type") in ("play", "discard"):
        card = g.tableau.cards.get(move["slot"])
        if card:
            rec["card"] = card.id
            rec["ctype"] = str(card.type)
    if move.get("type") == "play":
        cost = g.card_cost(actor, g.tableau.cards[move["slot"]])
        rec["paid"] = cost["coins"]
        rec["chain"] = cost["chained"]
    if move.get("type") == "tile":
        rec["tile"] = move["tile"]
        rec["paid"] = g.tile_cost(actor, LM_BY_ID[move["tile"]])["coins"]
    if move.get("type") == "pick_token":
        rec["token"] = move["token"]
    if move.get("type") in ("place", "kill", "raze"):
        rec["region"] = move.get("region")
    if move.get("type") == "move":
        rec["from"] = move.get("from")
        rec["to"] = move.get("to")
    return rec


def _snapshot(g: Game) -> dict:
    return {
        "turn": g.turn_no,
        "ch": g.chapter,
        "coins": [g.players[0].coins, g.players[1].coins],
        "presence": [g.presence_count(0), g.presence_count(1)],
        "races": [g.players[0].race_symbols_for_victory(), g.players[1].race_symbols_for_victory()],
        "quest": [g.quest.frodo - 14, g.quest.nazgul_progress],
        "gap": g.quest.gap,
        "supply": [g.supply(0), g.supply(1)],
        "units": {r: list(g.board_units[r]) for r in REGION_KEYS if any(g.board_units[r])},
        "forts": {r: list(g.board_forts[r]) for r in REGION_KEYS if any(g.board_forts[r])},
        "reserve": g.reserve,
    }


def record_chunk(args: tuple) -> str:
    """Worker: play n games, write one gzipped JSONL shard, return its path."""
    (spec_a, spec_b, n_games, seed0, rules, eval_model, out_name) = args
    import torch

    torch.set_num_threads(1)
    net = None
    if eval_model:
        from duel.ai.value_net import ValueNet
        from duel.engine.encoding import encode as _enc

        net = ValueNet.load(eval_model)

    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / f"{out_name}.jsonl.gz"
    t0 = time.time()
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for gi in range(n_games):
            seed = seed0 + gi
            bots = {0: make_bot(spec_a, seed * 2 + 1), 1: make_bot(spec_b, seed * 2 + 2)}
            g = Game(seed=seed, rules=rules)
            moves, snaps, values = [], [], []
            steps = 0
            while g.winner is None and steps < 600:
                actor = g.current
                move = bots[actor].choose(g)
                moves.append(_move_record(g, move, actor))
                g.apply(move)
                steps += 1
                if not g.pending:  # snapshot at clean turn boundaries
                    snaps.append(_snapshot(g))
                    if net is not None:
                        values.append(round(float(net.values(_enc(g, 0)[None, :])[0]), 4))
            final = {
                "seed": seed,
                "bots": [spec_a, spec_b],
                "rules": {k: v for k, v in g.rules.items()},
                "winner": g.winner,
                "reason": g.win_reason,
                "moves_n": steps,
                "moves": moves,
                "snaps": snaps,
                "values": values,
                "final": _snapshot(g),
                "played": [
                    [c.id for c in g.players[0].played],
                    [c.id for c in g.players[1].played],
                ],
                "tokens": [list(g.players[0].tokens), list(g.players[1].tokens)],
                "landmarks": [list(g.players[0].landmarks), list(g.players[1].landmarks)],
                "grey_types": [
                    sum(1 for c in g.players[0].played if c.type is CardType.GREY),
                    sum(1 for c in g.players[1].played if c.type is CardType.GREY),
                ],
            }
            f.write(json.dumps(final, ensure_ascii=False, default=str) + "\n")
    return f"{path.name}: {n_games} games in {time.time() - t0:.0f}s"


def collect(
    name: str,
    spec_a: str,
    spec_b: str,
    n_games: int,
    seed0: int = 0,
    rules: dict | None = None,
    eval_model: str | None = None,
    workers: int = 10,
) -> None:
    from concurrent.futures import ProcessPoolExecutor

    chunk = max(1, n_games // workers)
    jobs = []
    start = 0
    k = 0
    while start < n_games:
        n = min(chunk, n_games - start)
        jobs.append((spec_a, spec_b, n, seed0 + start, rules, eval_model, f"{name}_{k:02d}"))
        start += n
        k += 1
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for msg in pool.map(record_chunk, jobs):
            print(msg, flush=True)


if __name__ == "__main__":
    import sys

    # collect <name> <specA> <specB> <n> [seed0] [eval_model] [rules_json]
    name, a, b, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    seed0 = int(sys.argv[5]) if len(sys.argv) > 5 else 0
    eval_model = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] != "-" else None
    rules = json.loads(sys.argv[7]) if len(sys.argv) > 7 else None
    collect(name, a, b, n, seed0=seed0, rules=rules, eval_model=eval_model)
