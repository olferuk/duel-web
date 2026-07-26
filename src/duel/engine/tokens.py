"""Component-token encoding for transformer models (ZeusAI-style).

State -> sequence of 46 tokens, each a fixed 40-dim feature vector plus an
integer type id. No hand-crafted cross-features: the attention layers are
expected to discover interactions.

Token layout:
  0        global (chapter, reserve, tempo, pending)
  1..2     players (me, opp)
  3        quest
  4..23    tableau slots 0..19
  24..32   landmark tiles (9)
  33..39   regions (7)
  40..45   alliance stacks (6)
"""

import numpy as np

from duel.engine.cards import Card
from duel.engine.encoding import CARD_TYPES, RACES, SKILLS
from duel.engine.game import REGION_KEYS, Game
from duel.engine.landmarks import LANDMARKS
from duel.engine.quest import FRODO_START, HALF_STEPS

F = 44  # per-token feature dim
N_TOKENS = 1 + 2 + 1 + 20 + 9 + 7 + 6  # 46

TYPE_GLOBAL, TYPE_PLAYER, TYPE_QUEST, TYPE_SLOT, TYPE_TILE, TYPE_REGION, TYPE_STACK = range(7)

TOKEN_TYPES = np.array(
    [TYPE_GLOBAL, TYPE_PLAYER, TYPE_PLAYER, TYPE_QUEST]
    + [TYPE_SLOT] * 20
    + [TYPE_TILE] * 9
    + [TYPE_REGION] * 7
    + [TYPE_STACK] * 6,
    dtype=np.int64,
)


def _card_feats(g: Game, p: int, card: Card, out: np.ndarray) -> None:
    """Fills a 40-dim card descriptor."""
    out[CARD_TYPES.index(str(card.type))] = 1.0
    for s in card.cost_skills:
        out[6 + SKILLS.index(s)] += 0.34
    out[11] = card.cost_coins / 3
    cost = g.card_cost(p, card)
    out[12] = min(cost["coins"], 8) / 8
    out[13] = 1.0 if cost["chained"] else 0.0
    out[14] = 1.0 if cost["coins"] <= g.players[p].coins else 0.0
    out[15] = card.coins / 5
    out[16] = card.quest_steps / 3
    out[17] = card.troops / 3
    if card.race:
        out[18 + RACES.index(card.race)] = 1.0
    for s in card.skills:
        out[24 + SKILLS.index(s)] += 0.5
    for s in card.skills_choice:
        out[24 + SKILLS.index(s)] += 0.25
    for r in card.destinations:
        out[29 + REGION_KEYS.index(r)] = 1.0
    out[36] = 1.0 if card.gives_link else 0.0
    out[37] = 1.0 if card.takes_link else 0.0
    out[38] = card.movements / 3
    out[39] = (card.opp_coins_lost + card.casualties) / 3


def encode_tokens(g: Game, p: int) -> np.ndarray:
    o = 1 - p
    T = np.zeros((N_TOKENS, F), dtype=np.float32)

    # global
    t = T[0]
    t[g.chapter - 1] = 1.0
    t[3] = g.reserve / 25
    t[4] = 1.0 if g.current == p else 0.0
    t[5] = min(g.extra_turns, 2) / 2
    t[6] = len(g.tableau.taken) / 20
    t[7] = 1.0 if g.pending else 0.0
    t[8] = g.rules["discard_payout"][g.chapter - 1] / 4

    # players
    for k, pp in ((1, p), (2, o)):
        pl = g.players[pp]
        t = T[k]
        agg = pl._aggregates()
        t[0] = 1.0 if k == 1 else 0.0  # is-me
        t[1] = min(pl.coins, 20) / 10
        t[2] = g.presence_count(pp) / 7
        t[3] = pl.race_symbols_for_victory() / 6
        for race, cnt in agg["races"].items():
            t[4 + RACES.index(race)] = cnt / 2
        for s, cnt in agg["fixed"].items():
            t[10 + SKILLS.index(s)] = cnt / 3
        t[15] = len(agg["groups"]) / 3
        t[16] = len(agg["links"]) / 8
        t[17] = len(pl.tokens) / 4
        t[18] = g.supply(pp) / 15
        t[19] = g.forts_on_board(pp) / 3
        prog = (g.quest.frodo - FRODO_START) if pp == 0 else g.quest.nazgul_progress
        t[20] = prog / HALF_STEPS
        t[21] = len(pl.played) / 25

    # quest
    t = T[3]
    t[0] = (g.quest.frodo - FRODO_START) / HALF_STEPS
    t[1] = g.quest.nazgul_progress / HALF_STEPS
    t[2] = g.quest.gap / HALF_STEPS

    # slots
    tab = g.tableau
    for i in range(20):
        t = T[4 + i]
        present = i not in tab.taken
        t[0] = 1.0 if present else 0.0
        if not present:
            continue
        revealed = i in tab.revealed
        t[1] = 1.0 if revealed else 0.0
        t[2] = 1.0 if tab.is_available(i) else 0.0
        t[3] = tab.slots[i].row / 6
        if revealed:
            sub = np.zeros(40, dtype=np.float32)
            _card_feats(g, p, tab.cards[i], sub)
            t[4:44] = sub

    # tiles
    for j, lm in enumerate(LANDMARKS):
        t = T[24 + j]
        faceup = lm.id in g.landmarks_faceup
        t[0] = 1.0 if faceup else 0.0
        t[1] = 1.0 if lm.id in g.landmarks_deck else 0.0
        t[2] = 1.0 if lm.id in g.players[p].landmarks else 0.0
        t[3] = 1.0 if lm.id in g.players[o].landmarks else 0.0
        if lm.region:
            t[4 + REGION_KEYS.index(lm.region)] = 1.0
        t[11] = lm.units / 3
        t[12] = lm.coins / 5
        t[13] = lm.movements / 2
        t[14] = lm.quest_steps / 2
        t[15] = 1.0 if lm.effect else 0.0
        if faceup:
            cost = g.tile_cost(p, lm)["coins"]
            t[16] = min(cost, 10) / 10
            t[17] = 1.0 if cost <= g.players[p].coins else 0.0

    # regions
    for j, r in enumerate(REGION_KEYS):
        t = T[33 + j]
        t[0] = min(g.board_units[r][p], 6) / 6
        t[1] = min(g.board_units[r][o], 6) / 6
        t[2] = g.board_forts[r][p] / 2
        t[3] = g.board_forts[r][o] / 2
        t[4 + j] = 1.0  # region identity

    # alliance stacks
    from duel.engine.alliances import TOKENS as _ALL_TOKENS

    tok_idx = {tk.id: i for i, tk in enumerate(_ALL_TOKENS)}
    for j, race in enumerate(RACES):
        t = T[40 + j]
        t[0] = len(g.alliance_stacks[race]) / 3
        t[1 + j] = 1.0
        for tok in g.alliance_stacks[race]:
            # which exact tokens remain (public info), stable indexing 0..17
            t[10 + tok_idx[tok] % 18] = 1.0

    return T
