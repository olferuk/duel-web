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
from duel.engine.allies import BY_ID as ALLY_BY_ID
from duel.engine.allies import BY_SIDE as ALLY_BY_SIDE
from duel.engine.allies import ally_to_dict
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

def _edge_key(a: str, b: str) -> str:
    """Ключ связи регионов — упорядоченная пара, чтобы пережить JSON."""
    return "|".join(sorted((a, b)))


def move_key(m: dict) -> tuple:
    """Хэшируемый ключ хода без подписи: значения-списки/словари — через repr."""
    return tuple(
        sorted(
            (k, v if isinstance(v, (int, float, str, bool, type(None))) else repr(v))
            for k, v in m.items()
            if k != "label"
        )
    )


FELLOWSHIP, SAURON = 0, 1
SIDE_RU = ["Fellowship", "Sauron"]
UNITS_SUPPLY = 15
RACES = ["elves", "ents", "hobbits", "humans", "dwarves", "wizards"]
RACE_RU = {
    "elves": "Elves",
    "ents": "Ents",
    "hobbits": "Hobbits",
    "humans": "Humans",
    "dwarves": "Dwarves",
    "wizards": "Wizards",
}
SKILL_RU = {
    "Face": "Cunning",
    "Fist": "Strength",
    "Heart": "Courage",
    "Crown": "Leadership",
    "Book": "Knowledge",
}


@dataclass
class Player:
    coins: int = 0
    played: list[Card] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    landmarks: list[str] = field(default_factory=list)
    used_three_diff: bool = False
    # DLC Allies: жетоны Силы и карты союзников (пусто вне режима)
    power: int = 0
    ally_hand: list[str] = field(default_factory=list)
    ally_open: list[str] = field(default_factory=list)
    ally_gone: list[str] = field(default_factory=list)
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
    # DLC Allies (what-if рычаги; сам режим включается флагом Game(allies=True))
    "allies_pool": 7,  # карт союзников на фракцию
    "allies_hand": 3,  # сколько из них берётся в руку
    "power_start": 1,  # жетонов Силы игроку на старте
    "power_per_chapter": 2,  # жетонов на пирамиду при подготовке главы
}

# базовая цена ориентира для автомы по эпохам (соло-вариант, стр. 2)
AUTOMA_TILE_BASE = (7, 5, 2)

# DLC Allies: куда ложатся жетоны Силы при подготовке главы (диаграммы стр. 6).
# Заданы как (row, x), а не id слота, чтобы пережить правку layout.py.
# Во всех трёх главах — на ЗАКРЫТЫХ картах, симметрично на x = ∓2.
POWER_POSITIONS: dict[int, tuple[tuple[int, int], ...]] = {
    1: ((1, -2), (1, 2)),
    2: ((1, -2), (1, 2)),
    3: ((3, -2), (3, 2)),
}
POWER_TOKENS_TOTAL = 8


class Game:
    def __init__(
        self,
        seed: int | None = None,
        promo: bool = False,
        rules: dict | None = None,
        allies: bool = False,
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
        # ---- DLC Allies ----
        self.allies = allies
        start = self.rules["power_start"] if allies else 0
        self.power_supply = POWER_TOKENS_TOTAL - 2 * start if allies else 0
        for pl in self.players:
            pl.power = start
        self.power_slots: set[int] = set()
        # жетоны, окончательно выбывшие из игры (снятые с назгула, снятые
        # с ориентира при его покупке владельцем) — только для инварианта «всего 8»
        self.power_retired = 0
        self.ally_called = False
        self.ally_offered = False  # предложение призыва в этом ходу уже показывали
        # сколько жетонов Силы игрок получил ИМЕННО в этом ходу: только это
        # открывает призыв, который не был доступен до действия (см. _settle)
        self.power_gained_turn = [0, 0]
        self.turn_action_done = False
        # Том Бомбадил: жетоны, мешающие игроку двигаться по треку Кольца.
        # Индекс — тот, КОМУ мешают: обычно это Саурон (карта Братства), но
        # exit-эффект, применённый варгом в свою пользу, инвертирует роли.
        self.quest_locks = [0, 0]
        self.locked_stacks: dict[str, int] = {}
        self.locked_landmarks: dict[str, int] = {}
        self.locked_edges: dict[str, int] = {}
        # История применённых ходов (ключи без label) — кортеж, чтобы клоны
        # делили его бесплатно; нужна поиску для переноса дерева между ходами
        self.history: tuple = ()
        self.forced_take: dict | None = None
        if allies:
            self._deal_allies()
            self._place_power_tokens()
        # режим партии — первой строкой лога: «а стояла ли галочка промо?»
        # должно быть видно и через час после старта
        modes = ("Promo tiles: on." if promo else "") + (
            " Allies expansion: on." if allies else ""
        )
        self.log: list[str] = [("Game started. Sauron moves first. " + modes).rstrip()]

    # ---------- DLC Allies: setup ----------

    def _deal_allies(self) -> None:
        """Каждому — `allies_hand` случайных карт из `allies_pool` своей фракции.

        Остальные уходят вне игры не глядя: их id нигде не сохраняются, поэтому
        соперник (и поиск ботов) знает только состав колоды фракции.

        Режим `allies_ban_stable` (SP-2, стратифицированная абляция): бан не
        фильтрует колоду ДО тасовки (иначе сдвигается весь RNG партии), а
        заменяет забанённую карту в руке следующей незабанённой из остатка.
        Партии, где банённая карта не пришла в руку, побитово совпадают с
        бейзлайном — их можно не переигрывать.
        """
        ban = set(self.rules.get("allies_ban") or ())
        stable = bool(self.rules.get("allies_ban_stable"))
        for p in (FELLOWSHIP, SAURON):
            pool = self._ally_pool(p, keep_ban=stable)
            self.rng.shuffle(pool)
            hand = pool[: self.rules["allies_hand"]]
            if stable and ban:
                rest = [a for a in pool[self.rules["allies_hand"]:] if a not in ban]
                hand = [a if a not in ban else (rest.pop(0) if rest else None) for a in hand]
                hand = [a for a in hand if a is not None]
            self.players[p].ally_hand = hand

    def _ally_pool(self, p: int, keep_ban: bool = False) -> list[str]:
        """Колода фракции с учётом what-if правила `allies_ban` (абляция карт).

        keep_ban=True — не выбрасывать бан до тасовки (режим allies_ban_stable,
        замена происходит после раздачи в _deal_allies)."""
        ban = set() if keep_ban else set(self.rules.get("allies_ban") or ())
        return [a for a in list(ALLY_BY_SIDE[p])[: self.rules["allies_pool"]] if a not in ban]

    def _place_power_tokens(self) -> None:
        """Разложить жетоны Силы на карты пирамиды текущей главы.

        Позиции берутся по (row, x): при нестандартной раскладке отсутствующая
        позиция просто пропускается (решение раздела 8 спеки).
        """
        self.power_slots = set()
        if not self.allies:
            return
        want = self.rules["power_per_chapter"]
        by_pos = {(s.row, s.x): s.id for s in self.tableau.slots}
        for row, x in POWER_POSITIONS.get(self.chapter, ())[:want]:
            sid = by_pos.get((row, x))
            if sid is None or self.power_supply <= 0:
                continue
            self.power_slots.add(sid)
            self.power_supply -= 1

    def _award_power(self, p: int, revealed: list[int]) -> None:
        """Отдать игроку жетоны Силы со свежевскрытых карт."""
        if not self.allies or not self.power_slots:
            return
        got = self.power_slots & set(revealed)
        for sid in got:
            self.power_slots.discard(sid)
            self.players[p].power += 1
            self.power_gained_turn[p] += 1
        if got:
            self.log.append(f"{SIDE_RU[p]}: +{len(got)} Power token(s) from the revealed card")

    def _reveal_tableau(self, p: int) -> None:
        """Вскрыть ставшие доступными карты, начислив жетоны игроку `p`."""
        self._award_power(p, self.tableau.reveal_available())

    def _take_slot(self, p: int, slot_id: int, any_: bool = False, reveal: bool = True) -> Card:
        """Взять карту пирамиды, начислив жетоны Силы за вскрытые карты.

        Правило: «каждый раз, когда вы должны раскрыть карту с жетоном, сначала
        заберите жетон, потом переверните карту» — жетон получает тот, чьё
        действие вызвало раскрытие. `Tableau.take` игрока не знает, поэтому
        начисление живёт здесь.

        `reveal=False` — сброс без вскрытия (enter-эффект Фарамира): карты
        снизу освобождаются, но остаются закрытыми до конца хода.
        """
        if any_:
            card = self.tableau.take_any(slot_id, reveal=False)
        else:
            card = self.tableau.take(slot_id, reveal=False)
        if reveal:
            self._reveal_tableau(p)
        return card

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
                power=pl.power,
                ally_hand=list(pl.ally_hand),
                ally_open=list(pl.ally_open),
                ally_gone=list(pl.ally_gone),
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
        g.allies = self.allies
        g.power_supply = self.power_supply
        g.power_slots = set(self.power_slots)
        g.power_retired = self.power_retired
        g.ally_called = self.ally_called
        g.ally_offered = self.ally_offered
        g.power_gained_turn = list(self.power_gained_turn)
        g.turn_action_done = self.turn_action_done
        g.quest_locks = list(self.quest_locks)
        g.locked_stacks = dict(self.locked_stacks)
        g.locked_landmarks = dict(self.locked_landmarks)
        g.locked_edges = dict(self.locked_edges)
        g.history = self.history
        g.forced_take = dict(self.forced_take) if self.forced_take else None
        g.log = _NullLog()
        return g

    def randomize_hidden(self, rng: random.Random, viewer: int | None = None) -> None:
        """Resample everything hidden from BOTH players — for honest search.

        Unknowns: identities of facedown unrevealed tableau cards and of the
        hidden discard (interchangeable pool), the order inside alliance
        stacks, and all future shuffles (via reseeding our RNG). Public info
        is untouched.

        ``viewer`` — сторона, которая ведёт поиск: её собственная рука союзников
        ей известна и НЕ пересэмплируется (иначе легальные ходы призыва в мире
        расходятся с реальными, и голоса миров ложатся не на те ходы).
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
        if self.allies:
            # Рука союзников: известен только состав колоды фракции и то, какие
            # карты уже раскрыты или вышли. Пересэмплируем остаток.
            for p in (FELLOWSHIP, SAURON):
                if p == viewer:
                    continue
                pl = self.players[p]
                seen = set(pl.ally_open) | set(pl.ally_gone)
                rest = [a for a in self._ally_pool(p) if a not in seen]
                rng.shuffle(rest)
                pl.ally_hand = rest[: len(pl.ally_hand)]
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
                self.log.append(f"⚔️ {SIDE_RU[p]} conquers Middle-earth. Victory!")

    def _check_races(self, p: int) -> None:
        if self.winner is None and self.players[p].race_symbols_for_victory() >= 6:
            self.winner = p
            self.win_reason = "races"
            self.log.append(f"🤝 {SIDE_RU[p]} wins the support of 6 races. Victory!")

    def _place_units(self, p: int, region: str, n: int) -> None:
        if n > 0 and self.supply(p) == 0:
            self.log.append(f"{SIDE_RU[p]}: no units left, placement skipped")
        n = min(n, self.supply(p))
        if n <= 0:
            return
        self.board_units[region][p] += n
        self.log.append(f"{SIDE_RU[p]}: +{n} unit(s) in {REGION_RU[region]}")
        self._resolve_conflict(region)
        self._check_conquer()

    def _resolve_conflict(self, region: str) -> None:
        u = self.board_units[region]
        if u[0] > 0 and u[1] > 0:
            k = min(u[0], u[1])
            u[0] -= k
            u[1] -= k
            self.log.append(f"Conflict in {REGION_RU[region]}: each side loses {k}")

    def _advance_quest(self, p: int, steps: int) -> None:
        if self.winner is not None or steps <= 0:
            return
        who = "frodo" if p == FELLOWSHIP else "nazgul"
        if self.quest_locks[p]:
            # Том Бомбадил: каждый жетон съедает одно продвижение, остаток идёт
            # в движение (BGG: «still a two-ring card, but one advancement»)
            spent = min(steps, self.quest_locks[p])
            self.quest_locks[p] -= spent
            self.power_retired += spent  # снятый жетон выбывает из игры
            steps -= spent
            self.log.append(
                f"Tom Bombadil: {SIDE_RU[p]} removes {spent} token(s),"
                f" {self.quest_locks[p]} left"
            )
            if steps <= 0:
                return
        bonuses = self.quest.advance(who, steps)
        self.log.append(f"{SIDE_RU[p]}: +{steps} on the Ring Path (gap {self.quest.gap})")
        if self.quest.winner is not None:
            self.winner = FELLOWSHIP if self.quest.winner == "fellowship" else SAURON
            self.win_reason = "quest"
            self.log.append(f"💍 {SIDE_RU[self.winner]} wins the Ring race. Victory!")
            return
        for b in bonuses:
            if b is Space.COIN:
                got = self._gain_coins(p, 1)
                self.log.append(f"Track bonus: +{got} coin")
            elif b is Space.EXTRA_TURN:
                # per the owner's ruling the extra turn is OPTIONAL.
                # Спросим в самом конце хода (_settle): иначе игрок берёт доп. ход,
                # а после него ему доигрывают оставшиеся эффекты карты — выглядит как баг.
                self.extra_offers.append(p)
                self.log.append("Track bonus: extra turn available")
            elif b is Space.UNIT:
                self.pending.append(
                    {
                        "type": "place_units",
                        "player": p,
                        "n": 1,
                        "regions": list(REGION_KEYS),
                        "optional": True,
                        "why": "track bonus",
                    }
                )
            elif b is Space.DESTROY_FORTRESS:
                self.pending.append(
                    {"type": "remove_fortress", "player": p, "optional": True, "why": "track bonus"}
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
        if self.forced_take is not None and self.forced_take["player"] == p:
            if self.forced_take["slot"] in self.tableau.taken:
                # навязанная карта исчезла до хода соперника — обязанность гаснет
                self.forced_take = None
            else:
                return self._forced_moves()
        for sid in self.tableau.available():
            card = self.tableau.cards[sid]
            cost = self.card_cost(p, card)
            if cost["coins"] <= self.players[p].coins:
                lbl = "via chain" if cost["chained"] else f"cost {cost['coins']}🪙"
                moves.append(
                    {
                        "type": "play",
                        "slot": sid,
                        "label": f"Play ({lbl})",
                        "cost": cost["coins"],
                        "chained": cost["chained"],
                    }
                )
            if not self.is_automa(p):  # автома НИКОГДА не сбрасывает карты ради монет
                gain = self.rules["discard_payout"][self.chapter - 1] * (
                    2 if "humans_double_discard" in self.players[p].tokens else 1
                )
                moves.append(
                    {"type": "discard", "slot": sid, "label": f"Discard (+{gain}🪙)", "gain": gain}
                )
        for lm_id in self.landmarks_faceup:
            if not self._landmark_open(lm_id, p):
                continue  # заперт жетоном вождя урук-хай
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
        if not self.ally_called:
            moves += self._ally_moves()
        return moves

    # ---------- DLC Allies: призыв ----------

    def _ally_moves(self, p: int | None = None) -> list[dict]:
        """Ходы призыва: enter из руки за 1 жетон, exit раскрытого за 2."""
        if not self.allies:
            return []
        p = self.current if p is None else p
        pl = self.players[p]
        moves: list[dict] = []
        if pl.power >= 1:
            for aid in pl.ally_hand:
                moves.append(
                    {
                        "type": "ally_enter",
                        "ally": aid,
                        "label": f"{ALLY_BY_ID[aid].name_ru}: summon (1 token)",
                    }
                )
        if pl.power >= 2:
            for aid in pl.ally_open:
                moves.append(
                    {
                        "type": "ally_exit",
                        "ally": aid,
                        "label": f"{ALLY_BY_ID[aid].name_ru}: farewell (2 tokens)",
                    }
                )
        return moves

    def _forced_moves(self) -> list[dict]:
        """Грима: вместо своего хода соперник обязан взять указанную карту.

        Обычный ход заменён целиком — ни ориентиров, ни призыва союзника
        (призыв станет доступен сразу после исполнения, через ally_offer).
        """
        assert self.forced_take is not None
        ft = self.forced_take
        p = ft["player"]
        sid = ft["slot"]
        moves: list[dict] = []
        card = self.tableau.cards[sid]
        gain = self.rules["discard_payout"][self.chapter - 1] * (
            2 if "humans_double_discard" in self.players[p].tokens else 1
        )
        if ft["mode"] == "play_or_discard":
            cost = self.card_cost(p, card)
            if cost["coins"] <= self.players[p].coins:
                lbl = "via chain" if cost["chained"] else f"cost {cost['coins']}🪙"
                moves.append(
                    {
                        "type": "play",
                        "slot": sid,
                        "label": f"Gríma commands: play ({lbl})",
                        "cost": cost["coins"],
                        "chained": cost["chained"],
                    }
                )
        moves.append(
            {
                "type": "discard",
                "slot": sid,
                "label": f"Gríma commands: discard (+{gain}🪙)",
                "gain": gain,
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
                    {"type": "place", "region": r, "label": f"{pd['n']} unit(s) → {REGION_RU[r]}"}
                )
        elif t == "movements":
            for src in REGION_KEYS:
                if self.board_units[src][p] > 0:
                    for dst in sorted(ADJ[src]):
                        if not self._edge_open(src, dst, p):
                            continue  # связь перекрыта жетоном Балрога
                        moves.append(
                            {
                                "type": "move",
                                "from": src,
                                "to": dst,
                                "label": f"Unit: {REGION_RU[src]} → {REGION_RU[dst]}",
                            }
                        )
        elif t == "extra_turn_offer":
            moves.append({"type": "extra", "take": 1, "label": "🔄 Take another turn"})
            moves.append({"type": "extra", "take": 0, "label": "Pass the turn"})
        elif t == "casualties":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_units[r][opp] > 0:
                    moves.append(
                        {
                            "type": "kill",
                            "region": r,
                            "label": f"Remove enemy unit: {REGION_RU[r]}",
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
                            "label": f"Destroy enemy fortress: {REGION_RU[r]}",
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
                if self.alliance_stacks[race] and self._stack_open(race, p):
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
                            "label": f"Take from enemy: {card_label(c)}",
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
                    {"type": "retreat", "to": dst, "label": f"Retreat to {REGION_RU[dst]}"}
                )
        elif t == "ents_menu":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_units[r][opp] > 0:
                    moves.append(
                        {"type": "ents_kill", "region": r, "label": f"Remove unit: {REGION_RU[r]}"}
                    )
            if self.players[opp].coins > 0:
                moves.append({"type": "ents_coin", "label": "Enemy loses 1 coin"})
            for src in REGION_KEYS:
                if self.board_units[src][p] > 0:
                    for dst in sorted(ADJ[src]):
                        if not self._edge_open(src, dst, p):
                            continue
                        moves.append(
                            {
                                "type": "ents_move",
                                "from": src,
                                "to": dst,
                                "label": f"Unit: {REGION_RU[src]} → {REGION_RU[dst]}",
                            }
                        )
        elif t == "ally_offer":
            moves += self._ally_moves(p)
        elif t == "kill_region_all":
            opp = 1 - p
            for r in REGION_KEYS:
                if self.board_units[r][opp] > 0:
                    moves.append(
                        {
                            "type": "kill_all",
                            "region": r,
                            "label": f"Remove all: {REGION_RU[r]} ({self.board_units[r][opp]})",
                        }
                    )
        elif t == "arwen_chapter":
            for ch in sorted({c.chapter for c in self.discard_open}):
                moves.append({"type": "arwen_pick", "chapter": ch, "label": f"Chapter {ch}"})
        elif t == "elrond_race":
            for race in pd["races"]:
                if self.alliance_stacks[race] and self._stack_open(race, p):
                    moves.append({"type": "pick_race", "race": race, "label": RACE_RU[race]})
        elif t == "faramir_discard":
            for sid in self.tableau.available():
                moves.append(
                    {
                        "type": "faramir_pick",
                        "slot": sid,
                        "label": f"Discard: {self._slot_label(sid)}",
                    }
                )
        elif t == "witch_king_choice":
            moves.append({"type": "wk_quest", "label": "Nazgûl: 1 step on the track"})
            for r in REGION_KEYS:
                moves.append({"type": "wk_unit", "region": r, "label": f"Unit → {REGION_RU[r]}"})
        elif t == "lock_stack":
            for race in RACES:
                if race not in self.locked_stacks and self.alliance_stacks[race]:
                    moves.append(
                        {"type": "lock_race", "race": race, "label": f"Lock: {RACE_RU[race]}"}
                    )
        elif t == "discard_opp_token":
            for i, tok in enumerate(self.players[1 - p].tokens):
                moves.append(
                    {
                        "type": "drop_token",
                        "index": i,
                        "label": f"Remove token: {TOKEN_BY_ID[tok].text_ru}",
                    }
                )
        elif t == "lock_landmark":
            for lm_id in self.landmarks_faceup:
                if lm_id not in self.locked_landmarks:
                    moves.append(
                        {
                            "type": "lock_tile",
                            "tile": lm_id,
                            "label": f"Lock: {LM_BY_ID[lm_id].name_ru}",
                        }
                    )
        elif t == "take_landmark_free":
            for lm_id in self.landmarks_faceup:
                if self._landmark_open(lm_id, p):
                    moves.append(
                        {
                            "type": "free_tile",
                            "tile": lm_id,
                            "label": f"{LM_BY_ID[lm_id].name_ru} (free)",
                        }
                    )
        elif t == "lock_edge":
            for a, b in EDGES:
                key = _edge_key(a, b)
                if key not in self.locked_edges:
                    moves.append(
                        {
                            "type": "lock_link",
                            "edge": key,
                            "label": f"Block: {REGION_RU[a]} ↔ {REGION_RU[b]}",
                        }
                    )
        elif t == "choose_opp_ally":
            for aid in self.players[1 - p].ally_open:
                moves.append(
                    {
                        "type": "steal_exit",
                        "ally": aid,
                        "label": f"{ALLY_BY_ID[aid].name_ru} farewell, for your benefit",
                    }
                )
        elif t == "steal_opp_grey":
            opp = 1 - p
            for i, c in enumerate(self.players[opp].played):
                if c.type is CardType.GREY:
                    moves.append(
                        {"type": "grab_grey", "index": i, "label": f"Take: {card_label(c)}"}
                    )
        elif t == "grima_pick":
            for sid in self.tableau.available():
                moves.append(
                    {
                        "type": "grima_target",
                        "slot": sid,
                        "label": f"Force: {self._slot_label(sid)}",
                    }
                )
        if pd.get("optional") or t in ("movements", "casualties", "ents_menu"):
            moves.append({"type": "skip", "label": "Skip"})
        if not moves:
            moves.append({"type": "skip", "label": "Skip (no options)"})
        return moves

    # ---------- apply ----------

    def apply(self, move: dict) -> None:
        if self.winner is not None:
            raise ValueError("game over")
        self.history = self.history + (move_key(move),)
        p = self.current
        t = move["type"]
        if self.pending:
            self._apply_pending(move)
        elif t in ("ally_enter", "ally_exit"):
            self._ally_call(p, move)
        elif t == "play":
            self.forced_take = None
            self.turn_action_done = True
            card = self._take_slot(p, move["slot"])
            cost = self.card_cost(p, card)
            self._pay_coins(p, cost["coins"])
            self.players[p].add_card(card)
            chained = cost["chained"]
            if chained:
                how = " via chain"
            elif self.is_automa(p):
                how = " (automa, free)"
            else:
                how = f" for {cost['coins']}🪙"
            msg = f"Turn {self.turn_no} — {SIDE_RU[p]} plays {card_label(card)}" + how
            self.log.append(msg)
            self.last_action[p] = msg
            self.turn_no += 1
            if chained and "hobbits_chain_coins" in self.players[p].tokens:
                got = self._gain_coins(p, 3)
                self.log.append(f"Hobbits: +{got}🪙 for the chain")
            self._card_effects(p, card)
        elif t == "discard":
            self.forced_take = None
            self.turn_action_done = True
            card = self._take_slot(p, move["slot"])
            self.discard_open.append(card)
            mult = 2 if "humans_double_discard" in self.players[p].tokens else 1
            got = self._gain_coins(p, self.rules["discard_payout"][self.chapter - 1] * mult)
            msg = f"Turn {self.turn_no} — {SIDE_RU[p]} discards a card (+{got}🪙)"
            self.log.append(msg)
            self.last_action[p] = msg
            self.turn_no += 1
        elif t == "tile":
            self.turn_action_done = True
            lm = LM_BY_ID[move["tile"]]
            cost = self.tile_cost(p, lm)
            self._pay_coins(p, cost["coins"])
            self.landmarks_faceup.remove(lm.id)
            if self.locked_landmarks.pop(lm.id, None) is not None:
                self.power_retired += 1  # владелец забрал свой же запертый ориентир
            self.players[p].landmarks.append(lm.id)
            msg = f"Turn {self.turn_no} — {SIDE_RU[p]} builds {lm.name_ru} for {cost['coins']}🪙"
            self.log.append(msg)
            self.last_action[p] = msg
            self.turn_no += 1
            self._tile_effects(p, lm)
            if "dwarves_tile_turn" in self.players[p].tokens:
                self.extra_turns += 1
                self.log.append("Dwarves: extra turn")
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
        if self.allies and not self.turn_action_done:
            # был только призыв союзника — обычное действие ещё впереди,
            # ход не заканчиваем и ничего больше не спрашиваем
            if self.legal_moves():
                return
            # Призыв съел последнюю возможность (Фарамир сбросил единственную
            # доступную карту без вскрытия, монет на ориентир нет, жетонов нет):
            # состояние без единого хода ломает поиск — ход просто переходит.
            self.log.append(f"{SIDE_RU[self.current]}: no moves after the summon, turn passes")
            self.turn_action_done = True
        if (
            self.allies
            and not self.ally_called
            and not self.ally_offered
            and self.power_gained_turn[self.current]
            and self._ally_moves()
        ):
            # Второе окно призыва: «в любой момент хода, даже после того, как
            # вскрылись новые карты». Спрашиваем ТОЛЬКО если игрок получил жетон
            # именно в этом ходу — иначе тот же призыв был доступен ему и до
            # действия, и вопрос вырождается в лишний клик каждый ход.
            # Спрашиваем до _end_turn, поэтому призыв успевает до раскладки
            # следующей главы — этим обеспечен тайминг на стыке глав.
            self.ally_offered = True
            self.pending.append(
                {"type": "ally_offer", "player": self.current, "optional": True}
            )
            return
        if self.extra_offers:
            # все эффекты хода отыграны — теперь спрашиваем про дополнительный ход
            self.pending.append(
                {
                    "type": "extra_turn_offer",
                    "player": self.extra_offers.pop(0),
                    "why": "track bonus: extra turn",
                }
            )
            return
        self._end_turn()

    def _end_turn(self) -> None:
        # карты, освобождённые без вскрытия (enter Фарамира), вскрываются
        # в конце хода — жетон Силы достаётся тому, чей ход закончился
        self._reveal_tableau(self.current)
        if self.tableau.empty:
            if self.chapter == 3:
                self._final_scoring()
                return
            self.chapter += 1
            self.tableau = Tableau(self.chapter, seed=self.rng.randrange(1 << 30))
            self.discard_hidden.extend(self.tableau.discarded)
            self._place_power_tokens()
            while len(self.landmarks_faceup) < 3 and self.landmarks_deck:
                self.landmarks_faceup.append(self.landmarks_deck.pop())
            self.log.append(f"— Chapter {self.chapter} —")
        self.turn_action_done = False
        self.ally_called = False
        self.ally_offered = False
        self.power_gained_turn = [0, 0]
        if self.extra_turns > 0:
            self.extra_turns -= 1
            self.log.append(f"{SIDE_RU[self.current]} takes another turn")
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
        who = "draw" if self.winner == "draw" else f"winner: {SIDE_RU[self.winner]}"
        self.log.append(f"End of Chapter 3. Presence {a}:{b} — {who}.")

    # ---------- card effects ----------

    def _card_effects(self, p: int, card: Card) -> None:
        toks = self.players[p].tokens
        # сила Тома Бомбадила / Похлёбки Эовин: +3🪙 за карту с символом цепочки
        if self._apower(p, "chain_coins3") and card.takes_link:
            got = self._gain_coins(p, 3)
            self.log.append(f"Character power: +{got}🪙 for the chain symbol")
        if card.type is CardType.YELLOW:
            got = self._gain_coins(p, card.coins)
            self.log.append(f"+{got}🪙")
            if "humans_yellow_quest" in toks or self._apower(p, "yellow_quest"):
                self._advance_quest(p, 1)
            if "elves_extra_turn" in toks:
                self.extra_turns += 1
                self.log.append("Elves: extra turn")
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
                        "why": "Hobbits" if "hobbits_blue_unit" in toks else "character power",
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
                self.log.append(f"{SIDE_RU[1 - p]} loses {lost}🪙")
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
        if counts.get(race, 0) == 2 and self.alliance_stacks[race] and self._stack_open(race, p):
            top2 = self.alliance_stacks[race][:2]
            self.pending.append(
                {
                    "type": "choose_token",
                    "player": p,
                    "options": list(top2),
                    "source": {"race": race, "count": len(top2)},
                    "why": f"2 symbols: {RACE_RU[race]}",
                }
            )
        if not player.used_three_diff and len(counts) >= 3:
            player.used_three_diff = True
            options = []
            races3 = sorted(counts, key=lambda r: -counts[r])[:3]
            for r in races3:
                # Шелоб: запертая стопка не даёт сопернику ни брать, ни смотреть
                if self.alliance_stacks[r] and self._stack_open(r, p):
                    options.append(self.alliance_stacks[r][0])
            if options:
                self.pending.append(
                    {
                        "type": "choose_token",
                        "player": p,
                        "options": options,
                        "source": {"three_diff": True},
                        "why": "3 different races",
                    }
                )

    # ---------- tile effects ----------

    def _tile_effects(self, p: int, lm: Landmark) -> None:
        if lm.region:
            self.board_forts[lm.region][p] += 1
            self.log.append(f"Fortress in {REGION_RU[lm.region]}")
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

    # ---------- DLC Allies: эффекты союзников ----------

    def _ally_call(self, p: int, move: dict) -> None:
        aid = move["ally"]
        ally = ALLY_BY_ID[aid]
        pl = self.players[p]
        enter = move["type"] == "ally_enter"
        cost = 1 if enter else 2
        assert pl.power >= cost
        pl.power -= cost
        # потраченные жетоны возвращаются в общий запас; карты, кладущие жетон
        # на поле, забирают его обратно через _put_token_on_board()
        self.power_supply += cost
        if enter:
            pl.ally_hand.remove(aid)
            pl.ally_open.append(aid)
            self.log.append(f"{SIDE_RU[p]} summons an ally: {ally.name_ru}")
        else:
            pl.ally_open.remove(aid)
            pl.ally_gone.append(aid)
            self.log.append(f"{SIDE_RU[p]} bids farewell to an ally: {ally.name_ru}")
        self.ally_called = True
        self._ally_effect(p, aid, "enter" if enter else "exit")

    def _slot_label(self, sid: int) -> str:
        """Подпись карты раскладки для меню выбора: «слот 12» игроку ничего не говорит."""
        if sid in self.tableau.revealed:
            return card_label(self.tableau.cards[sid])
        return f"face-down card (slot {sid})"

    def _stack_open(self, race: str, p: int) -> bool:
        """Доступна ли стопка Альянса игроку `p` (Шелоб запирает её сопернику)."""
        owner = self.locked_stacks.get(race)
        return owner is None or owner == p

    def _landmark_open(self, lm_id: str, p: int) -> bool:
        """Доступен ли ориентир игроку `p` (вождь урук-хай запирает сопернику)."""
        owner = self.locked_landmarks.get(lm_id)
        return owner is None or owner == p

    def _edge_open(self, a: str, b: str, p: int) -> bool:
        """Можно ли игроку `p` двигаться по связи (Балрог перекрывает сопернику)."""
        owner = self.locked_edges.get(_edge_key(a, b))
        return owner is None or owner == p

    def _put_token_on_board(self, n: int = 1) -> None:
        """Жетон лёг на поле (назгул, стопка, ориентир, связь) — он выбывает."""
        self.power_supply -= n

    def _lose_coins(self, p: int, n: int) -> int:
        lost = min(n, self.players[p].coins)
        self.players[p].coins -= lost
        self.reserve += lost
        return lost

    def _q(self, pd: dict) -> None:
        """Поставить pending с пометкой, что он от союзника (для UI и логов)."""
        pd.setdefault("optional", True)  # П2: эффект можно применить частично
        pd.setdefault("ally", True)
        self.pending.append(pd)

    def _ally_effect(self, p: int, aid: str, phase: str) -> None:
        """Эффекты всех 14 карт. `p` — тот, В ЧЬЮ ПОЛЬЗУ применяется эффект.

        Для exit-эффекта варга `p` — призвавший варга игрок, а не владелец
        карты: роли инвертируются полностью (решение 10 раздела 8 спеки).
        """
        opp = 1 - p
        enter = phase == "enter"

        # ---- Братство ----
        if aid == "tom_bombadil":
            n = 1 if enter else 2
            self.quest_locks[opp] += n
            self._put_token_on_board(n)
            self.log.append(
                f"Tom Bombadil: {SIDE_RU[opp]} must remove {self.quest_locks[opp]}"
                " token(s) before moving on the track"
            )
        elif aid == "goldberry":
            got = self._gain_coins(p, 3 if enter else 5)
            self.log.append(f"Goldberry: +{got}🪙")
            if not enter:
                lost = self._lose_coins(opp, 2)
                if lost:
                    self.log.append(f"Goldberry: {SIDE_RU[opp]} loses {lost}🪙")
        elif aid == "boromir":
            self._q({"type": "casualties" if enter else "kill_region_all", "player": p, "n": 1})
        elif aid == "arwen":
            if enter:
                self._q({"type": "arwen_chapter", "player": p})
            else:
                self._q({"type": "play_from_discard", "player": p})
        elif aid == "elrond":
            races = (
                ["dwarves", "humans", "elves", "hobbits"] if enter else ["wizards", "ents"]
            )
            self._q({"type": "elrond_race", "player": p, "races": races})
        elif aid == "faramir":
            # enter НЕ вскрывает освободившиеся карты (решение 13), exit — вскрывает
            self._q({"type": "faramir_discard", "player": p, "reveal": not enter})
            if not enter:
                self._q({"type": "faramir_discard", "player": p, "reveal": True})
        elif aid == "lobelia":
            n = 1 if enter else 2
            for _ in range(n):
                self._q(
                    {
                        "type": "place_units",
                        "player": p,
                        "n": 1,
                        "regions": list(REGION_KEYS),
                        "why": "Lobelia",
                    }
                )
            self._q({"type": "movements", "player": p, "n": n})

        # ---- Саурон ----
        elif aid == "witch_king":
            if enter:
                self._q({"type": "witch_king_choice", "player": p})
            else:
                self._advance_quest(p, 1)
                if self.winner is None:
                    self._q(
                        {
                            "type": "place_units",
                            "player": p,
                            "n": 1,
                            "regions": list(REGION_KEYS),
                            "why": "Witch-king",
                        }
                    )
        elif aid == "shelob":
            if enter:
                self._q({"type": "lock_stack", "player": p})
            else:
                self._q({"type": "discard_opp_token", "player": p})
        elif aid == "uruk_hai_chief":
            self._q({"type": "lock_landmark" if enter else "take_landmark_free", "player": p})
        elif aid == "balrog":
            self._q({"type": "lock_edge", "player": p, "kill": not enter})
        elif aid == "warg":
            if enter:
                hand = self.players[opp].ally_hand
                if hand:
                    victim = self.rng.choice(hand)
                    hand.remove(victim)
                    self.players[opp].ally_open.append(victim)
                    self.log.append(
                        f"Warg: {SIDE_RU[opp]} reveals {ALLY_BY_ID[victim].name_ru}"
                        ", enter effect lost"
                    )
                else:
                    self.log.append("Warg: the opponent has no unrevealed allies")
            else:
                self._q({"type": "choose_opp_ally", "player": p})
        elif aid == "cave_troll":
            self._q(
                {"type": "discard_opp_grey" if enter else "steal_opp_grey", "player": p}
            )
        elif aid == "grima":
            self._q(
                {
                    "type": "grima_pick",
                    "player": p,
                    "mode": "play_or_discard" if enter else "discard",
                }
            )

    # ---------- token effects ----------

    def _gain_token(self, p: int, token_id: str) -> None:
        tk = TOKEN_BY_ID[token_id]
        self.log.append(f"{SIDE_RU[p]} gains a token: {RACE_RU[tk.race]} — {tk.text_ru}")
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
                self.log.append(f"Automa: one-time +{got}🪙 for the Hobbits token")
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
                        "why": "Wizards",
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
        if pd["type"] == "ally_offer":
            self.pending.pop(0)
            self._ally_call(p, move)
        elif pd["type"] == "kill_region_all":
            self.pending.pop(0)
            r = move["region"]
            n = self.board_units[r][1 - p]
            self.board_units[r][1 - p] = 0
            self.log.append(f"Boromir: {SIDE_RU[1 - p]} loses {n} unit(s) in {REGION_RU[r]}")
            self._check_conquer()
        elif pd["type"] == "arwen_chapter":
            self.pending.pop(0)
            pool = [i for i, c in enumerate(self.discard_open) if c.chapter == move["chapter"]]
            idx = self.rng.choice(pool)
            card = self.discard_open.pop(idx)
            self.players[p].add_card(card)
            self.log.append(f"Arwen: random card from the discard: {card_label(card)} (free)")
            self._card_effects(p, card)
        elif pd["type"] == "elrond_race":
            self.pending.pop(0)
            race = move["race"]
            tok = self.alliance_stacks[race].pop(0)
            self.log.append(f"Elrond: top {RACE_RU[race]} token")
            self._gain_token(p, tok)
        elif pd["type"] == "faramir_discard":
            self.pending.pop(0)
            card = self._take_slot(p, move["slot"], reveal=pd.get("reveal", True))
            self.discard_open.append(card)
            # монет за этот сброс НЕ даётся (примечание правил)
            self.log.append(f"Faramir: discarded from the center: {card_label(card)}")
        elif pd["type"] == "witch_king_choice":
            self.pending.pop(0)
            if t == "wk_quest":
                self._advance_quest(p, 1)
            else:
                self._place_units(p, move["region"], 1)
        elif pd["type"] == "lock_stack":
            self.pending.pop(0)
            race = move["race"]
            self.locked_stacks[race] = p
            self._put_token_on_board()
            self.log.append(f"Shelob: {RACE_RU[race]} stack closed to {SIDE_RU[1 - p]}")
        elif pd["type"] == "discard_opp_token":
            self.pending.pop(0)
            tok = self.players[1 - p].tokens.pop(move["index"])
            self.log.append(f"Shelob: {SIDE_RU[1 - p]} loses a token: {TOKEN_BY_ID[tok].text_ru}")
        elif pd["type"] == "lock_landmark":
            self.pending.pop(0)
            self.locked_landmarks[move["tile"]] = p
            self._put_token_on_board()
            self.log.append(
                f"Uruk-hai Chief: {LM_BY_ID[move['tile']].name_ru} closed to {SIDE_RU[1 - p]}"
            )
        elif pd["type"] == "take_landmark_free":
            self.pending.pop(0)
            lm = LM_BY_ID[move["tile"]]
            self.landmarks_faceup.remove(lm.id)
            if self.locked_landmarks.pop(lm.id, None) is not None:
                self.power_retired += 1  # владелец забрал свой же запертый ориентир
            self.players[p].landmarks.append(lm.id)
            self.log.append(f"Uruk-hai Chief: {SIDE_RU[p]} builds {lm.name_ru} for free")
            self._tile_effects(p, lm)
        elif pd["type"] == "lock_edge":
            self.pending.pop(0)
            key = move["edge"]
            self.locked_edges[key] = p
            self._put_token_on_board()
            a, b = key.split("|")
            self.log.append(
                f"Balrog: link {REGION_RU[a]} ↔ {REGION_RU[b]} closed to {SIDE_RU[1 - p]}"
            )
            if pd.get("kill"):
                for r in (a, b):
                    if self.board_units[r][1 - p] > 0:
                        self.board_units[r][1 - p] -= 1
                        self.log.append(f"Balrog: {SIDE_RU[1 - p]} loses a unit in {REGION_RU[r]}")
                self._check_conquer()
        elif pd["type"] == "choose_opp_ally":
            self.pending.pop(0)
            aid = move["ally"]
            self.log.append(
                f"Warg: {SIDE_RU[p]} uses the {ALLY_BY_ID[aid].name_ru} farewell"
            )
            self._ally_effect(p, aid, "exit")
        elif pd["type"] == "steal_opp_grey":
            self.pending.pop(0)
            card = self.players[1 - p].remove_card(move["index"])
            self.players[p].add_card(card)
            self.log.append(f"Cave Troll: {SIDE_RU[p]} takes {card_label(card)}")
            self._check_races(p)
        elif pd["type"] == "grima_pick":
            self.pending.pop(0)
            self.forced_take = {"player": 1 - p, "slot": move["slot"], "mode": pd["mode"]}
            self.log.append(f"Gríma forces a center card on {SIDE_RU[1 - p]}")
        elif pd["type"] == "extra_turn_offer":
            self.pending.pop(0)
            if move.get("take"):
                self.extra_turns += 1
                self.log.append(f"{SIDE_RU[p]} takes the extra turn")
            else:
                self.log.append(f"{SIDE_RU[p]} declines the extra turn")
        elif pd["type"] == "place_units":
            self.pending.pop(0)
            self._place_units(p, move["region"], pd["n"])
        elif pd["type"] == "movements":
            self.board_units[move["from"]][p] -= 1
            self.board_units[move["to"]][p] += 1
            self.log.append(
                f"{SIDE_RU[p]}: unit {REGION_RU[move['from']]} → {REGION_RU[move['to']]}"
            )
            self._resolve_conflict(move["to"])
            self._check_conquer()
            pd["n"] -= 1
            if pd["n"] <= 0:
                self.pending.pop(0)
        elif pd["type"] == "casualties":
            self.board_units[move["region"]][1 - p] -= 1
            self.log.append(f"{SIDE_RU[1 - p]} loses a unit in {REGION_RU[move['region']]}")
            self._check_conquer()
            pd["n"] -= 1
            if pd["n"] <= 0:
                self.pending.pop(0)
        elif pd["type"] == "remove_fortress":
            self.pending.pop(0)
            self.board_forts[move["region"]][1 - p] -= 1
            self.log.append(f"{SIDE_RU[1 - p]} fortress in {REGION_RU[move['region']]} destroyed")
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
                    "why": f"Grey Havens: {RACE_RU[race]}",
                },
            )
        elif pd["type"] == "play_from_discard":
            self.pending.pop(0)
            card = self.discard_open.pop(move["index"])
            self.players[p].add_card(card)
            self.log.append(f"{SIDE_RU[p]} plays {card_label(card)} from the discard (free)")
            self._card_effects(p, card)
        elif pd["type"] == "discard_opp_grey":
            self.pending.pop(0)
            card = self.players[1 - p].remove_card(move["index"])
            self.discard_open.append(card)
            self.log.append(f"Isengard: {SIDE_RU[1 - p]} loses {card_label(card)}")
        elif pd["type"] == "shire_play":
            self.pending.pop(0)
            card = self._take_slot(p, move["slot"], any_=True)
            cost = self.card_cost(p, card)
            self._pay_coins(p, cost["coins"])
            self.players[p].add_card(card)
            self.log.append(
                f"The Shire: {SIDE_RU[p]} plays {card_label(card)} for {cost['coins']}🪙"
            )
            self._card_effects(p, card)
        elif pd["type"] == "grond_pick":
            self.pending.pop(0)
            region = move["region"]
            self.board_forts[region][1 - p] -= 1
            self.log.append(f"Grond: {SIDE_RU[1 - p]} fortress in {REGION_RU[region]} destroyed")
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
            self.log.append(f"Grond: {k} {SIDE_RU[1 - p]} unit(s) retreat to {REGION_RU[dst]}")
            self._resolve_conflict(dst)
            self._grond_finish(p, pd["region"])
        elif pd["type"] == "ents_menu":
            if t == "ents_kill":
                self.board_units[move["region"]][1 - p] -= 1
                self.log.append(
                    f"Ents: {SIDE_RU[1 - p]} loses a unit in {REGION_RU[move['region']]}"
                )
            elif t == "ents_coin":
                lost = min(1, self.players[1 - p].coins)
                self.players[1 - p].coins -= lost
                self.reserve += lost
                self.log.append(f"Ents: {SIDE_RU[1 - p]} loses {lost}🪙")
            elif t == "ents_move":
                self.board_units[move["from"]][p] -= 1
                self.board_units[move["to"]][p] += 1
                self._resolve_conflict(move["to"])
                self.log.append(f"Ents: unit {REGION_RU[move['from']]} → {REGION_RU[move['to']]}")
            self._check_conquer()
            pd["n"] -= 1
            if pd["n"] <= 0:
                self.pending.pop(0)
        else:
            raise ValueError(f"bad pending move {move} for {pd}")

    def _grond_finish(self, p: int, region: str) -> None:
        self.board_forts[region][p] += 1
        self.log.append(f"Grond: {SIDE_RU[p]} fortress in {REGION_RU[region]}")
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
            "allies": self.allies,
            "power_slots": sorted(self.power_slots),
            "power_supply": self.power_supply,
            "power_retired": self.power_retired,
            "quest_locks": list(self.quest_locks),
            "locked_stacks": dict(self.locked_stacks),
            "locked_landmarks": dict(self.locked_landmarks),
            "locked_edges": dict(self.locked_edges),
            "ally_called": self.ally_called,
            "forced_take": self.forced_take,
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
                    # DLC Allies. ally_hand — скрытая информация: веб-слой
                    # вырезает чужую руку в _payload() по посадочному месту.
                    "power": pl.power,
                    "ally_hand": [ally_to_dict(ALLY_BY_ID[a]) for a in pl.ally_hand],
                    "ally_hand_count": len(pl.ally_hand),
                    "ally_open": [ally_to_dict(ALLY_BY_ID[a]) for a in pl.ally_open],
                    "ally_gone": [ally_to_dict(ALLY_BY_ID[a]) for a in pl.ally_gone],
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
        return f"Gold +{c.coins}"
    if c.type is CardType.BLUE:
        return f"Ring ×{c.quest_steps}"
    if c.type is CardType.GREEN:
        return f"Race: {RACE_RU[c.race]}"
    if c.type is CardType.RED:
        dst = "/".join(REGION_RU[d] for d in c.destinations)
        return f"War ×{c.troops} ({dst})"
    if c.type is CardType.PURPLE:
        return "Maneuvers"
    if c.skills_choice:
        return "Skill: " + "/".join(SKILL_RU[s] for s in c.skills_choice)
    return "Skill: " + "+".join(SKILL_RU[s] for s in c.skills)
