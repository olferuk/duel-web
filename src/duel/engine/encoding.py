"""Fixed-size vector encoding of a game state, from one player's perspective.

`encode(game, p)` returns a float32 vector; `FEATURE_NAMES` names every
component (len(FEATURE_NAMES) == OBS_SIZE). Sections:

- globals: chapter, discard value, reserve, extra turns, pending type
- per player (me, then opponent): coins, presence, races, skills, links,
  passive tokens, supplies, quest progress
- victory proximity (engineered): steps left to each of the 3 victories
- board: units/fortresses per region, both sides, contested flag
- quest: gap, distance/type of next own bonus for both characters
- tableau: 20 slots x card features (costs computed for "me")
- landmarks: 9 tiles x (status, my cost, effects)
- alliance stacks: remaining tokens per race

Facedown tableau cards contribute only structural flags (present/covered),
not identity — the encoding respects the game's hidden information.
"""

import numpy as np

from duel.engine.alliances import TOKENS
from duel.engine.cards import Card, CardType
from duel.engine.game import REGION_KEYS, Game
from duel.engine.landmarks import LANDMARKS
from duel.engine.quest import FRODO_START, HALF, HALF_STEPS, Space

SKILLS = ["Face", "Fist", "Heart", "Crown", "Book"]
RACES = ["elves", "ents", "hobbits", "humans", "dwarves", "wizards"]
LINKS = [
    "Pot",
    "Anvil",
    "Horseshoe",
    "Harp",
    "Horse",
    "Backpack",
    "Fish",
    "Bow And Arrow",
    "Sword",
    "Helmet",
    "Chest",
    "Acorn",
    "Scroll",
    "Campfire",
    "Sleeping Bag",
    "Chest Mail",
    "Ax",
]
PASSIVE_TOKENS = [t.id for t in TOKENS if t.kind == "passive"]
CARD_TYPES = [
    str(t)
    for t in (
        CardType.GREY,
        CardType.YELLOW,
        CardType.GREEN,
        CardType.BLUE,
        CardType.RED,
        CardType.PURPLE,
    )
]
PENDING_TYPES = [
    "place_units",
    "movements",
    "casualties",
    "remove_fortress",
    "choose_token",
    "choose_race",
    "play_from_discard",
    "discard_opp_grey",
    "shire_play",
    "grond_pick",
    "grond_retreat",
    "ents_menu",
]
TILE_EFFECTS = [
    "play_from_discard",
    "grey_havens_tokens",
    "discard_opp_grey",
    "shire_play_visible",
    "grond_assault",
]
MAX_SLOTS = 20
BONUS_KINDS = [Space.COIN, Space.UNIT, Space.EXTRA_TURN, Space.DESTROY_FORTRESS]


class _Builder:
    """Accumulates values; optionally records feature names."""

    __slots__ = ("names", "values")

    def __init__(self, record_names: bool = False) -> None:
        self.values: list[float] = []
        self.names: list[str] | None = [] if record_names else None

    def add(self, name: str, value: float) -> None:
        if self.names is not None:
            self.names.append(name)
        self.values.append(value)

    def one_hot(self, prefix: str, options: list, value) -> None:
        for opt in options:
            self.add(f"{prefix}={opt}", 1.0 if opt == value else 0.0)


def _own_progress(game: Game, p: int) -> int:
    """Steps the player's character has made on its own half (0..14)."""
    return game.quest.frodo - FRODO_START if p == 0 else game.quest.nazgul_progress


def _next_bonus_distance(progress: int) -> tuple[int, Space | None]:
    for d in range(1, HALF_STEPS - progress + 1):
        idx = progress + d
        if idx < len(HALF) and HALF[idx] in BONUS_KINDS:
            return d, HALF[idx]
    return HALF_STEPS, None


def _encode_player(b: _Builder, game: Game, p: int, tag: str) -> None:
    pl = game.players[p]
    races = pl.race_counts
    b.add(f"{tag}.coins", min(pl.coins, 20) / 10)
    b.add(f"{tag}.presence", game.presence_count(p) / 7)
    b.add(f"{tag}.races_distinct", len(races) / 6)
    b.add(f"{tag}.race_victory", pl.race_symbols_for_victory() / 6)
    for race in RACES:
        b.add(f"{tag}.race.{race}", races.get(race, 0) / 2)
    fixed, groups, wilds = pl.skill_pool()
    for s in SKILLS:
        b.add(f"{tag}.skill.{s}", fixed.get(s, 0) / 3)
    b.add(f"{tag}.skill_groups", len(groups) / 3)
    b.add(f"{tag}.skill_wild", float(wilds))
    links = pl.links
    for link in LINKS:
        b.add(f"{tag}.link.{link}", 1.0 if link in links else 0.0)
    for tok in PASSIVE_TOKENS:
        b.add(f"{tag}.token.{tok}", 1.0 if tok in pl.tokens else 0.0)
    b.add(f"{tag}.tokens_total", len(pl.tokens) / 4)
    b.add(f"{tag}.used_three_diff", 1.0 if pl.used_three_diff else 0.0)
    b.add(f"{tag}.units_supply", game.supply(p) / 15)
    b.add(f"{tag}.forts_on_board", game.forts_on_board(p) / 3)
    b.add(f"{tag}.cards_played", len(pl.played) / 25)
    b.add(f"{tag}.grey_cards", pl._aggregates()["grey"] / 8)
    b.add(f"{tag}.quest_progress", _own_progress(game, p) / HALF_STEPS)


def _encode_victory_proximity(b: _Builder, game: Game, p: int, tag: str) -> None:
    quest_left = (HALF_STEPS - _own_progress(game, p)) / HALF_STEPS
    races_left = max(0, 6 - game.players[p].race_symbols_for_victory()) / 6
    regions_left = (7 - game.presence_count(p)) / 7
    b.add(f"{tag}.quest_left", quest_left)
    b.add(f"{tag}.races_left", races_left)
    b.add(f"{tag}.regions_left", regions_left)
    b.add(f"{tag}.best_victory_closeness", min(quest_left, races_left, regions_left))


def _encode_card(b: _Builder, game: Game, p: int, card: Card, tag: str) -> None:
    b.one_hot(f"{tag}.type", CARD_TYPES, str(card.type))
    cost = game.card_cost(p, card)
    b.add(f"{tag}.my_cost", min(cost["coins"], 8) / 8)
    b.add(f"{tag}.chained", 1.0 if cost["chained"] else 0.0)
    b.add(f"{tag}.affordable", 1.0 if cost["coins"] <= game.players[p].coins else 0.0)
    b.add(f"{tag}.gives_link", 1.0 if card.gives_link else 0.0)
    b.add(f"{tag}.opp_would_chain", 1.0 if card.takes_link in game.players[1 - p].links else 0.0)
    b.add(f"{tag}.coins", card.coins / 5)
    b.add(f"{tag}.quest_steps", card.quest_steps / 3)
    b.add(f"{tag}.troops", card.troops / 3)
    for s in SKILLS:
        n = card.skills.count(s) + (0.5 if s in card.skills_choice else 0.0)
        b.add(f"{tag}.skill.{s}", n / 2)
    b.one_hot(f"{tag}.race", [*RACES, None], card.race)
    for r in REGION_KEYS:
        b.add(f"{tag}.dest.{r}", 1.0 if r in card.destinations else 0.0)
    b.add(f"{tag}.movements", card.movements / 3)
    b.add(f"{tag}.opp_coins_lost", card.opp_coins_lost / 3)
    b.add(f"{tag}.casualties", card.casualties / 2)


CARD_FEATURES = 6 + 8 + 5 + 7 + 7 + 3  # keep in sync with _encode_card


def _encode_into(b: _Builder, game: Game, p: int) -> None:
    o = 1 - p

    b.one_hot("chapter", [1, 2, 3], game.chapter)
    mult = 2 if "humans_double_discard" in game.players[p].tokens else 1
    b.add("discard_gain", game.chapter * mult / 6)
    b.add("reserve", game.reserve / 25)
    b.add("extra_turns", min(game.extra_turns, 2) / 2)
    b.add("my_turn", 1.0 if game.current == p else 0.0)
    head = game.pending[0] if game.pending else None
    b.one_hot("pending", [*PENDING_TYPES, None], head["type"] if head else None)
    b.add("pending_n", (head.get("n", 0) if head else 0) / 3)
    b.add("pending_mine", 1.0 if head and head["player"] == p else 0.0)

    _encode_player(b, game, p, "me")
    _encode_player(b, game, o, "opp")
    _encode_victory_proximity(b, game, p, "me")
    _encode_victory_proximity(b, game, o, "opp")

    for r in REGION_KEYS:
        b.add(f"board.{r}.my_units", min(game.board_units[r][p], 6) / 6)
        b.add(f"board.{r}.opp_units", min(game.board_units[r][o], 6) / 6)
        b.add(f"board.{r}.my_forts", game.board_forts[r][p] / 2)
        b.add(f"board.{r}.opp_forts", game.board_forts[r][o] / 2)
        b.add(f"board.{r}.contested", 1.0 if game.present(p, r) and game.present(o, r) else 0.0)

    b.add("quest.gap", game.quest.gap / HALF_STEPS)
    for tag, pp in (("me", p), ("opp", o)):
        d, kind = _next_bonus_distance(_own_progress(game, pp))
        b.add(f"quest.{tag}.next_bonus_dist", d / HALF_STEPS)
        b.one_hot(
            f"quest.{tag}.next_bonus",
            [str(k) for k in BONUS_KINDS] + [None],
            str(kind) if kind else None,
        )

    for i in range(MAX_SLOTS):
        tag = f"slot{i:02d}"
        present = i not in game.tableau.taken
        revealed = present and i in game.tableau.revealed
        available = present and game.tableau.is_available(i)
        b.add(f"{tag}.present", 1.0 if present else 0.0)
        b.add(f"{tag}.revealed", 1.0 if revealed else 0.0)
        b.add(f"{tag}.available", 1.0 if available else 0.0)
        if revealed:
            _encode_card(b, game, p, game.tableau.cards[i], tag)
        else:
            for j in range(CARD_FEATURES):
                b.add(f"{tag}.card{j}", 0.0)

    for lm in LANDMARKS:
        tag = f"tile.{lm.id}"
        faceup = lm.id in game.landmarks_faceup
        cost = game.tile_cost(p, lm)["coins"] if faceup else 0
        b.add(f"{tag}.faceup", 1.0 if faceup else 0.0)
        b.add(f"{tag}.in_deck", 1.0 if lm.id in game.landmarks_deck else 0.0)
        b.add(f"{tag}.my_cost", min(cost, 10) / 10 if faceup else 0.0)
        b.add(f"{tag}.affordable", 1.0 if faceup and cost <= game.players[p].coins else 0.0)
        b.one_hot(f"{tag}.region", [*REGION_KEYS, None], lm.region)
        b.add(f"{tag}.units", lm.units / 3)
        b.add(f"{tag}.coins", lm.coins / 5)
        b.add(f"{tag}.movements", lm.movements / 2)
        b.add(f"{tag}.quest_steps", lm.quest_steps / 2)
        b.one_hot(f"{tag}.effect", [*TILE_EFFECTS, None], lm.effect)

    for race in RACES:
        b.add(f"alliance.{race}.remaining", len(game.alliance_stacks[race]) / 3)

    _encode_extra(b, game, p)


def _encode_extra(b: _Builder, game: Game, p: int) -> None:
    """Extended feature groups (x1..x12), appended AFTER the v1 block so old
    models keep working on the feature prefix. Each group carries an `xN.`
    prefix for ablation masking."""
    from duel.engine.cards import BY_CHAPTER

    o = 1 - p
    tab = game.tableau

    # ---- x1: unseen pool of the current chapter (deck accounting) ----
    seen: set[str] = set()
    for sid in tab.revealed:
        if sid not in tab.taken:
            seen.add(tab.cards[sid].id)
    for pl in game.players:
        for c in pl.played:
            if c.chapter == game.chapter:
                seen.add(c.id)
    for c in game.discard_open:
        if c.chapter == game.chapter:
            seen.add(c.id)
    unseen = [c for c in BY_CHAPTER[game.chapter] if c.id not in seen]
    n_unseen = max(len(unseen), 1)
    for t in CARD_TYPES:
        b.add(f"x1.unseen.type={t}", sum(1 for c in unseen if str(c.type) == t) / n_unseen)
    for race in RACES:
        b.add(f"x1.unseen.race={race}", sum(1 for c in unseen if c.race == race) / 2)
    b.add("x1.unseen.n", len(unseen) / 23)
    b.add("x1.unseen.links", sum(1 for c in unseen if c.gives_link) / 6)
    b.add("x1.unseen.quest", sum(c.quest_steps for c in unseen) / 8)
    b.add("x1.unseen.troops", sum(c.troops for c in unseen) / 10)

    # ---- x2: exact alliance stack contents (public info) ----
    from duel.engine.alliances import TOKENS as _TOKENS

    for tk in _TOKENS:
        b.add(f"x2.instack.{tk.id}", 1.0 if tk.id in game.alliance_stacks[tk.race] else 0.0)
    b.add("x2.eagle_in_stack", 1.0 if "hobbits_eagle" in game.alliance_stacks["hobbits"] else 0.0)

    # ---- x3: tableau geometry: what does taking each slot unlock ----
    for i in range(MAX_SLOTS):
        slot = tab.slots[i] if i < len(tab.slots) else None
        if slot is None or i in tab.taken:
            b.add(f"x3.slot{i:02d}.unlocks", 0.0)
            b.add(f"x3.slot{i:02d}.depth", 0.0)
            continue
        unlocks = 0
        for below in slot.covers:
            others = [c for c in tab.slots[below].covered_by if c != i]
            if all(c in tab.taken for c in others):
                unlocks += 1
        b.add(f"x3.slot{i:02d}.unlocks", unlocks / 2)
        b.add(f"x3.slot{i:02d}.depth", slot.row / 6)

    # ---- x4: opponent affordability of visible cards ----
    for i in range(MAX_SLOTS):
        if i < len(tab.slots) and i not in tab.taken and i in tab.revealed:
            cost_o = game.card_cost(o, tab.cards[i])
            b.add(f"x4.slot{i:02d}.opp_cost", min(cost_o["coins"], 8) / 8)
            b.add(
                f"x4.slot{i:02d}.opp_afford",
                1.0 if cost_o["coins"] <= game.players[o].coins else 0.0,
            )
        else:
            b.add(f"x4.slot{i:02d}.opp_cost", 0.0)
            b.add(f"x4.slot{i:02d}.opp_afford", 0.0)

    # ---- x5: imminent-victory threat flags ----
    for tag, pp in (("me", p), ("opp", o)):
        pl = game.players[pp]
        b.add(f"x5.{tag}.races5", 1.0 if pl.race_symbols_for_victory() >= 5 else 0.0)
        b.add(f"x5.{tag}.presence6", 1.0 if game.presence_count(pp) >= 6 else 0.0)
        left = HALF_STEPS - _own_progress(game, pp)
        b.add(f"x5.{tag}.quest3", 1.0 if left <= 3 else 0.0)
        b.add(f"x5.{tag}.quest1", 1.0 if left <= 1 else 0.0)

    # ---- x6: board expansion potential ----
    from duel.engine.game import ADJ

    for tag, pp in (("me", p), ("opp", o)):
        frontier = sum(
            1
            for r in REGION_KEYS
            if not game.present(pp, r) and any(game.present(pp, a) for a in ADJ[r])
        )
        b.add(f"x6.{tag}.frontier", frontier / 7)

    # ---- x7: chapter tempo ----
    cards_left = len(tab.slots) - len(tab.taken)
    b.add("x7.cards_left", cards_left / 20)
    b.add("x7.i_take_last", 1.0 if (cards_left % 2 == 1) == (game.current == p) else 0.0)
    b.add("x7.last_chapter", 1.0 if game.chapter == 3 else 0.0)

    # ---- x8: economic edges ----
    b.add("x8.coins_diff", max(-10, min(10, game.players[p].coins - game.players[o].coins)) / 10)
    b.add("x8.forts_diff", (game.forts_on_board(p) - game.forts_on_board(o)) / 3)
    payout = game.rules["discard_payout"][game.chapter - 1]
    b.add("x8.payout", payout / 4)

    # ---- x9: market composition + my token synergy ----
    visible = [tab.cards[i] for i in tab.revealed if i not in tab.taken]
    for t in CARD_TYPES:
        b.add(f"x9.visible.type={t}", sum(1 for c in visible if str(c.type) == t) / 6)
    syn = {
        "elves_extra_turn": "yellow",
        "humans_yellow_quest": "yellow",
        "dwarves_green_moves": "green",
        "hobbits_blue_unit": "blue",
        "humans_red_extra": "red",
        "elves_red_any": "red",
    }
    for tag, pp in (("me", p), ("opp", o)):
        s = sum(
            sum(1 for c in visible if str(c.type) == want)
            for tok, want in syn.items()
            if tok in game.players[pp].tokens
        )
        b.add(f"x9.{tag}.synergy", min(s, 10) / 10)

    # ---- x10: chain access to the visible market ----
    for tag, pp in (("me", p), ("opp", o)):
        links = game.players[pp].links
        b.add(f"x10.{tag}.chainable", sum(1 for c in visible if c.takes_link in links) / 4)

    # ---- x11: quest bonuses still ahead ----
    from duel.engine.quest import HALF

    for tag, pp in (("me", p), ("opp", o)):
        prog = _own_progress(game, pp)
        ahead = sum(1 for i2 in range(prog + 1, len(HALF)) if HALF[i2] in BONUS_KINDS)
        b.add(f"x11.{tag}.bonuses_ahead", ahead / 4)

    # ---- x12: global phase clock ----
    total_taken = (game.chapter - 1) * 20 + len(tab.taken)
    b.add("x12.phase", total_taken / 60)


def encode(game: Game, p: int) -> np.ndarray:
    b = _Builder()
    _encode_into(b, game, p)
    return np.asarray(b.values, dtype=np.float32)


def _compute_names() -> list[str]:
    b = _Builder(record_names=True)
    _encode_into(b, Game(seed=0), 0)
    assert b.names is not None
    return b.names


FEATURE_NAMES: list[str] = _compute_names()
OBS_SIZE = len(FEATURE_NAMES)
