"""Web server: lobby (vs-bot / PvP-by-link / hot-seat), rooms API + static UI."""

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from duel.engine.automa import CHARACTERS, Automa, automa_rules
from duel.engine.board import EDGES, RACES, REGIONS
from duel.engine.game import Game

STATIC = Path(__file__).parent / "static"

# public-hosting mode: legacy global endpoints off, curated bots only, CSP on
PUBLIC = os.environ.get("DUEL_PUBLIC") == "1"

app = FastAPI(title="Дуэль за Средиземье", docs_url=None if PUBLIC else "/docs", redoc_url=None)

# ---- basic abuse protection (public internet is full of bored kids) ----
RATE_WINDOW = 10.0  # seconds
RATE_LIMIT = 40  # API requests per window per IP (polling is ~8/10s)
MAX_BODY = 64 * 1024
MAX_ROOMS = 300
MAX_ROOMS_PER_IP = 8
_RATE: dict[str, deque] = defaultdict(deque)
# CPU guard: only this many bot searches at once; the rest wait briefly or 503
_BOT_SLOTS = threading.BoundedSemaphore(4)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("fly-client-ip") or request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


@app.middleware("http")
async def hardening(request: Request, call_next):
    if request.url.path.startswith("/api"):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY:
            return JSONResponse({"detail": "payload too large"}, status_code=413)
        ip = _client_ip(request)
        now = time.time()
        if len(_RATE) > 20_000:  # crude memory bound
            _RATE.clear()
        q = _RATE[ip]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return JSONResponse({"detail": "слишком много запросов, притормози"}, status_code=429)
        q.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if PUBLIC:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


def _legacy_guard() -> None:
    """The old single-global-game endpoints are hot-seat debug only: on a public
    host they would let strangers reset each other's game — hide them."""
    if PUBLIC:
        raise HTTPException(404)


state: dict = {"game": None}


class NewGame(BaseModel):
    seed: int | None = None
    promo: bool = False


class MoveBody(BaseModel):
    move: dict


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/board")
def board() -> dict:
    return {"regions": REGIONS, "edges": EDGES, "races": RACES}


@app.post("/api/game/new")
def new_game(body: NewGame) -> dict:
    _legacy_guard()
    state["game"] = Game(seed=body.seed, promo=body.promo)
    return state["game"].to_dict()


@app.get("/api/game")
def get_game() -> dict:
    _legacy_guard()
    if state["game"] is None:
        return {"empty": True}
    return state["game"].to_dict()


BOT_MENU = [
    # ELO — из единой лестницы recompute_elo() от 03.08.2026 (включая матчи автом:
    # владелец решил, что лестница общая — мера «сложности для игрока», а не режима)
    {
        "id": "galadriel",
        "label": "👑 Галадриэль · ELO ≈1250",
        "desc": "Владычица Лориэна, шестое воплощение династии: союзы шести рас (MCTS-240)",
    },
    {
        "id": "champion",
        "label": "Гэндальф · ELO ≈1100",
        "desc": "Экс-чемпион: глубокий поиск (MCTS-240) + нейросеть w3. Честный, без подглядываний",
    },
    {
        "id": "strong",
        "label": "Элронд · ELO ≈990",
        "desc": "Тот же мозг, что у Гэндальфа, но вдвое меньше раздумий (MCTS-120 + w3)",
    },
    {
        "id": "mcts",
        "label": "Арагорн · ELO ≈1030",
        "desc": "Опытный следопыт: классический Монте-Карло с ручной эвристикой, без нейросетей",
    },
    {
        "id": "frodo",
        "label": "Фродо · ELO ≈1010 · стиль: Кольцо",
        "desc": "Верен миссии: рвётся по Пути Кольца к Роковой горе, порой в ущерб всему прочему",
    },
    {
        "id": "witch_king",
        "label": "Король-чародей · ELO ≈1105 · стиль: война",
        "desc": "Агрессор: армии, крепости и захват регионов прежде всего",
    },
    {
        "id": "gollum",
        "label": "Голлум · ELO ≈1070 · стиль: прелесть",
        "desc": "Копит золото и ищет выгоду. Моя пре-е-елесть",
    },
    {
        "id": "2ply",
        "label": "Боромир · ELO ≈920",
        "desc": "Смотрит на свой ход и твой ответ — но не дальше (минимакс на 2 хода)",
    },
    {
        "id": "greedy",
        "label": "Гимли · ELO ≈790",
        "desc": "Жадина: берёт лучшее прямо сейчас, не думая о будущем",
    },
    {
        "id": "random",
        "label": "Пиппин · ELO ≈95",
        "desc": "Дурак Тука: ходит наугад. Идеален для знакомства с правилами",
    },
]


def _automa_desc(cid: str) -> str:
    from duel.engine.automa import COLOR_RU, REPEAT_RU

    ch = CHARACTERS[cid]
    pref = "/".join(COLOR_RU[t] for t in sorted(ch.preferred, key=str))
    parts = [ch.power_ru, f"предпочитает {pref} карты"]
    if ch.repeats:
        parts.append("повтор хода: " + " и ".join(REPEAT_RU[r] for r in sorted(ch.repeats)))
    return "; ".join(parts)


# Соло-вариант: автома играет по печатным правилам (карты решений + кубик d6),
# а не как обычные боты — отдельная группа в лобби.
# ELO измерен ареной 03.08.2026 (analysis/automa_eval*.py, ~14k партий):
# сила — от льготных правил соло-режима (бесплатные карты), не от качества решений.
AUTOMA_ELO = {
    "witch_king": 1200,
    "galadriel": 1170,
    "tom_bombadil": 1090,
    "saruman": 1155,
    "elrond": 1110,
    "smaug": 1135,
    "sauron": 1475,
    "gandalf": 1465,
    "eowyns_stew": 1380,
}
AUTOMA_MENU = [
    {
        "id": f"automa-{cid}",
        "label": f"{ch.name_ru} · ELO ≈{AUTOMA_ELO[cid]}",
        "desc": _automa_desc(cid),
        "group": "automa",
        "art": f"/static/art/solo/{ch.art}",
    }
    # сильнейшие первыми, как в основном меню
    for cid, ch in sorted(CHARACTERS.items(), key=lambda kv: -AUTOMA_ELO[kv[0]])
]
BOT_MENU = BOT_MENU + AUTOMA_MENU


@app.get("/api/bots")
def list_bots() -> dict:
    from duel.ai.onnx_net import MODELS

    nets = (
        sorted({p.stem for pat in ("*.pt", "*.onnx") for p in MODELS.glob(pat)})
        if MODELS.exists()
        else []
    )
    bots = ["greedy", "mcts", *[f"net-{n}" for n in nets]]
    if "v8" in nets:
        bots = ["mcts300-v8", "mcts120-v8", *bots]
    if "w3" in nets:
        bots = ["mcts300-w3", "mcts120-w3", *bots]  # reigning champion first
    net_needed = {"champion", "strong", "frodo", "witch_king", "galadriel", "gollum"}
    menu = [m for m in BOT_MENU if m["id"] not in net_needed or "w3" in nets]
    return {"bots": bots, "menu": menu}


_BOTS: dict = {}


def _get_bot(kind: str):

    if kind in _BOTS:
        return _BOTS[kind]
    bot = _make_bot(kind, seed=7)
    _BOTS[kind] = bot
    return bot


_NETS: dict = {}


def _get_net(model: str):
    """Net-like with .values(); torch checkpoint or ONNX depending on the image."""
    if model not in _NETS:
        if os.environ.get("DUEL_ONNX") == "1":
            from duel.ai.onnx_net import OnnxValueNet

            _NETS[model] = OnnxValueNet(model)
        else:
            try:
                from duel.ai.value_net import ValueNet

                _NETS[model] = ValueNet.load(model)
            except ImportError:  # torch-free image: fall back to onnxruntime
                from duel.ai.onnx_net import OnnxValueNet

                _NETS[model] = OnnxValueNet(model)
    return _NETS[model]


def _net_eval(model: str):
    from duel.engine.encoding import encode

    net = _get_net(model)

    def ev(state):
        return float(net.values(encode(state, 0)[None, :])[0])

    return ev


def _make_bot(kind: str, seed: int = 7):
    """Fresh bot instance. All search bots are HONEST (PIMC, no RNG peeking):
    against humans clairvoyance is cheating, and the web is for humans."""
    import re

    if kind.startswith("automa-"):
        cid = kind[len("automa-") :]
        if cid not in CHARACTERS:
            raise HTTPException(400, f"неизвестный персонаж автомы {cid!r}")
        return Automa(cid, seed=seed)

    from duel.ai.mcts import HonestMctsBot

    if kind == "champion":
        return HonestMctsBot(sims=240, seed=seed, name=kind, eval_fn=_net_eval("w3"), worlds=4)
    if kind == "strong":
        return HonestMctsBot(sims=120, seed=seed, name=kind, eval_fn=_net_eval("w3"), worlds=4)
    if kind == "mcts":
        return HonestMctsBot(sims=150, seed=seed, name="mcts150-heur", leaf="heuristic", worlds=4)
    if kind == "galadriel":
        try:
            ev = _net_eval("gala_best")  # актуальная чемпионка династии (Γ³)
        except Exception:
            from duel.ai.personality import personality_eval

            ev = personality_eval(_get_net("w3"), "galadriel")
        return HonestMctsBot(sims=240, seed=seed, name=kind, eval_fn=ev, worlds=4)
    if kind in ("frodo", "witch_king", "gollum"):
        # предпочитаем персонально обученную сеть p_<kind>; до её появления —
        # базовая w3 с наклоном оценки к стилю персонажа
        try:
            ev = _net_eval(f"p_{kind}")
        except Exception:  # персональной сети ещё нет — базовая w3 с наклоном
            from duel.ai.personality import personality_eval

            ev = personality_eval(_get_net("w3"), kind)
        return HonestMctsBot(sims=120, seed=seed, name=kind, eval_fn=ev, worlds=4)
    if kind == "2ply":
        from duel.ai.bots import TwoPlyBot

        return TwoPlyBot(seed=seed)
    if kind == "greedy":
        from duel.ai.bots import GreedyBot

        return GreedyBot(seed=seed)
    if kind == "random":
        from duel.ai.bots import RandomBot

        return RandomBot(seed=seed)
    if m := re.fullmatch(r"mcts(\d+)-(\w+)", kind):
        sims, model = int(m.group(1)), m.group(2)
        return HonestMctsBot(sims=sims, seed=seed, name=kind, eval_fn=_net_eval(model), worlds=4)
    if kind.startswith("net-") and re.fullmatch(r"net-\w+", kind):
        from duel.ai.value_net import NetBot

        if kind[4:] not in _NETS:
            _net_eval(kind[4:])
        return NetBot(_NETS[kind[4:]], name=kind)
    raise HTTPException(400, f"unknown bot {kind}")


@app.post("/api/game/bot_step")
def bot_step(kind: str = "mcts") -> dict:
    """Have the bot make one move for the current player."""
    _legacy_guard()
    if kind.startswith("automa-"):
        raise HTTPException(400, "автома играет только в комнатах (нужны её правила в партии)")
    g: Game | None = state["game"]
    if g is None:
        raise HTTPException(400, "no game")
    if g.winner is not None:
        return g.to_dict()
    bot = _get_bot(kind)
    g.apply(bot.choose(g))
    return g.to_dict()


@app.post("/api/game/move")
def make_move(body: MoveBody) -> dict:
    _legacy_guard()
    g: Game | None = state["game"]
    if g is None:
        raise HTTPException(400, "no game")
    legal = g.legal_moves()
    if body.move not in legal:
        stripped = {k: v for k, v in body.move.items() if k != "label"}
        match = next(
            (m for m in legal if {k: v for k, v in m.items() if k != "label"} == stripped), None
        )
        if match is None:
            raise HTTPException(400, f"illegal move: {body.move}")
    g.apply(body.move)
    return g.to_dict()


# ---------- rooms: vs-bot / PvP-by-link / hot-seat ----------

ROOMS: dict[str, dict] = {}
ROOM_TTL = 3 * 3600


class NewRoom(BaseModel):
    mode: str  # "bot" | "pvp" | "hotseat"
    bot: str | None = None
    side: int = 0  # creator's seat
    promo: bool = False
    seed: int | None = None


class RoomMove(BaseModel):
    token: str
    move: dict


class RoomToken(BaseModel):
    token: str


def _purge_rooms() -> None:
    now = time.time()
    for rid in [
        r
        for r, room in ROOMS.items()
        if now - room["ts"] > ROOM_TTL
        or (room["game"].winner is not None and now - room["ts"] > 900)
    ]:
        del ROOMS[rid]


def _room(rid: str) -> dict:
    room = ROOMS.get(rid)
    if room is None:
        raise HTTPException(404, "комната не найдена или устарела")
    return room


def _actor(g: Game) -> int:
    return g.pending[0]["player"] if g.pending else g.current


def _payload(rid: str, room: dict, seat: int | None) -> dict:
    d = room["game"].to_dict()
    d.update(
        room=rid,
        mode=room["mode"],
        your_seat=seat,
        version=room["version"],
        waiting=room["mode"] == "pvp" and None in room["seats"].values(),
        bot_kind=room["bot_kind"],
        bot_seat=room["bot_seat"],
    )
    if isinstance(room.get("bot"), Automa):
        d["automa"] = room["bot"].to_dict()
    return d


def _seat_of(room: dict, token: str) -> int:
    for s, t in room["seats"].items():
        if t == token:
            return s
    raise HTTPException(403, "не твоя комната")


# Туториал: фиксированный сид (раскладка выверена под сценарий рельсов в
# static/tutorial.js) и детерминированный лёгкий соперник — партия воспроизводится
# в точности, пока ученик идёт по подсказкам
TUTORIAL_SEED = 10
TUTORIAL_BOT_SEED = 7


@app.post("/api/room/new")
def room_new(body: NewRoom, request: Request) -> dict:
    _purge_rooms()
    if body.mode not in ("bot", "pvp", "hotseat", "tutorial"):
        raise HTTPException(400, "mode: bot | pvp | hotseat | tutorial")
    if len(ROOMS) >= MAX_ROOMS:
        raise HTTPException(503, "сервер переполнен, попробуй позже")
    ip = _client_ip(request)
    if PUBLIC:  # локальной разработке кап не мешает
        active = sum(
            1
            for r in ROOMS.values()
            if r.get("ip") == ip and r["game"].winner is None
        )
        if active >= MAX_ROOMS_PER_IP:
            raise HTTPException(429, "слишком много комнат с одного адреса")
    if PUBLIC and body.mode == "bot" and (body.bot or "mcts") not in {m["id"] for m in BOT_MENU}:
        raise HTTPException(400, "неизвестный бот")
    rid = secrets.token_urlsafe(4)
    token = secrets.token_urlsafe(9)
    side = 1 if body.side == 1 else 0
    bot = bot_kind = bot_seat = None
    rules = None
    if body.mode == "tutorial":
        from duel.ai.bots import GreedyBot

        side = 0  # ученик всегда Братство: сценарий написан под эту сторону
        bot_kind = "tutorial"
        bot = GreedyBot(seed=TUTORIAL_BOT_SEED)
        bot_seat = 1
        seats = {side: token, bot_seat: "__bot__"}
        body = body.model_copy(update={"seed": TUTORIAL_SEED, "promo": False})
    elif body.mode == "bot":
        bot_kind = body.bot or "mcts"
        bot = _make_bot(bot_kind, seed=int(time.time()) % 100_000)
        bot_seat = 1 - side
        seats = {side: token, bot_seat: "__bot__"}
        if isinstance(bot, Automa):
            # партия должна знать об автоме: бесплатные карты, цены тайлов, силы
            rules = {"automa": automa_rules(bot.character, bot_seat)}
    elif body.mode == "hotseat":
        seats = {0: token, 1: token}
    else:
        seats = {side: token, 1 - side: None}
    ROOMS[rid] = {
        "game": Game(seed=body.seed, promo=body.promo, rules=rules),
        "mode": body.mode,
        "seats": seats,
        "bot": bot,
        "bot_kind": bot_kind,
        "bot_seat": bot_seat,
        "version": 0,
        "ts": time.time(),
        "ip": ip,
    }
    return {"token": token, "seat": side, **_payload(rid, ROOMS[rid], side)}


@app.post("/api/room/{rid}/join")
def room_join(rid: str) -> dict:
    room = _room(rid)
    free = [s for s, t in room["seats"].items() if t is None]
    if not free:
        raise HTTPException(409, "комната уже занята")
    token = secrets.token_urlsafe(9)
    room["seats"][free[0]] = token
    room["version"] += 1
    room["ts"] = time.time()
    return {"token": token, "seat": free[0], **_payload(rid, room, free[0])}


@app.get("/api/room/{rid}/state")
def room_state(rid: str, token: str, v: int = -1) -> dict:
    room = _room(rid)
    seat = _seat_of(room, token)
    if v == room["version"]:
        return {"unchanged": True, "version": v}
    return _payload(rid, room, seat)


@app.get("/api/room/{rid}/log")
def room_log(rid: str, token: str) -> dict:
    """Полный журнал партии: в state гоняется только хвост (он опрашивается раз в секунду)."""
    room = _room(rid)
    _seat_of(room, token)
    return {"log": room["game"].log}


@app.post("/api/room/{rid}/move")
def room_move(rid: str, body: RoomMove) -> dict:
    room = _room(rid)
    seat = _seat_of(room, body.token)
    g: Game = room["game"]
    if g.winner is None:
        actor = _actor(g)
        if room["seats"].get(actor) != body.token:
            raise HTTPException(403, "сейчас не твой ход")
        legal = g.legal_moves()
        if body.move not in legal:
            stripped = {k: v for k, v in body.move.items() if k != "label"}
            match = next(
                (m for m in legal if {k: v for k, v in m.items() if k != "label"} == stripped),
                None,
            )
            if match is None:
                raise HTTPException(400, f"illegal move: {body.move}")
        g.apply(body.move)
        room["version"] += 1
        room["ts"] = time.time()
    return _payload(rid, room, seat)


@app.post("/api/room/{rid}/bot_step")
def room_bot_step(rid: str, body: RoomToken) -> dict:
    room = _room(rid)
    seat = _seat_of(room, body.token)
    g: Game = room["game"]
    if room["mode"] not in ("bot", "tutorial") or room["bot"] is None:
        raise HTTPException(400, "в этой комнате нет бота")
    if g.winner is None and _actor(g) == room["bot_seat"]:
        if not _BOT_SLOTS.acquire(timeout=20):
            raise HTTPException(503, "боты перегружены, повтори через пару секунд")
        try:
            mv = room["bot"].choose(g)
        finally:
            _BOT_SLOTS.release()
        g.apply(mv)
        after = getattr(room["bot"], "after_apply", None)
        if after is not None:
            after(g, mv)
        room["version"] += 1
        room["ts"] = time.time()
    return _payload(rid, room, seat)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def warm_up_bots() -> None:
    """Load the default bot in the background so its first move is instant."""
    import threading

    def load():
        try:
            kind = "strong" if any(m["id"] == "strong" for m in BOT_MENU) else "mcts"
            bot = _make_bot(kind)
            bot.choose(Game(seed=0))  # warm torch kernels + net cache
        except Exception:
            pass

    threading.Thread(target=load, daemon=True).start()


def main() -> None:
    import os

    host = os.environ.get("DUEL_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", os.environ.get("DUEL_PORT", "8173")))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
