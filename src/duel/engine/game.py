"""Full game engine: turns, costs, effects, conflicts, alliances, victories.

Players: index 0 = Fellowship, 1 = Sauron. Sauron takes the first turn.

Moves are plain dicts (JSON-friendly). `legal_moves()` enumerates everything
the current player may do; `apply()` executes one move. Effects that require
a decision are queued in `self.pending`; while the queue is non-empty, legal
moves come from its head. When the queue drains, the turn ends (extra-turn
effects keep the same player).

Deliberate simplifications (flagged for later review):
- Payment is auto-optimized: skills cover as much of the cost as possible,
  the rest is paid in coins (there is no strategic reason to overpay).
- The "3 different races" alliance triggers automatically on reaching 3.
- Grond: the attacker chooses the retreat region for enemy units.
"""

import random
from dataclasses import dataclass, field
from itertools import product

from duel.engine.alliances import BY_ID as TOKEN_BY_ID
from duel.engine.board import EDGES, REGIONS
from duel.engine.cards import Card, CardType, card_to_dict
from duel.engine.landmarks import BY_ID as LM_BY_ID
from duel.engine.landmarks import LANDMARKS, Landmark, landmark_to_dict
from duel.engine.quest import QuestState, Space
from duel.engine.tableau import Tableau

REGION_KEYS: list[str] = [r["key"] for r in REGIONS]
REGION_RU: dict[str, str] = {r["key"]: r["name"] for r in REGIONS}
ADJ: dict[str, set[str]] = {k: set() for k in REGION_KEYS}
for _a, _b in EDGES:
    ADJ[_a].add(_b)
    ADJ[_b].add(_a)

FELLOWSHIP, SAURON = 0, 1
SIDE_RU = ["Братство", "Саурон"]
UNITS_SUPPLY = 15
RACES = ["elves", "ents", "hobbits", "humans", "dwarves", "wizards"]
RACE_RU = {
    "elves": "Эльфы",
    "ents": "Энты",
    "hobbits": "Хоббиты",
    "humans": "Люди",
    "dwarves": "Гномы",
    "wizards": "Волшебники",
}
SKILL_RU = {
    "Face": "Хитрость",
    "Fist": "Сила",
    "Heart": "Отвага",
    "Crown": "Лидерство",
    "Book": "Знание",
}


@dataclass
class Player:
    coins: int = 0
    played: list[Card] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    landmarks: list[str] = field(default_factory=list)
    used_three_diff: bool = False
    _agg: dict | None = field(default=None, repr=False, compare=False)

    def _aggregates(self) -> dict:
        """Cached per-card aggregates; rebuilt only after add/remove_card."""
        if self._agg is None:
            links: set[str] = set()
            races: dict[str, int] = {}
            fixed: dict[str, int] = {}
            groups: list[tuple[str, ...]] = []
            grey = 0
            skill_syms = 0.0
            for c in self.played:
                if c.gives_link:
                    links.add(c.gives_link)
                if c.race:
                    races[c.race] = races.get(c.race, 0) + 1
                for s in c.skills:
                    fixed[s] = fixed.get(s, 0) + 1
                if c.skills_choice:
                    groups.append(c.skills_choice)
                if c.type is CardType.GREY:
                    grey += 1
                    skill_syms += len(c.skills) + len(c.skills_choice) * 0.7
            self._agg = {
                "links": links,
                "races": races,
                "fixed": fixed,
                "groups": groups,
                "grey": grey,
                "skill_syms": skill_syms,
            }
        return self._agg

    def add_card(self, card: Card) -> None:
        self.played.append(card)
        self._agg = None

    def remove_card(self, index: int) -> Card:
        card = self.played.pop(index)
        self._agg = None
        return card

    @property
    def links(self) -> set[str]:
        return self._aggregates()["links"]

    @property
    def race_counts(self) -> dict[str, int]:
        return self._aggregates()["races"]

    def race_symbols_for_victory(self) -> int:
        n = len(self._aggregates()["races"])
        if "hobbits_eagle" in self.tokens:
            n += 1
        return n

    def skill_pool(self) -> tuple[dict[str, int], list[tuple[str, ...]], int]:
        """(fixed counts, choice groups, wild count) available per turn."""
        agg = self._aggregates()
        wilds = 1 if "elves_wild_skill" in self.tokens else 0
        return agg["fixed"], agg["groups"], wilds


def missing_skills(required: tuple[str, ...], player: Player) -> int:
    """How many required symbols cannot be covered by the player's skills.

    Results are memoized on the player's aggregate snapshot: identical
    queries repeat massively across search clones sharing card sets.
    """
    agg = player._aggregates()
    fixed, groups = agg["fixed"], agg["groups"]
    wilds = 1 if "elves_wild_skill" in player.tokens else 0
    cache = agg.setdefault("miss_cache", {})
    key = (required, wilds)
    hit = cache.get(key)
    if hit is not None:
        return hit
    result = _missing_skills_calc(required, fixed, groups, wilds)
    cache[key] = result
    return result


def _missing_skills_calc(required, fixed, groups, wilds) -> int:
    need: dict[str, int] = {}
    for s in required:
        need[s] = need.get(s, 0) + 1
    deficit: dict[str, int] = {}
    for s, n in need.items():
        short = n - min(n, fixed.get(s, 0))
        if short:
            deficit[s] = short
    if not deficit:
        return 0
    best = sum(deficit.values())
    options = [(*g, None) for g in groups]
    for combo in product(*options) if options else [()]:
        d = dict(deficit)
        for pick in combo:
            if pick is not None and d.get(pick, 0) > 0:
                d[pick] -= 1
        rest = sum(d.values())
        best = min(best, max(0, rest - wilds))
    return best


class _NullLog(list):
    """Log sink for search clones: append is a no-op."""

    def append(self, item) -> None:
        pass

    def extend(self, items) -> None:
        pass


DEFAULT_RULES = {
    "start_coins": (3, 2),  # (fellowship, sauron)
    "discard_payout": (1, 2, 3),  # coins per discard in chapters 1/2/3
    "first_player": SAURON,
    # Соло-вариант (автома): {"side": 0|1, "powers": [...]} или None.
    # Автома берёт карты бесплатно (без навыков, цепочек и монет), никогда не
    # сбрасывает карты ради монет, а ориентиры покупает за 7/5/2 монеты
    # (+1 за каждую свою крепость). "powers" — силы персонажа (automa.py).
    "automa": None,
}

# базовая цена ориентира для автомы по эпохам (соло-вариант, стр. 2)
AUTOMA_TILE_BASE = (7, 5, 2)


class Game:
    def __init__(
        self, seed: int | None = None, promo: bool = False, rules: dict | None = None
    ) -> None:
        self.rules = {**DEFAULT_RULES, **(rules or {})}
        self.rng = random.Random(seed)
        c0, c1 = self.rules["start_coins"]
        self.players = [Player(coins=c0), Player(coins=c1)]
        self.reserve = 30 - c0 - c1
        self.board_units: dict[str, list[int]] = {k: [0, 0] for k in REGION_KEYS}
        self.board_forts: dict[str, list[int]] = {k: [0, 0] for k in REGION_KEYS}
        self.board_units["arnor"][FELLOWSHIP] = 2
        self.board_units["mordor"][SAURON] = 2
        self.quest = QuestState()
        self.chapter = 1
        self.tableau = Tableau(1, seed=self.rng.randrange(1 << 30))
        # facedown pile (3 unseen cards per chapter) vs public pile (sold/stripped)
        self.discard_hidden: list[Card] = list(self.tableau.discarded)
        self.discard_open: list[Card] = []
        base = [lm.id for lm in LANDMARKS if not lm.promo]
        self.rng.shuffle(base)
        self.landmarks_faceup = base[:3]
        deck = base[3:]
        if promo:
            deck += [lm.id for lm in LANDMARKS if lm.promo]
            self.rng.shuffle(deck)
        self.landmarks_deck = deck
        self.alliance_stacks: dict[str, list[str]] = {}
        for race in RACES:
            ids = [t.id for t in TOKEN_BY_ID.values() if t.race == race]
            self.rng.shuffle(ids)
            self.alliance_stacks[race] = ids
        self.current = self.rules["first_player"]
        self.extra_turns = 0
        # предложения доп. хода с трека: спрашиваем ТОЛЬКО когда всё остальное хода отыграно
        self.extra_offers: list[int] = []
        self.pending: list[dict] = []
        self.turn_no = 1
        self.last_action: list[str | None] = [None, None]
        self.winner: int | str | None = None  # 0 | 1 | "draw"
        self.win_reason: str | None = None
        self.promo = promo
        # режим партии — первой строкой лога: «а стояла ли галочка промо?»
        # должно быть видно и через час после старта
        self.log: list[str] = [
            "Партия началась. Ходит Саурон." + (" Промо-тайлы: вкл." if promo else "")
        ]

    # ---------- fast copy for search ----------

    def clone(self) -> "Game":
        """Cheap copy: immutable data shared, mutable containers duplicated.

        The clone's log is a no-op sink, so search rollouts don't burn time
        building strings nobody reads.
        """
        g = object.__new__(Game)
        g.rng = random.Random.__new__(random.Random)
        g.rng.setstate(self.rng.getstate())
        g.players = [
            Player(
                coins=pl.coins,
                played=list(pl.played),
                tokens=list(pl.tokens),
                landmarks=list(pl.landmarks),
                used_three_diff=pl.used_three_diff,
            )
            for pl in self.players
        ]
        g.reserve = self.reserve
        g.board_units = {k: list(v) for k, v in self.board_units.items()}
        g.board_forts = {k: list(v) for k, v in self.board_forts.items()}
        g.quest = QuestState(
            frodo=self.quest.frodo,
            nazgul_progress=self.quest.nazgul_progress,
            winner=self.quest.winner,
            log=_NullLog(),
        )
        g.rules = self.rules
        g.chapter = self.chapter
        g.tableau = self.tableau.clone()
        g.discard_hidden = list(self.discard_hidden)
        g.discard_open = list(self.discard_open)
        g.landmarks_faceup = list(self.landmarks_faceup)
        g.landmarks_deck = list(self.landmarks_deck)
        g.alliance_stacks = {r: list(s) for r, s in self.alliance_stacks.items()}
        g.current = self.current
        g.turn_no = self.turn_no
        g.last_action = list(self.last_action)
        g.extra_turns = self.extra_turns
        g.extra_offers = list(self.extra_offers)
        g.pending = [dict(pd) for pd in self.pending]
        g.winner = self.winner
        g.win_reason = self.win_reason
        g.promo = self.promo
        g.log = _NullLog()
        return g

    def randomize_hidden(self, rng: random.Random) -> None:
        """Resample everything hidden from BOTH players — for honest search.

        Unknowns: identities of facedown unrevealed tableau cards and of the
        hidden discard (interchangeable pool), the order inside alliance
        stacks, and all future shuffles (via reseeding our RNG). Public info
        is untouched.
        """
        tab = self.tableau
        hidden_slots = [
            s.id for s in tab.slots if s.id not in tab.taken and s.id not in tab.revealed
        ]
        pool = [tab.cards[i] for i in hidden_slots] + list(self.discard_hidden)
        rng.shuffle(pool)
        tab.cards = dict(tab.cards)  # unshare from clone siblings before mutating
        for i in hidden_slots:
            tab.cards[i] = pool.pop()
        self.discard_hidden = pool
        for stack in self.alliance_stacks.values():
            rng.shuffle(stack)
        self.rng = random.Random(rng.getrandbits(64))

    # ---------- helpers ----------

    def units_on_board(self, p: int) -> int:
        return sum(u[p] for u in self.board_units.values())

    def supply(self, p: int) -> int:
        return UNITS_SUPPLY - self.units_on_board(p)

    def forts_on_board(self, p: int) -> int:
        return sum(f[p] for f in self.board_forts.values())

    def present(self, p: int, region: str) -> bool:
        return self.board_units[region][p] > 0 or self.board_forts[region][p] > 0

    def presence_count(self, p: int) -> int:
        return sum(self.present(p, r) for r in REGION_KEYS)

    def _gain_coins(self, p: int, n: int) -> int:
        n = min(n, self.reserve)
        self.players[p].coins += n
        self.reserve -= n
        return n

    def _pay_coins(self, p: int, n: int) -> None:
        assert self.players[p].coins >= n
        self.players[p].coins -= n
        self.reserve += n

    def _check_conquer(self) -> None:
        if self.winner is not None:
            return
        for p in (0, 1):
            if self.presence_count(p) == 7:
                self.winner = p
                self.win_reason = "conquest"
                self.log.append(f"⚔️ {SIDE_RU[p]} покоряет Средиземье — победа!")

    def _check_races(self, p: int) -> None:
        if self.winner is None and self.players[p].race_symbols_for_victory() >= 6:
            self.winner = p
            self.win_reason = "races"
            self.log.append(f"🤝 {SIDE_RU[p]} заручился поддержкой 6 рас — победа!")

    def _place_units(self, p: int, region: str, n: int) -> None:
        if n > 0 and self.supply(p) == 0:
            self.log.append(f"{SIDE_RU[p]}: запас юнитов пуст — размещение пропущено")
        n = min(n, self.supply(p))
        if n <= 0:
            return
        self.board_units[region][p] += n
        self.log.append(f"{SIDE_RU[p]}: +{n} юнит(ов) в {REGION_RU[region]}")
        self._resolve_conflict(region)
        self._check_conquer()

    def _resolve_conflict(self, region: str) -> None:
        u = self.board_units[region]
        if u[0] > 0 and u[1] > 0:
            k = min(u[0], u[1])
            u[0] -= k
            u[1] -= k
            self.log.append(f"Конфликт в {REGION_RU[region]}: обе стороны теряют по {k}")

    def _advance_quest(self, p: int, steps: int) -> None:
        if self.winner is not None or steps <= 0:
            return
        who = "frodo" if p == FELLOWSHIP else "nazgul"
        bonuses = self.quest.advance(who, steps)
        self.log.append(f"{SIDE_RU[p]}: +{steps} по Пути Кольца (разрыв {self.quest.gap})")
        if self.quest.winner is not None:
            self.winner = FELLOWSHIP if self.quest.winner == "fellowship" else SAURON
            self.win_reason = "quest"
            self.log.append(f"💍 {SIDE_RU[self.winner]} выигрывает гонку Кольца — победа!")
            return
        for b in bonuses:
            if b is Space.COIN:
                got = self._gain_coins(p, 1)
                self.log.append(f"Бонус трека: +{got} монета")
            elif b is Space.EXTRA_TURN:
                # per the owner's ruling the extra turn is OPTIONAL.
                # Спросим в самом конце хода (_settle): иначе игрок берёт доп. ход,
                # а после него ему доигрывают оставшиеся эффекты карты — выглядит как баг.
                self.extra_offers.append(p)
                self.log.append("Бонус трека: право дополнительного хода")
            elif b is Space.UNIT:
                self.pending.append(
                    {
                        "type": "place_units",
                        "player": p,
                        "n": 1,
                        "regions": list(REGION_KEYS),
                        "optional": True,
                        "why": "бонус трека",
                    }
                )
            elif b is Space.DESTROY_FORTRESS:
                self.pending.append(
                    {"type": "remove_fortress", "player": p, "optional": True, "why": "бонус трека"}
                )

    # ---------- automa helpers ----------

    def automa_side(self) -> int | None:
        a = self.rules.get("automa")
        return a["side"] if a else None

    def is_automa(self, p: int) -> bool:
        return self.automa_side() == p

    def _apower(self, p: int, power: str) -> bool:
        a = self.rules.get("automa")
        return bool(a) and a["side"] == p and power in a.get("powers", ())

    # ---------- cost ----------

    def card_cost(self, p: int, card: Card) -> dict:
        if self.is_automa(p):
            # автоме не нужны навыки, цепочки и монеты для карт глав
            return {"coins": 0, "chained": False}
        player = self.players[p]
        if card.takes_link and card.takes_link in player.links:
            return {"coins": 0, "chained": True}
        miss = missing_skills(card.cost_skills, player)
        return {"coins": card.cost_coins + miss, "chained": False}

    def tile_cost(self, p: int, lm: Landmark) -> dict:
        player = self.players[p]
        surcharge = 0 if "dwarves_free_tile" in player.tokens else self.forts_on_board(p)
        if self.is_automa(p):
            return {"coins": AUTOMA_TILE_BASE[self.chapter - 1] + surcharge, "chained": False}
        miss = missing_skills(lm.cost, player)
        return {"coins": miss + surcharge, "chained": False}

    # ---------- legal moves ----------

    def legal_moves(self) -> list[dict]:
        if self.winner is not None:
            return []
        if self.pending:
            moves = self._pending_moves(self.pending[0])
            if (
                self.pending[0].get("combo")
                and len(self.pending) > 1
                and self.pending[1].get("combo")
            ):
                # пара эффектов одной карты: игрок выбирает порядок сам
                second = [
                    m for m in self._pending_moves(self.pending[1]) if m["type"] != "skip"
                ]
                seen = {tuple(sorted(m.items())) for m in moves}
                moves += [m for m in second if tuple(sorted(m.items())) not in seen]
            return moves
        moves: list[dict] = []
        p = self.current
        for sid in self.tableau.available():
            card = self.tableau.cards[sid]
            cost = self.card_cost(p, card)
            if cost["coins"] <= self.players[p].coins:
                lbl = "по цепочке" if cost["chained"] else f"цена {cost['coins']}🪙"
                moves.append(
                    {
                        "type": "play",
                        "slot": sid,
                        "label": f"Сыграть ({lbl})",
                        "cost": cost["coins"],
                        "chained": cost["chained"],
                    }
                )
            if not self.is_automa(p):  # автома НИКОГДА не сбрасывает карты ради монет
                gain = self.rules["discard_payout"][self.chapter - 1] * (
                    2 if "humans_double_discard" in self.players[p].tokens else 1
                )
                moves.append(
                    {"type": "discard", "slot": sid, "label": f"Сбросить (+{gain}🪙)", "gain": gain}
                )
        for lm_id in self.landmarks_faceup:
            lm = LM_BY_ID[lm_id]
            cost = self.tile_cost(p, lm)
            if cost["coins"] <= self.players[p].coins:
                moves.append(
                    {
                        "type": "tile",
                        "tile": lm_id,
                        "label": f"{lm.name_ru} ({cost['coins']}🪙)",
                        "cost": cost["coins"],
                    }
                )
        return moves

    def _pending_moves(self, pd: dict) -> list[dict]:
        t = pd["type"]
        p = pd["player"]
        moves: list[dict] = []
        if t == "place_units":
            for r in pd["regions"]:
                moves.append(
                    {"type": "place", "region": r, "label": f"{pd['n']} юнит(ов) → {REGION_RU[r]}"}
                )
        elif t == "movements":
            for src in REGION_KEYS:
                if self.board_units[src][p] > 0:
                    for dst in sorted(ADJ[src]):
                        moves.append(
                            {
                                "type": "move",
                                "from": src,
                                "to": dst,
                                "label": f"Юнит: {REGION_RU[src]} → {REGION_RU[dst]}",
                            }
                        )
        elif t == "extra_turn_offer":
            moves.append({"type": "extra", "take": 1, "label": "🔄 Сходить ещё раз"})
            moves.append({"type": "extra", "take": 0, "label": "Передать ход противнику"})
        elif t == "casualties":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_units[r][opp] > 0:
                    moves.append(
                        {
                            "type": "kill",
                            "region": r,
                            "label": f"Убрать юнита врага: {REGION_RU[r]}",
                        }
                    )
        elif t == "remove_fortress":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_forts[r][opp] > 0:
                    moves.append(
                        {
                            "type": "raze",
                            "region": r,
                            "label": f"Снести крепость врага: {REGION_RU[r]}",
                        }
                    )
        elif t == "choose_token":
            for tok in pd["options"]:
                tk = TOKEN_BY_ID[tok]
                moves.append(
                    {
                        "type": "pick_token",
                        "token": tok,
                        "label": f"{RACE_RU[tk.race]}: {tk.text_ru}",
                    }
                )
        elif t == "choose_race":
            for race in RACES:
                if self.alliance_stacks[race]:
                    moves.append({"type": "pick_race", "race": race, "label": RACE_RU[race]})
        elif t == "play_from_discard":
            # сброс = ТОЛЬКО проданные карты; отложенные при сетапе — вне игры
            for i, c in enumerate(self.discard_open):
                moves.append(
                    {
                        "type": "discard_play",
                        "index": i,
                        "label": card_label(c),
                        "card": card_to_dict(c),
                    }
                )
        elif t == "discard_opp_grey":
            opp = 1 - p
            for i, c in enumerate(self.players[opp].played):
                if c.type is CardType.GREY:
                    moves.append(
                        {
                            "type": "strip_grey",
                            "index": i,
                            "label": f"Снять у врага: {card_label(c)}",
                        }
                    )
        elif t == "shire_play":
            for sid, c in self.tableau.cards.items():
                if sid in self.tableau.taken or sid not in self.tableau.revealed:
                    continue
                cost = self.card_cost(p, c)
                if cost["coins"] <= self.players[p].coins:
                    moves.append(
                        {
                            "type": "shire_pick",
                            "slot": sid,
                            "cost": cost["coins"],
                            "label": f"{card_label(c)} ({cost['coins']}🪙)",
                        }
                    )
        elif t == "grond_pick":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_forts[r][opp] > 0:
                    moves.append({"type": "grond_target", "region": r, "label": REGION_RU[r]})
        elif t == "grond_retreat":
            for dst in sorted(ADJ[pd["region"]]):
                moves.append(
                    {"type": "retreat", "to": dst, "label": f"Отступление в {REGION_RU[dst]}"}
                )
        elif t == "ents_menu":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_units[r][opp] > 0:
                    moves.append(
                        {"type": "ents_kill", "region": r, "label": f"Убрать юнита: {REGION_RU[r]}"}
                    )
            if self.players[opp].coins > 0:
                moves.append({"type": "ents_coin", "label": "Враг теряет 1 монету"})
            for src in REGION_KEYS:
                if self.board_units[src][p] > 0:
                    for dst in sorted(ADJ[src]):
                        moves.append(
                            {
                                "type": "ents_move",
                                "from": src,
                                "to": dst,
                                "label": f"Юнит: {REGION_RU[src]} → {REGION_RU[dst]}",
                            }
                        )
        if pd.get("optional") or t in ("movements", "casualties", "ents_menu"):
            moves.append({"type": "skip", "label": "Пропустить"})
        if not moves:
            moves.append({"type": "skip", "label": "Пропустить (нет вариантов)"})
        return moves

    # ---------- apply ----------

    def apply(self, move: dict) -> None:
        if self.winner is not None:
            raise ValueError("game over")
        p = self.current
        t = move["type"]
        if self.pending:
            self._apply_pending(move)
        elif t == "play":
            card = self.tableau.take(move["slot"])
            cost = self.card_cost(p, card)
            self._pay_coins(p, cost["coins"])
            self.players[p].add_card(card)
            chained = cost["chained"]
            if chained:
                how = " по цепочке"
            elif self.is_automa(p):
                how = " (автома — бесплатно)"
            else:
                how = f" за {cost['coins']}🪙"
            msg = f"Ход {self.turn_no} — {SIDE_RU[p]} играет {card_label(card)}" + how
            self.log.append(msg)
            self.last_action[p] = msg
            self.turn_no += 1
            if chained and "hobbits_chain_coins" in self.players[p].tokens:
                got = self._gain_coins(p, 3)
                self.log.append(f"Хоббиты: +{got}🪙 за цепочку")
            self._card_effects(p, card)
        elif t == "discard":
            card = self.tableau.take(move["slot"])
            self.discard_open.append(card)
            mult = 2 if "humans_double_discard" in self.players[p].tokens else 1
            got = self._gain_coins(p, self.rules["discard_payout"][self.chapter - 1] * mult)
            msg = f"Ход {self.turn_no} — {SIDE_RU[p]} сбрасывает карту (+{got}🪙)"
            self.log.append(msg)
            self.last_action[p] = msg
            self.turn_no += 1
        elif t == "tile":
            lm = LM_BY_ID[move["tile"]]
            cost = self.tile_cost(p, lm)
            self._pay_coins(p, cost["coins"])
            self.landmarks_faceup.remove(lm.id)
            self.players[p].landmarks.append(lm.id)
            msg = f"Ход {self.turn_no} — {SIDE_RU[p]} возводит {lm.name_ru} за {cost['coins']}🪙"
            self.log.append(msg)
            self.last_action[p] = msg
            self.turn_no += 1
            self._tile_effects(p, lm)
            if "dwarves_tile_turn" in self.players[p].tokens:
                self.extra_turns += 1
                self.log.append("Гномы: дополнительный ход")
        else:
            raise ValueError(f"bad move {move}")
        self._settle()

    def _settle(self) -> None:
        """Drop empty pendings; end the turn when nothing is left to decide."""
        while self.pending and self.winner is None:
            head = self.pending[0]
            moves = self._pending_moves(head)
            if any(m["type"] != "skip" for m in moves):
                return  # real decision required
            self.pending.pop(0)  # nothing to do — auto-skip
        if self.winner is not None:
            self.pending.clear()
            self.extra_offers.clear()
            return
        if self.extra_offers:
            # все эффекты хода отыграны — теперь спрашиваем про дополнительный ход
            self.pending.append(
                {
                    "type": "extra_turn_offer",
                    "player": self.extra_offers.pop(0),
                    "why": "бонус трека — дополнительный ход",
                }
            )
            return
        self._end_turn()

    def _end_turn(self) -> None:
        if self.tableau.empty:
            if self.chapter == 3:
                self._final_scoring()
                return
            self.chapter += 1
            self.tableau = Tableau(self.chapter, seed=self.rng.randrange(1 << 30))
            self.discard_hidden.extend(self.tableau.discarded)
            while len(self.landmarks_faceup) < 3 and self.landmarks_deck:
                self.landmarks_faceup.append(self.landmarks_deck.pop())
            self.log.append(f"— Эпоха {self.chapter} —")
        if self.extra_turns > 0:
            self.extra_turns -= 1
            self.log.append(f"{SIDE_RU[self.current]} ходит ещё раз")
        else:
            self.current = 1 - self.current

    def _final_scoring(self) -> None:
        a, b = self.presence_count(0), self.presence_count(1)
        if a > b:
            self.winner = 0
        elif b > a:
            self.winner = 1
        else:
            self.winner = "draw"
        self.win_reason = "presence"
        who = "ничья" if self.winner == "draw" else f"победа: {SIDE_RU[self.winner]}"
        self.log.append(f"Конец 3-й эпохи. Присутствие {a}:{b} — {who}.")

    # ---------- card effects ----------

    def _card_effects(self, p: int, card: Card) -> None:
        toks = self.players[p].tokens
        # сила Тома Бомбадила / Похлёбки Эовин: +3🪙 за карту с символом цепочки
        if self._apower(p, "chain_coins3") and card.takes_link:
            got = self._gain_coins(p, 3)
            self.log.append(f"Сила персонажа: +{got}🪙 за символ цепочки")
        if card.type is CardType.YELLOW:
            got = self._gain_coins(p, card.coins)
            self.log.append(f"+{got}🪙")
            if "humans_yellow_quest" in toks or self._apower(p, "yellow_quest"):
                self._advance_quest(p, 1)
            if "elves_extra_turn" in toks:
                self.extra_turns += 1
                self.log.append("Эльфы: дополнительный ход")
        elif card.type is CardType.BLUE:
            self._advance_quest(p, card.quest_steps)
            if (
                "hobbits_blue_unit" in toks or self._apower(p, "blue_unit")
            ) and self.winner is None:
                self.pending.append(
                    {
                        "type": "place_units",
                        "player": p,
                        "n": 1,
                        "regions": list(REGION_KEYS),
                        "optional": True,
                        "why": "Хоббиты" if "hobbits_blue_unit" in toks else "сила персонажа",
                    }
                )
        elif card.type is CardType.RED:
            n = card.troops + (
                1 if "humans_red_extra" in toks or self._apower(p, "red_extra") else 0
            )
            regions = list(REGION_KEYS) if "elves_red_any" in toks else list(card.destinations)
            self.pending.append({"type": "place_units", "player": p, "n": n, "regions": regions})
        elif card.type is CardType.GREEN:
            self._green_effects(p, card)
        elif card.type is CardType.PURPLE:
            if card.movements:
                combo = bool(card.casualties)  # пара эффектов одной карты — порядок свободный
                self.pending.append(
                    {"type": "movements", "player": p, "n": card.movements, "combo": combo}
                )
            if card.opp_coins_lost:
                lost = min(card.opp_coins_lost, self.players[1 - p].coins)
                self.players[1 - p].coins -= lost
                self.reserve += lost
                self.log.append(f"{SIDE_RU[1 - p]} теряет {lost}🪙")
            if card.casualties:
                combo = bool(card.movements)
                self.pending.append(
                    {"type": "casualties", "player": p, "n": card.casualties, "combo": combo}
                )

    def _green_effects(self, p: int, card: Card) -> None:
        player = self.players[p]
        counts = player.race_counts
        self._check_races(p)
        if self.winner is not None:
            return
        if "dwarves_green_moves" in player.tokens or self._apower(p, "green_moves2"):
            self.pending.append({"type": "movements", "player": p, "n": 2})
        race = card.race
        assert race is not None
        if counts.get(race, 0) == 2 and self.alliance_stacks[race]:
            top2 = self.alliance_stacks[race][:2]
            self.pending.append(
                {
                    "type": "choose_token",
                    "player": p,
                    "options": list(top2),
                    "source": {"race": race, "count": len(top2)},
                    "why": f"2 символа: {RACE_RU[race]}",
                }
            )
        if not player.used_three_diff and len(counts) >= 3:
            player.used_three_diff = True
            options = []
            races3 = sorted(counts, key=lambda r: -counts[r])[:3]
            for r in races3:
                if self.alliance_stacks[r]:
                    options.append(self.alliance_stacks[r][0])
            if options:
                self.pending.append(
                    {
                        "type": "choose_token",
                        "player": p,
                        "options": options,
                        "source": {"three_diff": True},
                        "why": "3 разных расы",
                    }
                )

    # ---------- tile effects ----------

    def _tile_effects(self, p: int, lm: Landmark) -> None:
        if lm.region:
            self.board_forts[lm.region][p] += 1
            self.log.append(f"Крепость в {REGION_RU[lm.region]}")
            self._check_conquer()
            if lm.units:
                self._place_units(p, lm.region, lm.units)
        if lm.coins:
            got = self._gain_coins(p, lm.coins)
            self.log.append(f"+{got}🪙")
        if lm.quest_steps:
            self._advance_quest(p, lm.quest_steps)
        if self.winner is not None:
            return
        if lm.movements:
            self.pending.append({"type": "movements", "player": p, "n": lm.movements})
        if lm.effect == "play_from_discard":
            self.pending.append({"type": "play_from_discard", "player": p, "optional": True})
        elif lm.effect == "grey_havens_tokens":
            self.pending.append({"type": "choose_race", "player": p})
        elif lm.effect == "discard_opp_grey":
            self.pending.append({"type": "discard_opp_grey", "player": p, "optional": True})
        elif lm.effect == "shire_play_visible":
            self.pending.append({"type": "shire_play", "player": p, "optional": True})
        elif lm.effect == "grond_assault":
            self.pending.append({"type": "grond_pick", "player": p, "optional": True})

    # ---------- token effects ----------

    def _gain_token(self, p: int, token_id: str) -> None:
        tk = TOKEN_BY_ID[token_id]
        self.log.append(f"{SIDE_RU[p]} получает жетон: {RACE_RU[tk.race]} — {tk.text_ru}")
        # instant tokens resolve once but stay on display in the player panel;
        # no effect code ever queries instant ids, so keeping them is safe
        self.players[p].tokens.append(token_id)
        if tk.kind == "passive":
            # соло-вариант: автома не умеет играть по цепочке, поэтому жетон
            # хоббитов даёт ей 3 монеты РАЗОВО при получении (Том Бомбадил и
            # Похлёбка Эовин — исключение: у них цепочная сила уже есть)
            if (
                token_id == "hobbits_chain_coins"
                and self.is_automa(p)
                and not self._apower(p, "chain_coins3")
            ):
                got = self._gain_coins(p, 3)
                self.log.append(f"Автома: +{got}🪙 разово за жетон хоббитов")
            self._check_races(p)
            return
        if token_id == "ents_extra_turn":
            self.extra_turns += 1
        elif token_id == "ents_remove_fort":
            self.pending.append({"type": "remove_fortress", "player": p, "optional": True})
        elif token_id == "ents_menu3":
            self.pending.append({"type": "ents_menu", "player": p, "n": 3})
        elif token_id == "wizards_quest2":
            self._advance_quest(p, 2)
        elif token_id == "wizards_units2":
            for _ in range(2):
                self.pending.append(
                    {
                        "type": "place_units",
                        "player": p,
                        "n": 1,
                        "regions": list(REGION_KEYS),
                        "optional": True,
                        "why": "Волшебники",
                    }
                )
        elif token_id == "wizards_discard_play":
            self.pending.append({"type": "play_from_discard", "player": p, "optional": True})

    # ---------- pending application ----------

    def _apply_pending(self, move: dict) -> None:
        pd = self.pending[0]
        if pd.get("combo") and len(self.pending) > 1 and self.pending[1].get("combo"):
            # свободный порядок пары эффектов: ход адресует нужный пендинг
            want = {"move": "movements", "kill": "casualties"}.get(move["type"])
            if want and pd["type"] != want and self.pending[1]["type"] == want:
                self.pending[0], self.pending[1] = self.pending[1], self.pending[0]
                pd = self.pending[0]
        p = pd["player"]
        t = move["type"]
        if t == "skip":
            self.pending.pop(0)
            return
        if pd["type"] == "extra_turn_offer":
            self.pending.pop(0)
            if move.get("take"):
                self.extra_turns += 1
                self.log.append(f"{SIDE_RU[p]} использует дополнительный ход")
            else:
                self.log.append(f"{SIDE_RU[p]} отказывается от дополнительного хода")
        elif pd["type"] == "place_units":
            self.pending.pop(0)
            self._place_units(p, move["region"], pd["n"])
        elif pd["type"] == "movements":
            self.board_units[move["from"]][p] -= 1
            self.board_units[move["to"]][p] += 1
            self.log.append(
                f"{SIDE_RU[p]}: юнит {REGION_RU[move['from']]} → {REGION_RU[move['to']]}"
            )
            self._resolve_conflict(move["to"])
            self._check_conquer()
            pd["n"] -= 1
            if pd["n"] <= 0:
                self.pending.pop(0)
        elif pd["type"] == "casualties":
            self.board_units[move["region"]][1 - p] -= 1
            self.log.append(f"{SIDE_RU[1 - p]} теряет юнита в {REGION_RU[move['region']]}")
            self._check_conquer()
            pd["n"] -= 1
            if pd["n"] <= 0:
                self.pending.pop(0)
        elif pd["type"] == "remove_fortress":
            self.pending.pop(0)
            self.board_forts[move["region"]][1 - p] -= 1
            self.log.append(f"Крепость {SIDE_RU[1 - p]} в {REGION_RU[move['region']]} снесена")
            self._check_conquer()
        elif pd["type"] == "choose_token":
            self.pending.pop(0)
            chosen = move["token"]
            src = pd["source"]
            if src.get("three_diff"):
                for tok in pd["options"]:
                    race = TOKEN_BY_ID[tok].race
                    if tok == chosen:
                        self.alliance_stacks[race].remove(tok)
            else:
                race = src["race"]
                self.alliance_stacks[race].remove(chosen)
            self._gain_token(p, chosen)
        elif pd["type"] == "choose_race":
            self.pending.pop(0)
            race = move["race"]
            top2 = self.alliance_stacks[race][:2]
            self.pending.insert(
                0,
                {
                    "type": "choose_token",
                    "player": p,
                    "options": list(top2),
                    "source": {"race": race},
                    "why": f"Серые Гавани: {RACE_RU[race]}",
                },
            )
        elif pd["type"] == "play_from_discard":
            self.pending.pop(0)
            card = self.discard_open.pop(move["index"])
            self.players[p].add_card(card)
            self.log.append(f"{SIDE_RU[p]} играет из сброса {card_label(card)} (бесплатно)")
            self._card_effects(p, card)
        elif pd["type"] == "discard_opp_grey":
            self.pending.pop(0)
            card = self.players[1 - p].remove_card(move["index"])
            self.discard_open.append(card)
            self.log.append(f"Изенгард: у {SIDE_RU[1 - p]} снята {card_label(card)}")
        elif pd["type"] == "shire_play":
            self.pending.pop(0)
            card = self.tableau.take_any(move["slot"])
            cost = self.card_cost(p, card)
            self._pay_coins(p, cost["coins"])
            self.players[p].add_card(card)
            self.log.append(f"Шир: {SIDE_RU[p]} играет {card_label(card)} за {cost['coins']}🪙")
            self._card_effects(p, card)
        elif pd["type"] == "grond_pick":
            self.pending.pop(0)
            region = move["region"]
            self.board_forts[region][1 - p] -= 1
            self.log.append(f"Гронд: крепость {SIDE_RU[1 - p]} в {REGION_RU[region]} разрушена")
            enemies = self.board_units[region][1 - p]
            if enemies > 0:
                self.pending.insert(
                    0, {"type": "grond_retreat", "player": p, "region": region, "count": enemies}
                )
            else:
                self._grond_finish(p, region)
        elif pd["type"] == "grond_retreat":
            self.pending.pop(0)
            region, dst, k = pd["region"], move["to"], pd["count"]
            self.board_units[region][1 - p] -= k
            self.board_units[dst][1 - p] += k
            self.log.append(f"Гронд: {k} юнит(ов) {SIDE_RU[1 - p]} отступают в {REGION_RU[dst]}")
            self._resolve_conflict(dst)
            self._grond_finish(p, pd["region"])
        elif pd["type"] == "ents_menu":
            if t == "ents_kill":
                self.board_units[move["region"]][1 - p] -= 1
                self.log.append(
                    f"Энты: {SIDE_RU[1 - p]} теряет юнита в {REGION_RU[move['region']]}"
                )
            elif t == "ents_coin":
                lost = min(1, self.players[1 - p].coins)
                self.players[1 - p].coins -= lost
                self.reserve += lost
                self.log.append(f"Энты: {SIDE_RU[1 - p]} теряет {lost}🪙")
            elif t == "ents_move":
                self.board_units[move["from"]][p] -= 1
                self.board_units[move["to"]][p] += 1
                self._resolve_conflict(move["to"])
                self.log.append(f"Энты: юнит {REGION_RU[move['from']]} → {REGION_RU[move['to']]}")
            self._check_conquer()
            pd["n"] -= 1
            if pd["n"] <= 0:
                self.pending.pop(0)
        else:
            raise ValueError(f"bad pending move {move} for {pd}")

    def _grond_finish(self, p: int, region: str) -> None:
        self.board_forts[region][p] += 1
        self.log.append(f"Гронд: крепость {SIDE_RU[p]} в {REGION_RU[region]}")
        self._place_units(p, region, 1)
        self._check_conquer()

    # ---------- serialization ----------

    def to_dict(self) -> dict:
        tab = self.tableau.to_dict()
        lms = [landmark_to_dict(LM_BY_ID[i]) for i in self.landmarks_faceup]
        if self.winner is None:
            for slot in tab["slots"]:
                if slot["available"] and not slot["taken"] and slot["card"]:
                    cost = self.card_cost(self.current, self.tableau.cards[slot["id"]])
                    slot["price"] = {
                        "coins": cost["coins"],
                        "chained": cost["chained"],
                        "affordable": cost["coins"] <= self.players[self.current].coins,
                    }
            for lm_d in lms:
                cost = self.tile_cost(self.current, LM_BY_ID[lm_d["id"]])
                lm_d["price"] = {
                    "coins": cost["coins"],
                    "chained": False,
                    "affordable": cost["coins"] <= self.players[self.current].coins,
                }
        return {
            "chapter": self.chapter,
            "current": self.current,
            "promo": self.promo,
            "turn_no": self.turn_no,
            "winner": self.winner,
            "win_reason": self.win_reason,
            "reserve": self.reserve,
            "players": [
                {
                    "side": ["fellowship", "sauron"][i],
                    "coins": pl.coins,
                    "played": [card_to_dict(c) for c in pl.played],
                    "links": sorted(pl.links),
                    "races": pl.race_counts,
                    "race_victory_count": pl.race_symbols_for_victory(),
                    "tokens": [
                        {
                            "id": t,
                            "race": TOKEN_BY_ID[t].race,
                            "text": TOKEN_BY_ID[t].text_ru,
                            "kind": TOKEN_BY_ID[t].kind,
                        }
                        for t in pl.tokens
                    ],
                    "presence": self.presence_count(i),
                    "supply": self.supply(i),
                    "last_action": self.last_action[i],
                }
                for i, pl in enumerate(self.players)
            ],
            "board": {
                r: {"units": self.board_units[r], "forts": self.board_forts[r]} for r in REGION_KEYS
            },
            "quest": self.quest.to_dict(),
            "tableau": tab,
            "landmarks": lms,
            "landmarks_deck": len(self.landmarks_deck),
            "alliance_stacks": {
                # composition is public info (only the ORDER is hidden), so
                # expose the remaining tokens sorted by id to mask the order
                r: {
                    "count": len(s),
                    "tokens": sorted(
                        ({"id": t, "text": TOKEN_BY_ID[t].text_ru} for t in s),
                        key=lambda d: d["id"],
                    ),
                }
                for r, s in self.alliance_stacks.items()
            },
            "discard_hidden": len(self.discard_hidden),
            "discard_open": [card_to_dict(c) for c in self.discard_open],
            "pending": self.pending[0] if self.pending else None,
            "moves": self.legal_moves(),
            "log": self.log[-14:],
        }


def card_label(c: Card) -> str:
    if c.type is CardType.YELLOW:
        return f"Золото +{c.coins}"
    if c.type is CardType.BLUE:
        return f"Кольцо ×{c.quest_steps}"
    if c.type is CardType.GREEN:
        return f"Раса: {RACE_RU[c.race]}"
    if c.type is CardType.RED:
        dst = "/".join(REGION_RU[d] for d in c.destinations)
        return f"Война ×{c.troops} ({dst})"
    if c.type is CardType.PURPLE:
        return "Манёвры"
    if c.skills_choice:
        return "Навык: " + "/".join(SKILL_RU[s] for s in c.skills_choice)
    return "Навык: " + "+".join(SKILL_RU[s] for s in c.skills)
