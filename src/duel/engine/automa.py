"""Автома — соло-бот по официальному фанатскому соло-варианту v1.3.

Источник правил: rules/art/solo/*.pdf (BGG, Tommaso Martinoli). Автома играет
НЕ как обычные боты проекта (у тех — та же информация и те же ходы, что у
игрока): она берёт карты бесплатно, не сбрасывает ради монет, а решения
принимает по колоде из 12 карт решений, свойствам персонажа и кубику d6.

Модуль самодостаточен: класс :class:`Automa` реализует duck-typed интерфейс
бота (``choose``/``new_game``/``after_apply``) и ведёт «трассировку» — журнал
рассуждений на русском, который веб-интерфейс показывает игроку (карта
решения, броски кубика, сработавший приоритет).

Соответствие движку:
- свободная игра карт/цены тайлов/силы персонажей — режим ``rules["automa"]``
  в :mod:`duel.engine.game` (см. :func:`automa_rules`);
- все выборы (куда юниты, кого убить, какой жетон) приходят как pending-ходы
  движка и разрешаются здесь по таблицам приоритетов из PDF (стр. 4-5, 7-8).

Осознанные трактовки неоднозначностей PDF (v1.3 сыроват):
- «повтор хода с трека, если на карте решения уже есть символ повтора» —
  считаем только символ, СОВПАВШИЙ с персонажем (как во всех остальных
  уточнениях документа);
- кубик по k кандидатам — (бросок-1) % k (в живой игре перебрасывали бы);
- «карта с символом цепочки» для Тома Бомбадила/Похлёбки — карта, у которой
  есть ВХОДЯЩАЯ цепочка (takes_link): именно её символ печатается на карте.
"""

import random
from dataclasses import dataclass, field

from duel.engine.cards import CardType
from duel.engine.game import ADJ, RACE_RU, REGION_KEYS, REGION_RU, Game
from duel.engine.landmarks import BY_ID as LM_BY_ID

# ---------------------------------------------------------------------------
# Данные: персонажи (лист personas-3x3) и карты решений (лист 2x6 / стр. 11)
# ---------------------------------------------------------------------------

# группы цветов на картах решений
GB = frozenset({CardType.GREEN, CardType.BLUE})
RP = frozenset({CardType.RED, CardType.PURPLE})
BRP = frozenset({CardType.BLUE, CardType.RED, CardType.PURPLE})
G = frozenset({CardType.GREEN})
PREF = "pref"  # слот «предпочтение персонажа»

COLOR_RU = {
    CardType.GREY: "grey",
    CardType.YELLOW: "yellow",
    CardType.GREEN: "green",
    CardType.BLUE: "blue",
    CardType.RED: "red",
    CardType.PURPLE: "purple",
}

# символы повтора хода: паучиха Шелоб и таран Гронд (врата)
SHELOB, GROND = "shelob", "grond"
REPEAT_RU = {SHELOB: "Shelob", GROND: "Grond"}


@dataclass(frozen=True)
class DecisionCard:
    id: int
    priorities: tuple  # три слота: frozenset[CardType] | "pref"
    direction: str  # "lr" | "rl" — направление сканирования раскладки
    repeat: str | None = None  # символ повтора хода


# 12 карт: столбец «слева направо» (стр. 11 слева), затем «справа налево».
DECISION_CARDS: list[DecisionCard] = [
    DecisionCard(0, (PREF, BRP, G), "lr", repeat=SHELOB),
    DecisionCard(1, (BRP, G, PREF), "lr"),
    DecisionCard(2, (BRP, G, PREF), "lr"),
    DecisionCard(3, (GB, RP, PREF), "lr"),
    DecisionCard(4, (GB, RP, PREF), "lr"),
    DecisionCard(5, (GB, RP, PREF), "lr"),
    DecisionCard(6, (PREF, GB, RP), "rl", repeat=GROND),
    DecisionCard(7, (GB, RP, PREF), "rl"),
    DecisionCard(8, (GB, RP, PREF), "rl"),
    DecisionCard(9, (BRP, G, PREF), "rl"),
    DecisionCard(10, (BRP, G, PREF), "rl"),
    DecisionCard(11, (BRP, G, PREF), "rl"),
]


@dataclass(frozen=True)
class Character:
    id: str
    name_ru: str
    powers: tuple[str, ...]  # ключи сил для движка (rules["automa"]["powers"])
    power_ru: str  # описание сил для интерфейса
    repeats: frozenset  # символы повтора хода на карте персонажа
    preferred: frozenset  # предпочитаемые цвета карт (слот PREF)
    art: str  # файл арта в static/art/solo/


CHARACTERS: dict[str, Character] = {
    c.id: c
    for c in [
        Character(
            "witch_king",
            "Witch-king",
            ("red_extra",),
            "Red card: +1 unit",
            frozenset({SHELOB}),
            frozenset({CardType.RED, CardType.PURPLE}),
            "witchking.jpg",
        ),
        Character(
            "galadriel",
            "Galadriel",
            ("red_extra",),
            "Red card: +1 unit",
            frozenset({SHELOB}),
            frozenset({CardType.RED, CardType.PURPLE}),
            "galadriel.jpg",
        ),
        Character(
            "tom_bombadil",
            "Tom Bombadil",
            ("chain_coins3",),
            "Card with a chain symbol: +3🪙",
            frozenset(),
            frozenset({CardType.GREY}),
            "tom.jpg",
        ),
        Character(
            "saruman",
            "Saruman",
            ("green_moves2",),
            "Green card: 2 moves",
            frozenset({GROND}),
            frozenset({CardType.GREEN}),
            "saruman.jpg",
        ),
        Character(
            "elrond",
            "Elrond",
            ("green_moves2",),
            "Green card: 2 moves",
            frozenset({GROND}),
            frozenset({CardType.GREEN}),
            "elrond.jpg",
        ),
        Character(
            "smaug",
            "Smaug",
            ("yellow_quest",),
            "Yellow card: +1 step on the Ring Path",
            frozenset(),
            frozenset({CardType.YELLOW}),
            "smaug.jpg",
        ),
        Character(
            "sauron",
            "Sauron",
            ("blue_unit",),
            "Blue card: a unit in any region",
            frozenset({SHELOB, GROND}),
            frozenset({CardType.BLUE}),
            "sauron.jpg",
        ),
        Character(
            "gandalf",
            "Gandalf",
            ("blue_unit",),
            "Blue card: a unit in any region",
            frozenset({SHELOB, GROND}),
            frozenset({CardType.BLUE}),
            "gandalf.jpg",
        ),
        Character(
            "eowyns_stew",
            "Éowyn's Stew",
            ("red_extra", "chain_coins3"),
            "Red card: +1 unit; chain card: +3🪙",
            frozenset({SHELOB, GROND}),
            frozenset({CardType.BLUE}),
            "stew.jpg",
        ),
    ]
}


def automa_rules(character: str, side: int) -> dict:
    """Значение rules["automa"] для Game под данного персонажа."""
    return {"side": side, "powers": list(CHARACTERS[character].powers)}


def _slot_ru(slot, char: Character) -> str:
    if slot == PREF:
        pref = "/".join(COLOR_RU[t] for t in sorted(char.preferred, key=str))
        return f"preference ({pref})"
    return "/".join(COLOR_RU[t] for t in sorted(slot, key=str))


def decision_card_to_dict(card: DecisionCard, char: Character) -> dict:
    return {
        "id": card.id,
        "direction": card.direction,
        "repeat": card.repeat,
        "repeat_matches": card.repeat in char.repeats if card.repeat else False,
        "slots": [
            {
                "pref": s == PREF,
                "colors": sorted(char.preferred if s == PREF else s, key=str),
                "label": _slot_ru(s, char),
            }
            for s in card.priorities
        ],
    }


# ---------------------------------------------------------------------------
# Автома
# ---------------------------------------------------------------------------


@dataclass
class Automa:
    """Соло-бот. Хранит колоду решений, кубик и трассировку рассуждений."""

    character: str
    seed: int | None = None
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.char = CHARACTERS[self.character]
        self.name = f"automa-{self.character}"
        self.rng = random.Random(self.seed)
        self.new_game()

    # -- интерфейс бота ------------------------------------------------------

    def new_game(self) -> None:
        self.deck = [c.id for c in DECISION_CARDS]
        self.rng.shuffle(self.deck)
        self.discard: list[int] = []
        self.card: int | None = None  # текущая (последняя вскрытая) карта решения
        self.trace: list[dict] = []
        self.turn_repeat_granted = False

    def game_rules(self, side: int) -> dict:
        """Правила партии для арены: автома объявляет свой режим движка."""
        return {"automa": automa_rules(self.character, side)}

    def choose(self, game: Game) -> dict:
        p = game.pending[0]["player"] if game.pending else game.current
        if not game.is_automa(p):
            raise ValueError("automa asked to move for a non-automa seat")
        if game.pending:
            return self._resolve_pending(game, p)
        return self._main_move(game, p)

    def after_apply(self, game: Game, move: dict) -> None:
        """Сверка после применения хода: не дублировать повтор хода.

        Если в этом ходу уже сработал символ повтора и жетон энтов «ещё один
        ход» дал бы второй дополнительный ход — по уточнению правил соло
        оставляем один.
        """
        if (
            move.get("type") == "pick_token"
            and move.get("token") == "ents_extra_turn"
            and self.turn_repeat_granted
            and game.extra_turns > 0
        ):
            game.extra_turns -= 1
            self._t(
                "repeat",
                "The Ents token gives no second extra turn (the repeat symbol already fired)",
            )

    # -- сериализация для интерфейса ----------------------------------------

    def to_dict(self) -> dict:
        return {
            "character": self.character,
            "name": self.char.name_ru,
            "power": self.char.power_ru,
            "repeats": sorted(self.char.repeats),
            "preferred": sorted(self.char.preferred, key=str),
            "art": self.char.art,
            "deck": len(self.deck),
            "discarded": len(self.discard),
            "card": (
                decision_card_to_dict(DECISION_CARDS[self.card], self.char)
                if self.card is not None
                else None
            ),
            "trace": self.trace[-40:],
        }

    # -- трассировка и кубик -------------------------------------------------

    def _t(self, kind: str, text: str, **extra) -> None:
        self.trace.append({"kind": kind, "text": text, **extra})
        del self.trace[:-120]  # не копить бесконечно

    def _die(self, reason: str, k: int = 6) -> int:
        """Бросок d6; при k кандидатах выбираем (бросок-1) % k."""
        roll = self.rng.randint(1, 6)
        self._t("die", f"🎲 {roll} — {reason}", roll=roll)
        return roll

    def _pick_by_die(self, cands: list, reason: str):
        if len(cands) == 1:
            return cands[0]
        roll = self._die(reason + f" ({len(cands)} options)")
        return cands[(roll - 1) % len(cands)]

    # -- основной ход --------------------------------------------------------

    def _main_move(self, game: Game, p: int) -> dict:
        self.turn_repeat_granted = False
        self._t("turn", f"— Automa turn ({self.char.name_ru}) —")
        moves = game.legal_moves()

        tile_moves = [m for m in moves if m["type"] == "tile"]
        if tile_moves:
            return self._buy_tile(game, p, tile_moves)
        if game.landmarks_faceup:
            cost = game.tile_cost(p, LM_BY_ID[game.landmarks_faceup[0]])["coins"]
            self._t(
                "tile",
                f"Cannot afford a landmark ({game.players[p].coins}🪙 of {cost}), plays a card",
            )

        return self._play_by_decision(game, p, moves)

    def _buy_tile(self, game: Game, p: int, tile_moves: list[dict]) -> dict:
        cost = tile_moves[0].get("cost", 0)
        self._t("tile", f"Enough coins ({game.players[p].coins}🪙), buys a landmark for {cost}🪙")
        if game.presence_count(p) == 6:
            winning = [
                m
                for m in tile_moves
                if LM_BY_ID[m["tile"]].region and not game.present(p, LM_BY_ID[m["tile"]].region)
            ]
            if winning:
                lm = LM_BY_ID[winning[0]["tile"]]
                self._t("tile", f"{lm.name_ru} gives the 7th region: instant victory!")
                return winning[0]
        names = ", ".join(LM_BY_ID[m["tile"]].name_ru for m in tile_moves)
        chosen = self._pick_by_die(tile_moves, f"which landmark to take: {names}")
        self._t("tile", f"Die roll picks: {LM_BY_ID[chosen['tile']].name_ru}")
        return chosen

    def _reveal(self) -> DecisionCard:
        if not self.deck:
            self.deck, self.discard = self.discard, []
            self.rng.shuffle(self.deck)
            self._t("reveal", "Decision deck ran out and was reshuffled")
        if self.card is not None:
            self.discard.append(self.card)
        self.card = self.deck.pop(0)
        card = DECISION_CARDS[self.card]
        arrow = "→" if card.direction == "lr" else "←"
        prio = " > ".join(_slot_ru(s, self.char) for s in card.priorities)
        rep = f", repeat: {REPEAT_RU[card.repeat]}" if card.repeat else ""
        self._t("reveal", f"Decision card: {prio}; scan {arrow}{rep}")
        return card

    def _scan_order(self, game: Game, direction: str) -> list[int]:
        """Доступные слоты: нижний ряд первым, внутри ряда по направлению."""
        avail = game.tableau.available()
        slots = game.tableau.slots
        return sorted(
            avail,
            key=lambda sid: (-slots[sid].row, slots[sid].x if direction == "lr" else -slots[sid].x),
        )

    def _play_by_decision(self, game: Game, p: int, moves: list[dict]) -> dict:
        dec = self._reveal()
        order = self._scan_order(game, dec.direction)
        chosen_sid: int | None = None
        for i, slot in enumerate(dec.priorities, start=1):
            colors = self.char.preferred if slot == PREF else slot
            matches = [sid for sid in order if game.tableau.cards[sid].type in colors]
            if matches:
                chosen_sid = matches[0]
                self._t(
                    "prio",
                    f"Priority {i} ({_slot_ru(slot, self.char)}): "
                    f"takes the first in scan order: {self._card_ru(game, chosen_sid)}",
                )
                break
            self._t("prio", f"Priority {i} ({_slot_ru(slot, self.char)}): none available")
        if chosen_sid is None:
            chosen_sid = order[0]
            side_ru = "left" if dec.direction == "lr" else "right"
            self._t(
                "prio",
                f"No match, takes the far {side_ru} of the bottom row: "
                f"{self._card_ru(game, chosen_sid)}",
            )

        self._maybe_repeat(game, p, dec, chosen_sid)
        play = next(m for m in moves if m["type"] == "play" and m["slot"] == chosen_sid)
        return play

    def _card_ru(self, game: Game, sid: int) -> str:
        from duel.engine.game import card_label

        c = game.tableau.cards[sid]
        return f"«{card_label(c)}» ({COLOR_RU[c.type]})"

    def _maybe_repeat(self, game: Game, p: int, dec: DecisionCard, sid: int) -> None:
        if not dec.repeat or dec.repeat not in self.char.repeats:
            return
        card = game.tableau.cards[sid]
        # эльфы уже дадут доп. ход за жёлтую карту — не дублируем (уточнение PDF)
        elves_dup = card.type is CardType.YELLOW and "elves_extra_turn" in game.players[p].tokens
        self.turn_repeat_granted = True
        if elves_dup:
            self._t("repeat", "Repeat matched, but the Elves token already gives one extra turn")
            return
        game.extra_turns += 1
        game.log.append(f"Automa ({self.char.name_ru}): repeat symbol, extra turn")
        self._t("repeat", f"Repeat symbol ({REPEAT_RU[dec.repeat]}) matched: extra turn!")

    # -- разрешение pending-решений ------------------------------------------

    def _resolve_pending(self, game: Game, p: int) -> dict:
        pd = game.pending[0]
        # пара «перемещения+потери» одной фиолетовой карты: сначала потери (PDF)
        if (
            pd.get("combo")
            and pd["type"] == "movements"
            and len(game.pending) > 1
            and game.pending[1].get("combo")
            and game.pending[1]["type"] == "casualties"
        ):
            pd = game.pending[1]
        t = pd["type"]
        moves = [m for m in game.legal_moves() if m["type"] != "skip"]
        if t == "place_units":
            return self._do_place(game, p, pd)
        if t == "movements":
            return self._do_move(game, p, pd)
        if t == "casualties":
            return self._do_kill(game, p, pd)
        if t == "remove_fortress":
            return self._do_raze(game, p)
        if t == "extra_turn_offer":
            return self._do_extra_offer()
        if t == "choose_token":
            return self._do_choose_token(game, pd)
        if t == "choose_race":
            return self._do_choose_race(game)
        if t == "play_from_discard":
            return self._do_discard_play(game, moves)
        if t == "discard_opp_grey":
            return self._do_strip_grey(game, p, moves)
        if t == "shire_play":
            return self._do_shire(game, moves)
        if t == "grond_pick":
            return self._do_grond_pick(game, p, moves)
        if t == "grond_retreat":
            return self._do_grond_retreat(game, p, pd, moves)
        if t == "ents_menu":
            return self._do_ents_menu(game, p, moves)
        # неизвестное решение — не падаем: пропускаем, если можно
        return {"type": "skip"}

    # выбор региона для юнитов (приоритеты красных карт, стр. 5)
    def _do_place(self, game: Game, p: int, pd: dict) -> dict:
        region = self._place_region(game, p, list(pd["regions"]), pd["n"])
        return {"type": "place", "region": region}

    def _place_region(self, game: Game, p: int, regions: list[str], n: int) -> str:
        opp = 1 - p
        steps = [
            (
                "7th region: instant victory",
                lambda r: game.presence_count(p) == 6 and not game.present(p, r),
            ),
            (
                "region with no own units or fortresses",
                lambda r: game.board_units[r][p] == 0 and game.board_forts[r][p] == 0,
            ),
            (
                f"player has ≤{n} units and no fortress",
                lambda r: game.board_units[r][opp] <= n and game.board_forts[r][opp] == 0,
            ),
            (
                f"player has ≤{n} units and a fortress",
                lambda r: game.board_units[r][opp] <= n and game.board_forts[r][opp] > 0,
            ),
        ]
        for i, (label, ok) in enumerate(steps, start=1):
            cands = [r for r in regions if ok(r)]
            if cands:
                region = self._pick_by_die(cands, f"priority tie: {label}")
                self._t("place", f"Units ({n}): priority {i}, {label} → {REGION_RU[region]}")
                return region
        region = self._pick_by_die(regions, "region for units")
        self._t("place", f"Units: no priority applied, die → {REGION_RU[region]}")
        return region

    # перемещения (приоритеты фиолетовых карт, стр. 5)
    def _do_move(self, game: Game, p: int, pd: dict) -> dict:
        n = pd["n"]
        # источник: не оголять регион (последний юнит уходит только из-под крепости)
        srcs = [
            r
            for r in REGION_KEYS
            if game.board_units[r][p] > 0
            and (game.board_units[r][p] > 1 or game.board_forts[r][p] > 0)
        ]
        if not srcs:
            self._t("move", "Move: no unit can leave, skipped")
            return {"type": "skip"}
        reach = sorted({d for s in srcs for d in ADJ[s]})
        opp = 1 - p
        steps = [
            (
                "7th region: instant victory",
                lambda r: game.presence_count(p) == 6 and not game.present(p, r),
            ),
            (
                "region with no own units or fortresses",
                lambda r: game.board_units[r][p] == 0 and game.board_forts[r][p] == 0,
            ),
            (
                f"player has ≤{n} units and no fortress",
                lambda r: game.board_units[r][opp] <= n and game.board_forts[r][opp] == 0,
            ),
            (
                f"player has ≤{n} units and a fortress",
                lambda r: game.board_units[r][opp] <= n and game.board_forts[r][opp] > 0,
            ),
        ]
        dst = None
        for i, (label, ok) in enumerate(steps, start=1):
            cands = [r for r in reach if ok(r)]
            if cands:
                dst = self._pick_by_die(cands, f"priority tie: {label}")
                self._t("move", f"Move: priority {i}, {label} → {REGION_RU[dst]}")
                break
        if dst is None:
            dst = self._pick_by_die(reach, "where to move")
            self._t("move", f"Move: no priority applied, die → {REGION_RU[dst]}")
        adj_srcs = [s for s in srcs if dst in ADJ[s]]
        best = max(game.board_units[s][p] for s in adj_srcs)
        src = self._pick_by_die(
            [s for s in adj_srcs if game.board_units[s][p] == best], "where to move from"
        )
        self._t("move", f"Unit moves {REGION_RU[src]} → {REGION_RU[dst]}")
        return {"type": "move", "from": src, "to": dst}

    # потери игрока (приоритеты фиолетовых карт, стр. 5)
    def _do_kill(self, game: Game, p: int, pd: dict) -> dict:
        opp = 1 - p
        regions = [r for r in REGION_KEYS if game.board_units[r][opp] > 0]
        if not regions:
            return {"type": "skip"}

        def near_bot(r: str) -> bool:
            return any(game.board_units[a][p] > 0 for a in ADJ[r])

        steps = [
            (
                "player has 1 unit and no fortress",
                lambda r: game.board_units[r][opp] == 1 and game.board_forts[r][opp] == 0,
            ),
            (
                "next to automa units, no fortress",
                lambda r: near_bot(r) and game.board_forts[r][opp] == 0,
            ),
            (
                "player has 1 unit and a fortress",
                lambda r: game.board_units[r][opp] == 1 and game.board_forts[r][opp] > 0,
            ),
            (
                "next to automa units, with a fortress",
                lambda r: near_bot(r) and game.board_forts[r][opp] > 0,
            ),
        ]
        for i, (label, ok) in enumerate(steps, start=1):
            cands = [r for r in regions if ok(r)]
            if cands:
                region = self._pick_by_die(cands, f"priority tie: {label}")
                self._t("kill", f"Losses: priority {i}, {label} → {REGION_RU[region]}")
                return {"type": "kill", "region": region}
        region = self._pick_by_die(regions, "whose unit to remove")
        self._t("kill", f"Losses: die → {REGION_RU[region]}")
        return {"type": "kill", "region": region}

    # снос крепости: где у игрока меньше всего юнитов (стр. 4/8)
    def _do_raze(self, game: Game, p: int) -> dict:
        opp = 1 - p
        regions = [r for r in REGION_KEYS if game.board_forts[r][opp] > 0]
        if not regions:
            return {"type": "skip"}
        fewest = min(game.board_units[r][opp] for r in regions)
        cands = [r for r in regions if game.board_units[r][opp] == fewest]
        region = self._pick_by_die(cands, "tie: fewest player units")
        self._t("raze", f"Fortress: fewest player units in {REGION_RU[region]}, destroyed")
        return {"type": "raze", "region": region}

    def _do_extra_offer(self) -> dict:
        if self.turn_repeat_granted:
            self._t("extra", "Track extra turn: repeat symbol already fired, declined")
            return {"type": "extra", "take": 0}
        self._t("extra", "Track extra turn: taken")
        return {"type": "extra", "take": 1}

    # жетоны рас: кубик решает (стр. 4); Серые Гавани — только верхний жетон
    def _do_choose_token(self, game: Game, pd: dict) -> dict:
        options = pd["options"]
        if str(pd.get("why", "")).startswith("Grey Havens"):
            self._t("token", "Grey Havens: takes the top token of the stack")
            return {"type": "pick_token", "token": options[0]}
        chosen = self._pick_by_die(options, "which race token to take")
        self._t("token", "Die picked a token")
        return {"type": "pick_token", "token": chosen}

    def _do_choose_race(self, game: Game) -> dict:
        races = [r for r in game.alliance_stacks if game.alliance_stacks[r]]
        if game.chapter == 3:
            late = [r for r in races if r in ("ents", "wizards")]
            if late:
                self._t("token", "Chapter 3: die only between Ents and Wizards")
                races = late
        race = self._pick_by_die(races, "which race stack")
        self._t("token", f"Grey Havens: race {RACE_RU[race]}")
        return {"type": "pick_race", "race": race}

    # Барад-Дур / жетон волшебников: сыграть из сброса по новой карте решения
    def _do_discard_play(self, game: Game, moves: list[dict]) -> dict:
        if not moves:
            return {"type": "skip"}
        dec = self._reveal()
        self._t("prio", "Play from discard: decision card colors, ties go to the latest chapter")
        cands_all = list(range(len(game.discard_open)))
        for slot in dec.priorities:
            colors = self.char.preferred if slot == PREF else slot
            cands = [i for i in cands_all if game.discard_open[i].type in colors]
            if cands:
                best_ch = max(game.discard_open[i].chapter for i in cands)
                cands = [i for i in cands if game.discard_open[i].chapter == best_ch]
                idx = self._pick_by_die(cands, "chapter tie")
                return {"type": "discard_play", "index": idx}
        best_ch = max(game.discard_open[i].chapter for i in cands_all)
        cands = [i for i in cands_all if game.discard_open[i].chapter == best_ch]
        idx = self._pick_by_die(cands, "no match, latest chapter")
        return {"type": "discard_play", "index": idx}

    # Изенгард: серую карту навыка, которого у игрока меньше всего (стр. 8)
    def _do_strip_grey(self, game: Game, p: int, moves: list[dict]) -> dict:
        if not moves:
            return {"type": "skip"}
        opp_cards = game.players[1 - p].played
        counts: dict[str, int] = {}
        for c in opp_cards:
            for s in (*c.skills, *c.skills_choice):
                counts[s] = counts.get(s, 0) + 1

        def score(m: dict) -> tuple:
            c = opp_cards[m["index"]]
            syms = (*c.skills, *c.skills_choice)
            fewest = min(counts.get(s, 0) for s in syms) if syms else 0
            return (fewest, -c.chapter, 0 if c.gives_link else 1)

        best = min(moves, key=score)
        self._t("strip", f"Isengard: takes {best['label']}")
        return best

    # Шир: обзор слева-направо сверху-вниз, но по приоритетам карты решения
    def _do_shire(self, game: Game, moves: list[dict]) -> dict:
        if not moves:
            return {"type": "skip"}
        dec = self._reveal()
        slots = game.tableau.slots
        order = sorted((m["slot"] for m in moves), key=lambda sid: (slots[sid].row, slots[sid].x))
        for slot in dec.priorities:
            colors = self.char.preferred if slot == PREF else slot
            matches = [sid for sid in order if game.tableau.cards[sid].type in colors]
            if matches:
                self._t("prio", f"The Shire: {self._card_ru(game, matches[0])}")
                return next(m for m in moves if m["slot"] == matches[0])
        self._t("prio", f"The Shire: no match, first visible {self._card_ru(game, order[0])}")
        return next(m for m in moves if m["slot"] == order[0])

    # Гронд: крепость там, где у игрока больше всего юнитов (стр. 8)
    def _do_grond_pick(self, game: Game, p: int, moves: list[dict]) -> dict:
        if not moves:
            return {"type": "skip"}
        opp = 1 - p
        best = max(game.board_units[m["region"]][opp] for m in moves)
        cands = [m for m in moves if game.board_units[m["region"]][opp] == best]
        chosen = self._pick_by_die(cands, "tie: most player units")
        self._t("raze", f"Grond: assault on {REGION_RU[chosen['region']]}")
        return chosen

    def _do_grond_retreat(self, game: Game, p: int, pd: dict, moves: list[dict]) -> dict:
        opp = 1 - p
        occupied = [m for m in moves if game.present(opp, m["to"])]
        cands = occupied or moves
        chosen = self._pick_by_die(cands, "where player units retreat")
        self._t("raze", f"Grond: player retreats to {REGION_RU[chosen['to']]}")
        return chosen

    # жетон энтов «3 раза»: кубик выбирает эффект (стр. 7)
    def _do_ents_menu(self, game: Game, p: int, moves: list[dict]) -> dict:
        kinds = []
        if any(m["type"] == "ents_kill" for m in moves):
            kinds.append("kill")
        if any(m["type"] == "ents_coin" for m in moves):
            kinds.append("coin")
        if any(m["type"] == "ents_move" for m in moves):
            kinds.append("move")
        if not kinds:
            return {"type": "skip"}
        roll = self._die("Ents effect: 1-2 unit, 3-4 coin, 5-6 move")
        want = ("kill", "kill", "coin", "coin", "move", "move")[roll - 1]
        if want not in kinds:
            want = kinds[(roll - 1) % len(kinds)]
            self._t("token", "Rolled effect unavailable, using the nearest available")
        if want == "coin":
            self._t("token", "Ents: player loses a coin")
            return {"type": "ents_coin"}
        if want == "kill":
            mv = self._do_kill(game, p, {"n": 1})
            if mv["type"] == "kill":
                return {"type": "ents_kill", "region": mv["region"]}
            return {"type": "skip"}
        mv = self._do_move(game, p, {"n": 1})
        if mv["type"] == "move":
            return {"type": "ents_move", "from": mv["from"], "to": mv["to"]}
        return {"type": "skip"}
