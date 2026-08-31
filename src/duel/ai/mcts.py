"""Monte-Carlo tree search bot (UCT).

Values are scalars from player 0's perspective (+1 = Fellowship wins);
selection at each node maximizes from the node's current player's view.
Handles extra turns naturally (consecutive moves by the same player).

`leaf_eval`: "rollout" (random playout, capped) or a callable
(game -> value from p0's perspective) e.g. heuristic or a value net.
"""

import math
import random

from duel.ai.bots import Bot
from duel.ai.heuristic import evaluate
from duel.engine.game import Game, move_key


def _terminal_value(game: Game) -> float:
    if game.winner == "draw":
        return 0.0
    return 1.0 if game.winner == 0 else -1.0


class _Node:
    __slots__ = ("children", "moves", "n", "state", "untried", "w")

    def __init__(self, state: Game):
        self.state = state
        self.moves = state.legal_moves()
        self.untried = list(range(len(self.moves)))
        self.children: dict[int, _Node] = {}
        self.n = 0
        self.w = 0.0  # total value from p0 perspective


class MctsBot(Bot):
    def __init__(
        self,
        sims: int = 200,
        c: float = 1.0,
        seed: int = 0,
        name: str = "mcts",
        leaf: str = "rollout",
        rollout_depth: int = 60,
        eval_fn=None,
        reuse: bool = False,
    ):
        self.sims = sims
        self.c = c
        self.rng = random.Random(seed)
        self.name = name
        self.leaf = leaf
        self.rollout_depth = rollout_depth
        self.eval_fn = eval_fn
        self.reuse = reuse
        self._root: _Node | None = None
        self._root_hist: tuple | None = None
        self.reused_visits = 0  # диагностика: визиты, принесённые переносом дерева

    def new_game(self) -> None:
        self._root = None
        self._root_hist = None

    def _take_root(self, game: Game):
        """Перенос дерева между ходами (SP-7, по образцу IsmctsBot._take_root):
        спускаемся из прежнего корня по ходам из game.history; если путь
        совпал — поддерево со всей статистикой становится новым корнем."""
        if self._root is None or self._root_hist is None:
            return None
        h = game.history
        rh = self._root_hist
        if len(h) < len(rh) or h[: len(rh)] != rh:
            return None
        node = self._root
        for k in h[len(rh):]:
            nxt = None
            for idx, ch in node.children.items():
                if move_key(node.moves[idx]) == k:
                    nxt = ch
                    break
            if nxt is None:
                return None
            node = nxt
        return node

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        if len(moves) == 1:
            self.last_visits = None
            return moves[0]
        root = self._take_root(game) if self.reuse else None
        if root is None:
            root = _Node(game.clone())
        self.reused_visits = root.n
        for _ in range(self.sims):
            self._simulate(root)
        if self.reuse:
            self._root = root
            self._root_hist = game.history
        visits = [root.children[i].n if i in root.children else 0 for i in range(len(root.moves))]
        self.last_visits = (root.moves, visits)
        self.last_root_value = root.w / max(root.n, 1)
        best = max(root.children.items(), key=lambda kv: kv[1].n)
        return root.moves[best[0]]

    def _simulate(self, node: _Node) -> float:
        path: list[tuple[_Node, int]] = []
        # --- selection ---
        while node.state.winner is None:
            if node.untried:
                idx = node.untried.pop(self.rng.randrange(len(node.untried)))
                child_state = node.state.clone()
                child_state.apply(node.moves[idx])
                child = _Node(child_state)
                node.children[idx] = child
                path.append((node, idx))
                node = child
                value = self._leaf_value(child.state)
                break
            sign = 1.0 if node.state.current == 0 else -1.0
            logn = math.log(node.n + 1)
            best_idx, best_u = -1, -1e18
            for idx, ch in node.children.items():
                u = sign * ch.w / (ch.n + 1e-9) + self.c * math.sqrt(logn / (ch.n + 1e-9))
                if u > best_u:
                    best_idx, best_u = idx, u
            path.append((node, best_idx))
            node = node.children[best_idx]
        else:
            value = _terminal_value(node.state)
        # --- backprop ---
        node.n += 1
        node.w += value
        for parent, _idx in path:
            parent.n += 1
            parent.w += value
        return value

    def choose_pimc(self, game: Game, worlds: int = 8) -> dict:
        """Honest search: Perfect Information Monte Carlo over sampled worlds.

        Root legal moves depend only on public info, so action stats
        aggregate across determinizations of the hidden state.
        """
        moves = game.legal_moves()
        if len(moves) == 1:
            return moves[0]
        # (сброс теперь только из проданных карт — он публичен, миры всегда
        # согласны, особый фолбэк для play_from_discard больше не нужен)
        totals = [0] * len(moves)
        per_world = max(1, self.sims // worlds)
        viewer = game.pending[0]["player"] if game.pending else game.current
        for _wi in range(worlds):
            g = game.clone()
            g.randomize_hidden(random.Random(self.rng.getrandbits(64)), viewer=viewer)
            root = _Node(g)
            saved, self.sims = self.sims, per_world
            for _ in range(per_world):
                self._simulate(root)
            self.sims = saved
            for i in range(len(moves)):
                if i in root.children:
                    totals[i] += root.children[i].n
        return moves[max(range(len(moves)), key=lambda i: totals[i])]

    def root_value(self, game: Game) -> float:
        """Run sims from this state and return the root's mean value (p0 view)."""
        root = _Node(game.clone())
        if not root.moves:
            return _terminal_value(game)
        for _ in range(self.sims):
            self._simulate(root)
        return root.w / max(root.n, 1)

    def _leaf_value(self, state: Game) -> float:
        if state.winner is not None:
            return _terminal_value(state)
        if callable(self.eval_fn):
            return self.eval_fn(state)
        if self.leaf == "heuristic":
            return evaluate(state, 0)
        # random rollout
        g = state.clone()
        for _ in range(self.rollout_depth):
            if g.winner is not None:
                break
            g.apply(self.rng.choice(g.legal_moves()))
        if g.winner is not None:
            return _terminal_value(g)
        return evaluate(g, 0)


class HonestMctsBot(MctsBot):
    """MCTS that never peeks at hidden information (PIMC over sampled worlds)."""

    def __init__(self, *args, worlds: int = 8, **kwargs):
        super().__init__(*args, **kwargs)
        self.worlds = worlds

    def choose(self, game: Game) -> dict:
        return self.choose_pimc(game, worlds=self.worlds)


_move_key = move_key  # тот же ключ, что пишет Game.history — нужен для переноса дерева


class _IsNode:
    """Узел общего дерева ISMCTS: дети по ключу хода, статистика делится между
    всеми мирами; `avail` — сколько раз ход был легален при проходе через узел."""

    __slots__ = ("children", "n", "w", "avail")

    def __init__(self):
        self.children: dict[tuple, _IsNode] = {}
        self.n = 0
        self.w = 0.0
        self.avail: dict[tuple, int] = {}


class IsmctsBot(MctsBot):
    """Честный поиск с ОДНИМ деревом (single-observer ISMCTS): на каждую симуляцию
    сэмплируется новый мир (скрытое пересэмплируется, своя рука известна), и
    симуляция идёт по общему дереву, применяя ходы к состоянию этого мира.
    В отличие от PIMC (K независимых деревьев по sims/K), вся глубина
    достаётся каждой симуляции, а статистика ходов копится через миры."""

    def __init__(self, *args, reuse: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.reuse = reuse
        self._root: _IsNode | None = None
        self._root_hist: tuple | None = None
        self.reused_visits = 0  # диагностика: сколько визитов принёс перенос дерева

    def new_game(self) -> None:
        self._root = None
        self._root_hist = None

    def _take_root(self, game: Game) -> _IsNode:
        """Перенос дерева: спускаемся из прежнего корня по ходам, применённым с
        тех пор (game.history); если путь есть — поддерево со всей статистикой
        становится корнем. У PIMC такого нет: его деревья одноразовые."""
        node = None
        if self.reuse and self._root is not None and self._root_hist is not None:
            h = game.history
            if len(h) >= len(self._root_hist) and h[: len(self._root_hist)] == self._root_hist:
                node = self._root
                for k in h[len(self._root_hist):]:
                    node = node.children.get(k)
                    if node is None:
                        break
        if node is None:
            node = _IsNode()
        self.reused_visits = node.n
        self._root = node
        self._root_hist = game.history
        return node

    def choose(self, game: Game) -> dict:
        moves = game.legal_moves()
        if len(moves) == 1:
            return moves[0]
        viewer = game.pending[0]["player"] if game.pending else game.current
        root = self._take_root(game)
        for _ in range(self.sims):
            g = game.clone()
            g.randomize_hidden(random.Random(self.rng.getrandbits(64)), viewer=viewer)
            self._simulate_is(root, g)
        keys = [_move_key(m) for m in moves]
        best = max(range(len(moves)), key=lambda i: root.children[keys[i]].n if keys[i] in root.children else -1)
        return moves[best]

    def _simulate_is(self, root: _IsNode, g: Game) -> float:
        path: list[_IsNode] = [root]
        node = root
        while g.winner is None:
            legal = g.legal_moves()
            if not legal:
                break
            keys = [_move_key(m) for m in legal]
            for k in keys:
                node.avail[k] = node.avail.get(k, 0) + 1
            untried = [i for i, k in enumerate(keys) if k not in node.children]
            if untried:
                i = untried[self.rng.randrange(len(untried))]
                g.apply(legal[i])
                child = _IsNode()
                node.children[keys[i]] = child
                path.append(child)
                value = self._leaf_value(g)
                break
            actor = g.pending[0]["player"] if g.pending else g.current
            sign = 1.0 if actor == 0 else -1.0
            best_i, best_u = 0, -1e18
            for i, k in enumerate(keys):
                ch = node.children[k]
                u = sign * ch.w / (ch.n + 1e-9) + self.c * math.sqrt(math.log(node.avail[k] + 1) / (ch.n + 1e-9))
                if u > best_u:
                    best_i, best_u = i, u
            g.apply(legal[best_i])
            node = node.children[keys[best_i]]
            path.append(node)
        else:
            value = _terminal_value(g)
        if g.winner is None and "value" not in locals():
            value = self._leaf_value(g)
        for nd in path:
            nd.n += 1
            nd.w += value
        return value
