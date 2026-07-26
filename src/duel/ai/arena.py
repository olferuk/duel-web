"""Arena: matches between bots, ELO ladder, persistence."""

import json
import time

from duel.ai.bots import Bot
from duel.ai.journal import LAB, log_entry
from duel.engine.game import Game

ELO_FILE = LAB / "elo.json"
K = 24
MAX_MOVES = 600


def play_game(bot0: Bot, bot1: Bot, seed: int) -> int | str:
    """bot0 plays Fellowship (player 0), bot1 plays Sauron. Returns winner."""
    g = Game(seed=seed)
    bots = {0: bot0, 1: bot1}
    bot0.new_game()
    bot1.new_game()
    for _ in range(MAX_MOVES):
        if g.winner is not None:
            return g.winner
        actor = g.pending[0]["player"] if g.pending else g.current
        move = bots[actor].choose(g)
        g.apply(move)
    return "draw"


def play_match(a: Bot, b: Bot, n: int, seed0: int = 0) -> dict:
    """n games, colors alternate. Returns wins from a's perspective."""
    wins_a = wins_b = draws = 0
    t0 = time.perf_counter()
    for i in range(n):
        seed = seed0 + i
        if i % 2 == 0:
            w = play_game(a, b, seed)
            if w == 0:
                wins_a += 1
            elif w == 1:
                wins_b += 1
            else:
                draws += 1
        else:
            w = play_game(b, a, seed)
            if w == 0:
                wins_b += 1
            elif w == 1:
                wins_a += 1
            else:
                draws += 1
    secs = round(time.perf_counter() - t0, 1)
    return {"wins_a": wins_a, "wins_b": wins_b, "draws": draws, "n": n, "secs": secs}


class Ladder:
    def __init__(self) -> None:
        self.ratings: dict[str, float] = {}
        self.games: dict[str, int] = {}
        if ELO_FILE.exists():
            data = json.loads(ELO_FILE.read_text())
            self.ratings = data["ratings"]
            self.games = data["games"]

    def rating(self, name: str) -> float:
        return self.ratings.setdefault(name, 1000.0)

    def _update_pair(self, a: str, b: str, score_a: float) -> None:
        ra, rb = self.rating(a), self.rating(b)
        ea = 1 / (1 + 10 ** ((rb - ra) / 400))
        self.ratings[a] = ra + K * (score_a - ea)
        self.ratings[b] = rb + K * ((1 - score_a) - (1 - ea))
        self.games[a] = self.games.get(a, 0) + 1
        self.games[b] = self.games.get(b, 0) + 1

    def record_match(self, a: Bot, b: Bot, result: dict) -> None:
        for _ in range(result["wins_a"]):
            self._update_pair(a.name, b.name, 1.0)
        for _ in range(result["wins_b"]):
            self._update_pair(a.name, b.name, 0.0)
        for _ in range(result["draws"]):
            self._update_pair(a.name, b.name, 0.5)
        self.save()

    def save(self) -> None:
        LAB.mkdir(parents=True, exist_ok=True)
        ELO_FILE.write_text(
            json.dumps({"ratings": self.ratings, "games": self.games}, ensure_ascii=False)
        )

    def publish(self) -> None:
        log_entry(
            "elo", ratings={k: round(v, 1) for k, v in self.ratings.items()}, games=self.games
        )


def run_match_and_log(ladder: Ladder, a: Bot, b: Bot, n: int, seed0: int = 0) -> dict:
    res = play_match(a, b, n, seed0)
    ladder.record_match(a, b, res)
    log_entry("match", a=a.name, b=b.name, **res)
    return res


def recompute_elo(passes: int = 30) -> Ladder:
    """Re-fit ratings from the full match history in the journal.

    Sequential ELO underrates late arrivals; iterating over all games
    several times with decreasing K converges to a stable estimate.
    """
    import random as _random

    from duel.ai.journal import read_journal

    games: list[tuple[str, str, float]] = []
    for e in read_journal():
        if e["kind"] != "match":
            continue
        games += [(e["a"], e["b"], 1.0)] * e["wins_a"]
        games += [(e["a"], e["b"], 0.0)] * e["wins_b"]
        games += [(e["a"], e["b"], 0.5)] * e.get("draws", 0)
    ladder = Ladder.__new__(Ladder)
    ladder.ratings = {}
    ladder.games = {}
    rng = _random.Random(0)
    for i in range(passes):
        order = list(games)
        rng.shuffle(order)
        k = max(4.0, 32.0 * (1 - i / passes))
        for a, b, score in order:
            ra, rb = ladder.rating(a), ladder.rating(b)
            ea = 1 / (1 + 10 ** ((rb - ra) / 400))
            ladder.ratings[a] = ra + k * (score - ea)
            ladder.ratings[b] = rb + k * ((1 - score) - (1 - ea))
    counts: dict[str, int] = {}
    for a, b, _s in games:
        counts[a] = counts.get(a, 0) + 1
        counts[b] = counts.get(b, 0) + 1
    ladder.games = counts
    ladder.save()
    return ladder
