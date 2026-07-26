const $ = (sel) => document.querySelector(sel);

const COIN_IMG = '<img class="coin" src="/static/icons/coin.png" alt="монета">';
const coinify = (s) => String(s).replaceAll("🪙", COIN_IMG);

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
const post = (path, body) =>
  api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

/* ---------- dictionaries ---------- */

const SKILL_ICONS = { Face: "🎭", Fist: "✊", Heart: "❤️", Crown: "👑", Book: "📖" };
const RACE_ICONS = {
  hobbits: "🌿", dwarves: "🔨", humans: "📯", elves: "🧪", ents: "🍃", wizards: "🔮",
};
const RACE_RU = {
  hobbits: "Хоббиты", dwarves: "Гномы", humans: "Люди",
  elves: "Эльфы", ents: "Энты", wizards: "Маги",
};
const LINK_RU = {
  Pot: "Котелок", Anvil: "Наковальня", Horseshoe: "Подкова", Harp: "Арфа",
  Horse: "Конь", Backpack: "Рюкзак", Fish: "Рыба", "Bow And Arrow": "Лук",
  Sword: "Меч", Helmet: "Шлем", Chest: "Сундук", Acorn: "Жёлудь",
  Scroll: "Свиток", Campfire: "Костёр", "Sleeping Bag": "Спальник",
  "Chest Mail": "Кольчуга", Ax: "Топор",
};
const REGION_RU = {
  lindon: "Линдон", arnor: "Арнор", rhovanion: "Рованион", enedwaith: "Энедвайт",
  rohan: "Рохан", gondor: "Гондор", mordor: "Мордор",
};
const SIDE_RU = ["Братство Кольца", "Саурон"];

const TOKEN_ICONS = {
  elves_extra_turn: "🪙🔄",
  elves_red_any: "⚔️🧭",
  elves_wild_skill: "🃏",
  dwarves_free_tile: "🏰💸",
  dwarves_tile_turn: "🏰🔄",
  dwarves_green_moves: "🍃🥾",
  hobbits_eagle: "🦅",
  hobbits_blue_unit: "💍⚔️",
  hobbits_chain_coins: "⛓🪙",
  humans_yellow_quest: "🪙💍",
  humans_red_extra: "⚔️➕",
  humans_double_discard: "🗑️✖2",
  ents_extra_turn: "🔄",
  ents_remove_fort: "🏰❌",
  ents_menu3: "🎯✖3",
  wizards_quest2: "💍💍",
  wizards_units2: "⚔️⚔️",
  wizards_discard_play: "🗑️▶️",
};

let BOARD = null; // static regions/edges
let G = null; // last game state
let ROOM = null; // {id, token, seat, mode}

function actorSeat() {
  if (!G) return null;
  return G.pending ? G.pending.player : G.current;
}

function canAct() {
  if (!ROOM || !G || G.winner !== null) return false;
  if (ROOM.mode === "hotseat") return true;
  return actorSeat() === ROOM.seat;
}

/* ---------- card faces (unchanged from layout iteration) ---------- */

function cardCost(card) {
  const parts = card.cost_skills.map((s) => SKILL_ICONS[s]);
  if (card.cost_coins) parts.push(`${card.cost_coins}🪙`);
  const cls = parts.length >= 5 ? "cost xs" : parts.length >= 4 ? "cost sm" : "cost";
  return parts.length ? `<div class="${cls}">${parts.join("")}</div>` : "";
}

function cardBody(card) {
  switch (card.type) {
    case "grey":
      if (card.skills_choice.length)
        return `<div class="big">${card.skills_choice.map((s) => SKILL_ICONS[s]).join("<i>/</i>")}</div>`;
      return `<div class="big">${card.skills.map((s) => SKILL_ICONS[s]).join("")}</div>`;
    case "yellow":
      return `<div class="big">🪙${card.coins}</div>`;
    case "blue":
      return `<div class="big">${"💍".repeat(card.quest_steps)}</div>`;
    case "green":
      return `<div class="big">${RACE_ICONS[card.race]}</div><div class="sub">${RACE_RU[card.race]}</div>`;
    case "red": {
      const sub = card.destinations.map((d) => REGION_RU[d]).join(" / ");
      // 3+ swords wrap like rings do: two per row
      const swords =
        card.troops >= 3
          ? Array.from({ length: card.troops }, () => "⚔️")
              .reduce((rows, s, i) => {
                if (i % 2 === 0) rows.push(s);
                else rows[rows.length - 1] += s;
                return rows;
              }, [])
              .join("<br>")
          : "⚔️".repeat(card.troops);
      return `<div class="big">${swords}</div>
        <div class="sub${sub.length > 16 ? " sm" : ""}">${sub}</div>`;
    }
    case "purple": {
      const fx = [];
      if (card.movements) fx.push(`🥾×${card.movements}`);
      if (card.opp_coins_lost) fx.push(`враг −${card.opp_coins_lost}🪙`);
      if (card.casualties) fx.push(`враг −${card.casualties}⚔️`);
      return `<div class="fx">${fx.map((f) => `<div>${f}</div>`).join("")}</div>`;
    }
  }
  return "";
}

const SKILL_RU = {
  Face: "Хитрость", Fist: "Сила", Heart: "Отвага", Crown: "Лидерство", Book: "Знание",
};

function cardTooltip(card) {
  const lines = [];
  switch (card.type) {
    case "grey":
      lines.push(
        card.skills_choice.length
          ? "Навык на выбор (один за ход): " + card.skills_choice.map((s) => SKILL_RU[s]).join(" или ")
          : "Даёт навык: " + card.skills.map((s) => SKILL_RU[s]).join(" + ")
      );
      break;
    case "yellow":
      lines.push(`Возьми ${card.coins} монет из резерва.`);
      break;
    case "blue":
      lines.push(`Пройди ${card.quest_steps} шаг(а) по Пути Кольца.`);
      break;
    case "green":
      lines.push(`Раса: ${RACE_RU[card.race]}. Символ для союзов и победы по 6 расам.`);
      break;
    case "red":
      lines.push(
        `Выставь ${card.troops} юнит(ов) в ОДИН регион: ${card.destinations.map((d) => REGION_RU[d]).join(" или ")}.`
      );
      break;
    case "purple": {
      if (card.movements) lines.push(`Перемести своих юнитов: ${card.movements} раз(а).`);
      if (card.opp_coins_lost) lines.push(`Противник теряет ${card.opp_coins_lost} монет(ы).`);
      if (card.casualties) lines.push(`Убери ${card.casualties} юнит(ов) противника.`);
      break;
    }
  }
  if (card.cost_skills.length || card.cost_coins) {
    const c = card.cost_skills.map((s) => SKILL_RU[s]).join(", ");
    lines.push(
      "Цена: " + [c, card.cost_coins ? `${card.cost_coins} монет` : ""].filter(Boolean).join(" + ")
    );
  } else if (!card.takes_link) {
    lines.push("Бесплатная.");
  }
  if (card.takes_link) lines.push(`⛓ Бесплатна при цепочке: ${LINK_RU[card.takes_link]}.`);
  if (card.gives_link) lines.push(`⛓ Даёт цепочку: ${LINK_RU[card.gives_link]}.`);
  return lines.join("<br>");
}

function cardFace(card, price) {
  const give = card.gives_link
    ? `<div class="give-link" title="даёт цепочку: ${LINK_RU[card.gives_link]}">⛓${LINK_RU[card.gives_link]}</div>`
    : "";
  const take = card.takes_link
    ? `<div class="take-link" title="бесплатно при цепочке: ${LINK_RU[card.takes_link]}">⛓→ ${LINK_RU[card.takes_link]}</div>`
    : "";
  const tag = price
    ? `<div class="price-tag ${price.affordable ? "" : "no"}">${
        price.chained ? "⛓ 0🪙" : `${price.coins}🪙`
      }</div>`
    : "";
  const pop = `<div class="card-pop">${cardTooltip(card)}</div>`;
  return `${cardCost(card)}${give}<div class="face-body">${cardBody(card)}</div>${take}${tag}${pop}`;
}

/* ---------- map ---------- */

let mapSel = null; // selected source region for a movement

function mapActions() {
  const acts = { direct: {}, moves: [] };
  if (!G || !canAct()) return acts;
  for (const m of G.moves) {
    if (m.type === "place" || m.type === "kill")
      (acts.direct[m.region] = acts.direct[m.region] || []).push(m);
    else if (m.type === "retreat") (acts.direct[m.to] = acts.direct[m.to] || []).push(m);
    else if (m.type === "move") acts.moves.push(m);
  }
  return acts;
}

function onRegionClick(r) {
  const acts = mapActions();
  if (acts.direct[r] && acts.direct[r].length) {
    mapSel = null;
    doMove(acts.direct[r][0]);
    return;
  }
  if (mapSel === r) {
    mapSel = null;
    renderMap();
    return;
  }
  if (mapSel) {
    const mv = acts.moves.find((m) => m.from === mapSel && m.to === r);
    if (mv) {
      mapSel = null;
      doMove(mv);
      return;
    }
  }
  if (acts.moves.some((m) => m.from === r)) {
    mapSel = r;
    renderMap();
  }
}

function renderMap() {
  if (!BOARD) return;
  const svg = $("#map");
  const pos = Object.fromEntries(BOARD.regions.map((r) => [r.key, r.pos]));
  const acts = mapActions();
  if (mapSel && !acts.moves.some((m) => m.from === mapSel)) mapSel = null;
  const lines = BOARD.edges
    .map(([a, b]) => {
      const [x1, y1] = pos[a];
      const [x2, y2] = pos[b];
      return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"
        stroke="#7a3020" stroke-width="0.45" stroke-dasharray="1.5 1"/>`;
    })
    .join("");
  const boxes = BOARD.regions
    .map((r) => {
      const [x, y] = r.pos;
      const cell = G && G.board ? G.board[r.key] : { units: [0, 0], forts: [0, 0] };
      // towers LEFT of the banner, troops RIGHT — all vertically centered on it;
      // same anchor for both sides (art tells them apart), second side shifts outward
      const items = [];
      const towers = [];
      if (cell.forts[0]) towers.push({ img: "tower0", n: cell.forts[0] });
      if (cell.forts[1]) towers.push({ img: "tower1", n: cell.forts[1] });
      const troops = [];
      if (cell.units[0]) troops.push({ img: "troop0", n: cell.units[0] });
      if (cell.units[1]) troops.push({ img: "troop1", n: cell.units[1] });
      towers.forEach((t, i) => items.push({ ...t, w: 4.1, h: 7.0, dx: -5.6 - i * 3.9, dy: -0.6 }));
      troops.forEach((t, i) => items.push({ ...t, w: 3.4, h: 6.6, dx: 5.4 + i * 3.4, dy: -0.6 }));
      const markers = items
        .map((it) => {
          const cx = x + it.dx;
          const cy = y + it.dy;
          const badge =
            it.n > 1
              ? `<circle cx="${cx + 1.6}" cy="${cy + 2.4}" r="1.25" fill="#241c12"
                   stroke="#e8dcc0" stroke-width="0.2"/>
                 <text x="${cx + 1.6}" y="${cy + 3.05}" text-anchor="middle"
                   font-size="1.8" font-weight="bold" fill="#fff">${it.n}</text>`
              : "";
          return `<image href="/static/icons/${it.img}.png"
              x="${cx - it.w / 2}" y="${cy - it.h / 2}" width="${it.w}" height="${it.h}"
              preserveAspectRatio="xMidYMid meet"/>${badge}`;
        })
        .join("");
      const dsts = mapSel ? acts.moves.filter((m) => m.from === mapSel).map((m) => m.to) : [];
      let hi = "";
      if (acts.direct[r.key]) hi = "direct";
      else if (mapSel === r.key) hi = "sel";
      else if (mapSel && dsts.includes(r.key)) hi = "dst";
      else if (!mapSel && acts.moves.some((m) => m.from === r.key)) hi = "src";
      const halo = hi
        ? `<ellipse cx="${x}" cy="${y - 0.6}" rx="8.6" ry="6.6" class="map-hi ${hi}"/>`
        : "";
      const clickable = hi ? `data-clickable="1"` : "";
      return `
        <g data-region="${r.key}" ${clickable}>
          <title>${r.name}</title>
          ${halo}
          <image href="/static/icons/${r.key}.png" x="${x - 2.2}" y="${y - 5.0}"
            width="4.4" height="8.8" preserveAspectRatio="xMidYMid meet"/>
          <text x="${x}" y="${y + 6.3}" text-anchor="middle" font-size="2"
            font-weight="bold" fill="#4a3820" letter-spacing="0.2">${r.name}</text>
          ${markers}
        </g>`;
    })
    .join("");
  svg.innerHTML = lines + boxes;
  svg.querySelectorAll("g[data-clickable]").forEach((g) =>
    g.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onRegionClick(g.dataset.region);
    })
  );
}

/* ---------- quest ---------- */

const SPACE_ICONS = {
  empty: "", coin: "🪙", unit: "⚔️", extra_turn: "🔄",
  destroy_fortress: "💥", ring: "💍", doom: "🌋",
};
const QSTEP = 44;

function questCells(strip, figureAt, figure) {
  return strip
    .map((kind, i) => {
      const cls = ["quest-space", kind !== "empty" ? "bonus" : "", kind === "doom" ? "doom" : ""]
        .filter(Boolean)
        .join(" ");
      const who = i === figureAt ? `<span class="who">${figure}</span>` : "";
      return `<div class="${cls}"><span class="icon">${SPACE_ICONS[kind]}</span>${who}</div>`;
    })
    .join("");
}

function renderQuest(q) {
  const width = 29 * QSTEP + 20;
  $("#quest-track").innerHTML = coinify(`
    <div class="quest-rows" style="width:${width}px">
      <div class="strip nazgul-strip" style="left:${q.strip_offset * QSTEP}px">
        ${questCells(q.nazgul_strip, q.nazgul_progress, "🏇")}
      </div>
      <div class="strip frodo-strip" style="left:${14 * QSTEP + 6}px">
        ${questCells(q.frodo_strip, q.frodo - 14, "🧝")}
      </div>
    </div>`);
}

/* ---------- tableau ---------- */

const CARD_W = 116, CARD_H = 166;
const UNIT_X = CARD_W / 2 + 5; // a bit of air between same-row cards
const STEP_Y = Math.round(CARD_H * 0.5); // moderate vertical overlap

function renderTableau() {
  const el = $("#tableau");
  const state = G.tableau;
  const movesBySlot = {};
  if (canAct())
    for (const m of G.moves)
      if (m.type === "play" || m.type === "discard" || m.type === "shire_pick")
        (movesBySlot[m.slot] = movesBySlot[m.slot] || []).push(m);

  const xs = state.slots.map((s) => s.x);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const width = (maxX - minX) * UNIT_X + CARD_W + 40;
  const height = Math.max(...state.slots.map((s) => s.row)) * STEP_Y + CARD_H + 30;
  el.style.minHeight = height + "px";
  const cx = Math.max(el.clientWidth, width) / 2;

  el.innerHTML = coinify(state.slots
    .filter((s) => !s.taken)
    .sort((a, b) => a.row - b.row)
    .map((s) => {
      const actionable = movesBySlot[s.id];
      const cls = [
        "card",
        s.revealed ? `faceup t-${s.card.type}` : `facedown ch${state.chapter}`,
        actionable ? "available" : "",
      ]
        .filter(Boolean)
        .join(" ");
      const content = s.revealed
        ? cardFace(s.card, s.price)
        : `<span class="slot-id" style="color:#c9b280">${s.id}</span>`;
      const left = cx + s.x * UNIT_X - CARD_W / 2;
      const top = 15 + s.row * STEP_Y;
      return `<div class="${cls}" data-slot="${s.id}" style="left:${left}px;top:${top}px">${content}</div>`;
    })
    .join(""));

  el.querySelectorAll(".card.available").forEach((c) =>
    c.addEventListener("click", (ev) => {
      ev.stopPropagation();
      showChooser(c, movesBySlot[c.dataset.slot]);
    })
  );
}

let chooserEl = null;
function closeChooser() {
  if (chooserEl) {
    chooserEl.remove();
    chooserEl = null;
  }
  document.querySelectorAll(".open-pile.show").forEach((el) => el.classList.remove("show"));
}
document.addEventListener("click", closeChooser);

function soldGroups(open) {
  const byType = {};
  for (const c of open) (byType[c.type] = byType[c.type] || []).push(c);
  return Object.entries(byType)
    .map(([t, cards]) => {
      const counts = {};
      for (const c of cards) {
        const k = `${miniLabel(c)} ${pileLabel(c)}`.trim();
        counts[k] = (counts[k] || 0) + 1;
      }
      return (
        `<div class="mini-group t-${t}">` +
        Object.entries(counts)
          .map(([k, n]) => `<div class="mini-card">${k}${n > 1 ? ` ×${n}` : ""}</div>`)
          .join("") +
        `</div>`
      );
    })
    .join("");
}

function pileLabel(c) {
  if (c.type === "green") return RACE_RU[c.race];
  if (c.type === "red") return c.destinations.map((d) => REGION_RU[d]).join("/");
  if (c.type === "purple") return "манёвры";
  return "";
}

function renderPiles() {
  const open = G.discard_open || [];
  $("#piles").innerHTML = coinify(`
    <div class="pile facedown-pile"
      title="Закрытый сброс: ${G.discard_hidden} карт (по 3 не вошли в каждую эпоху)">
      <span class="pile-num">${G.discard_hidden}</span><span class="pile-cap">закрыто</span>
    </div>
    <div class="pile open-pile ${open.length ? "clickable" : ""}"
      title="Проданные и снятые карты — кликни, чтобы посмотреть">
      <span class="pile-num">${open.length}</span><span class="pile-cap">продано</span>
      ${open.length ? `<div class="pile-pop"><b>Проданные карты:</b>${soldGroups(open)}</div>` : ""}
    </div>`);
  const op = document.querySelector(".open-pile.clickable");
  if (op)
    op.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasOpen = op.classList.contains("show");
      closeChooser();
      if (!wasOpen) op.classList.add("show");
    });
}

function showChooser(anchor, moves) {
  closeChooser();
  chooserEl = document.createElement("div");
  chooserEl.className = "chooser";
  for (const m of moves) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.innerHTML = coinify(m.label);
    b.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      closeChooser();
      await doMove(m);
    });
    chooserEl.appendChild(b);
  }
  const r = anchor.getBoundingClientRect();
  chooserEl.style.left = window.scrollX + r.left + "px";
  chooserEl.style.top = window.scrollY + r.bottom + 4 + "px";
  document.body.appendChild(chooserEl);
}

/* ---------- landmarks / races / panels ---------- */

const LM_TEXT = {
  barad_dur: "Крепость в Мордоре. Тайно выбери 1 карту из сброса и сыграй её бесплатно.",
  bree: "Крепость и 2 юнита в Арноре. Соверши 2 перемещения по карте.",
  erebor: "Крепость в Рованионе. Возьми 5 монет из резерва. 1 перемещение по карте.",
  grey_havens: "Крепость в Линдоне. Возьми 2 верхних жетона любой расы, оставь себе 1.",
  helms_deep: "Крепость и 3 юнита в Рохане.",
  isengard: "Крепость в Энедвайте. Сбрось 1 серую карту противника. +1 шаг по Пути Кольца.",
  minas_tirith: "Крепость и 1 юнит в Гондоре. +2 шага по Пути Кольца.",
  shire: "Сыграй любую видимую карту текущей эпохи (даже недоступную), оплатив её. Крепость НЕ ставится.",
  grond: "Снеси вражескую крепость в любом регионе (её юниты отступают в соседний). Поставь там свою крепость и 1 юнита.",
};

function renderLandmarks() {
  const movesByTile = {};
  if (canAct()) for (const m of G.moves) if (m.type === "tile") movesByTile[m.tile] = m;
  $("#landmark-row").innerHTML = coinify(
    G.landmarks
      .map((lm) => {
        const m = movesByTile[lm.id];
        const eff = [];
        if (lm.region) eff.push(`🏰 ${REGION_RU[lm.region]}`);
        if (lm.units) eff.push(`⚔️×${lm.units}`);
        if (lm.coins) eff.push(`🪙${lm.coins}`);
        if (lm.movements) eff.push(`🥾×${lm.movements}`);
        if (lm.quest_steps) eff.push(`💍×${lm.quest_steps}`);
        if (lm.effect)
          eff.push(lm.effect === "grey_havens_tokens" ? '<span class="dot-green"></span>' : "✨");
        const tag = lm.price
          ? `<div class="price-tag ${lm.price.affordable ? "" : "no"}">${lm.price.coins}🪙</div>`
          : "";
        return `<div class="tile faceup ${m ? "buyable" : ""}" data-tile="${lm.id}">
          <div class="tile-body">
            <b>${lm.name}</b>
            <span class="tile-cost">${lm.cost.map((s) => SKILL_ICONS[s]).join("")}</span>
            <span class="tile-eff${eff.join(" ").length > 12 ? " sm" : ""}">${eff.join(" ")}</span>
          </div>${tag}
          <div class="lm-pop">${LM_TEXT[lm.id] || ""}
            <div class="lm-pop-note">Доплата: +1🪙 за каждую свою крепость на карте</div>
          </div>
        </div>`;
      })
      .join("") || '<div class="area-hint">нет открытых тайлов</div>');
  if (G.landmarks_deck > 0)
    $("#landmark-row").innerHTML +=
      `<div class="tile stack"><b>Стопка</b><span class="stack-count">×${G.landmarks_deck}</span>` +
      `<span class="tile-eff">закрытые тайлы</span></div>`;
  document.querySelectorAll(".tile.buyable").forEach((t) =>
    t.addEventListener("click", () => doMove(movesByTile[t.dataset.tile]))
  );
}

const RACE_ORDER = ["elves", "hobbits", "humans", "dwarves", "ents", "wizards"];

function renderRaces() {
  $("#race-row").innerHTML = RACE_ORDER.filter((r) => r in G.alliance_stacks)
    .map((race) => {
      const st = G.alliance_stacks[race];
      const n = typeof st === "number" ? st : st.count;
      const tokens = typeof st === "number" ? [] : st.tokens;
      const pop = tokens.length
        ? `<div class="race-pop"><b>В стопке (порядок неизвестен):</b>${tokens
            .map(
              (t) =>
                `<div class="race-pop-chip"><span class="tok-ico">${TOKEN_ICONS[t.id] || "❔"}</span>
                 <span class="tok-txt">${t.text}</span></div>`
            )
            .join("")}</div>`
        : "";
      const instant = race === "ents" || race === "wizards" ? " instant" : "";
      return `<div class="race-token${instant}">
        <span class="race-ico">${RACE_ICONS[race]}</span>
        <span>${RACE_RU[race]}</span>
        <small>жетонов: ${n}</small>${pop}
      </div>`;
    })
    .join("");
}

function renderPanels() {
  for (const i of [0, 1]) {
    const pl = G.players[i];
    const el = document.querySelector(`#panel-${i} .panel-body`);
    const byType = {};
    for (const c of pl.played) (byType[c.type] = byType[c.type] || []).push(c);
    const cardsHtml = Object.entries(byType)
      .map(
        ([t, cards]) =>
          `<div class="mini-group t-${t}">` +
          cards
            .map(
              (c) =>
                `<div class="mini-card">${miniLabel(c)}${
                  c.gives_link
                    ? ` <span class="chain-mini">⛓${LINK_RU[c.gives_link]}</span>`
                    : ""
                }</div>`
            )
            .join("") +
          `</div>`
      )
      .join("");
    el.innerHTML = coinify(`
      <div class="coins">🪙 ${pl.coins}</div>
      <div class="stat">регионов: ${pl.presence} / 7 · рас: ${pl.race_victory_count} / 6</div>
      <div class="stat">юнитов в запасе: ${pl.supply}</div>
      ${pl.tokens.length ? `<div class="tokens">${pl.tokens.map((t) => `<div class="token ${t.kind === "instant" ? "used" : ""}" title="${t.text}"><span class="tok-ico">${RACE_ICONS[t.race]} ${TOKEN_ICONS[t.id] || ""}</span> ${t.text}${t.kind === "instant" ? " <i>(использован)</i>" : ""}</div>`).join("")}</div>` : ""}
      <div class="mini-cards">${cardsHtml}</div>
      ${pl.last_action ? `<div class="last-action">${pl.last_action}</div>` : ""}`);
    document.getElementById(`panel-${i}`).classList.toggle("active", G.current === i && !G.winner);
  }
}

function miniLabel(c) {
  switch (c.type) {
    case "grey":
      return c.skills_choice.length
        ? c.skills_choice.map((s) => SKILL_ICONS[s]).join("/")
        : c.skills.map((s) => SKILL_ICONS[s]).join("");
    case "yellow": return `🪙${c.coins}`;
    case "blue": return "💍".repeat(c.quest_steps);
    case "green": return RACE_ICONS[c.race];
    case "red": return "⚔️".repeat(c.troops);
    case "purple": return "🌀";
  }
  return "?";
}

/* ---------- prompt / turn bar ---------- */

function renderTurn() {
  const tb = $("#turnbar");
  if (G.winner !== null && G.winner !== undefined) {
    const txt =
      G.winner === "draw" ? "Ничья!" : `Победа: ${SIDE_RU[G.winner]}`;
    const why = { quest: "Путь Кольца", races: "поддержка рас", conquest: "покорение Средиземья", presence: "присутствие" }[G.win_reason] || "";
    tb.innerHTML = `🏆 ${txt} <small>(${why})</small>`;
    tb.className = "turnbar winner";
  } else {
    let who = "";
    if (ROOM && ROOM.mode !== "hotseat")
      who = actorSeat() === ROOM.seat ? " — твой ход" : ROOM.mode === "bot" ? "" : " — ждём соперника";
    if (G.waiting) who = " — ⏳ соперник ещё не подключился";
    tb.innerHTML = `Эпоха ${G.chapter} · ход ${G.turn_no} · ходит: <b class="${G.current ? "s" : "f"}">${SIDE_RU[G.current]}</b>${who}`;
    tb.className = "turnbar";
  }
  $("#reserve").textContent = `🪙 резерв: ${G.reserve}`;

  const pr = $("#prompt");
  const pendingMoves = canAct()
    ? G.moves.filter((m) => !["play", "discard", "tile", "shire_pick"].includes(m.type))
    : [];
  if (G.pending && pendingMoves.length) {
    const why = G.pending.why ? ` (${G.pending.why})` : "";
    pr.style.display = "";
    pr.innerHTML =
      `<div class="prompt-title">${SIDE_RU[G.pending.player]} — выбор${why}:</div>` +
      `<div class="prompt-btns"></div>`;
    const box = pr.querySelector(".prompt-btns");
    for (const m of pendingMoves.slice(0, 40)) {
      const b = document.createElement("button");
      b.className = "btn small";
      b.innerHTML = coinify(m.label);
      b.addEventListener("click", () => doMove(m));
      box.appendChild(b);
    }
  } else if (G.pending && G.pending.type === "shire_play" && canAct()) {
    pr.style.display = "";
    pr.innerHTML = `<div class="prompt-title">Шир: выбери видимую карту в раскладке (или пропусти)</div>`;
    const b = document.createElement("button");
    b.className = "btn small";
    b.textContent = "Пропустить";
    b.addEventListener("click", () => doMove({ type: "skip", label: "Пропустить" }));
    pr.appendChild(b);
  } else {
    pr.style.display = "none";
    pr.innerHTML = "";
  }
}

function renderLog() {
  $("#game-log").innerHTML = coinify(G.log.map((l) => `<div>${l}</div>`).join(""));
  const el = $("#game-log");
  el.scrollTop = el.scrollHeight;
}

/* ---------- main render / actions ---------- */

function renderAll() {
  if (!G || G.empty) return;
  renderTurn();
  renderPanels();
  renderLandmarks();
  renderRaces();
  renderPiles();
  renderMap();
  renderQuest(G.quest);
  renderTableau();
  renderLog();
}

/* ---------- rooms: bot / pvp / hotseat ---------- */

function setRoom(resp) {
  ROOM = { id: resp.room, token: resp.token || (ROOM && ROOM.token), seat: resp.seat ?? (ROOM && ROOM.seat), mode: resp.mode };
  G = resp;
  const info = $("#room-info");
  if (resp.mode === "pvp") {
    const link = `${location.origin}/?room=${resp.room}`;
    info.innerHTML = `PvP-комната <code>${resp.room}</code>
      <button class="btn small" id="topbar-copy">📋 ссылка</button>`;
    $("#topbar-copy").addEventListener("click", () => navigator.clipboard.writeText(link));
  } else if (resp.mode === "bot") {
    info.textContent = `против бота: ${ROOM.botLabel || resp.bot_kind}`;
  } else {
    info.textContent = "hot-seat";
  }
  renderAll();
}

async function roomState() {
  if (!ROOM) return;
  const resp = await api(
    `/api/room/${ROOM.id}/state?token=${encodeURIComponent(ROOM.token)}&v=${G ? G.version : -1}`
  );
  if (!resp.unchanged) {
    G = resp;
    renderAll();
  }
}

let botBusy = false;
async function botIfNeeded() {
  if (!ROOM || ROOM.mode !== "bot" || botBusy) return;
  botBusy = true;
  try {
    let guard = 0;
    while (G && G.winner === null && actorSeat() === G.bot_seat && guard++ < 80) {
      $("#turnbar").innerHTML += ' <span class="thinking">🤔 бот думает…</span>';
      G = await post(`/api/room/${ROOM.id}/bot_step`, { token: ROOM.token });
      renderAll();
      await new Promise((r) => setTimeout(r, 250));
    }
  } finally {
    botBusy = false;
  }
}

async function doMove(m) {
  if (!canAct()) return;
  mapSel = null;
  try {
    G = await post(`/api/room/${ROOM.id}/move`, { token: ROOM.token, move: m });
    renderAll();
    await botIfNeeded();
  } catch (e) {
    alert("Ход отклонён: " + e.message);
  }
}

/* ---------- lobby ---------- */

function showSection(id) {
  document.querySelectorAll(".lobby-section").forEach((s) => s.classList.add("hidden"));
  $(`#${id}`).classList.remove("hidden");
}

function hideLobby() {
  $("#lobby").classList.add("hidden");
}

async function loadBotMenu() {
  try {
    const resp = await api("/api/bots");
    const sel = $("#bot-diff");
    sel.innerHTML = "";
    for (const m of resp.menu || []) {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.label;
      o.dataset.desc = m.desc || "";
      sel.appendChild(o);
    }
    const updDesc = () => {
      const o = sel.selectedOptions[0];
      $("#bot-desc").textContent = o ? o.dataset.desc : "";
    };
    sel.addEventListener("change", updDesc);
    updDesc();
  } catch (e) {
    /* ai package unavailable */
  }
}

let pollTimer = null;
function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if (!ROOM || ROOM.mode !== "pvp") return;
    if (G && G.winner !== null && !G.waiting) return;
    try {
      await roomState();
      if (G && !G.waiting && !$("#lobby").classList.contains("hidden")) hideLobby();
    } catch (e) {
      /* transient */
    }
  }, 1300);
}

$("#lobby-bot").addEventListener("click", () => showSection("lobby-bot-opts"));
$("#lobby-pvp").addEventListener("click", () => showSection("lobby-pvp-opts"));
document.querySelectorAll("[data-back]").forEach((b) =>
  b.addEventListener("click", () => showSection("lobby-main"))
);

$("#start-bot").addEventListener("click", async () => {
  const sel = $("#bot-diff");
  const resp = await post("/api/room/new", {
    mode: "bot",
    bot: sel.value || "mcts",
    side: Number($("#side-select").value),
    promo: $("#promo").checked,
  });
  setRoom(resp);
  ROOM.botLabel = sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : sel.value;
  $("#room-info").textContent = `против бота: ${ROOM.botLabel}`;
  hideLobby();
  await botIfNeeded(); // if the bot's side opens the game
});

$("#lobby-hotseat").addEventListener("click", async () => {
  const resp = await post("/api/room/new", { mode: "hotseat" });
  setRoom(resp);
  hideLobby();
});

$("#start-pvp").addEventListener("click", async () => {
  const resp = await post("/api/room/new", {
    mode: "pvp",
    side: Number($("#pvp-side-select").value),
    promo: $("#pvp-promo").checked,
  });
  setRoom(resp);
  const link = `${location.origin}/?room=${resp.room}`;
  $("#room-link").textContent = link;
  $("#copy-link").addEventListener("click", () => navigator.clipboard.writeText(link));
  showSection("lobby-wait");
  startPolling();
});

async function joinRoom(rid) {
  showSection("lobby-join");
  try {
    const resp = await post(`/api/room/${rid}/join`, {});
    setRoom(resp);
    hideLobby();
    startPolling();
  } catch (e) {
    $("#join-info").textContent = "Не удалось подключиться: " + e.message;
  }
}

$("#to-lobby").addEventListener("click", () => {
  if (!G || G.winner !== null || confirm("Выйти из партии в лобби?")) location.href = "/";
});

(async function init() {
  BOARD = await api("/api/board");
  renderMap();
  await loadBotMenu();
  const rid = new URLSearchParams(location.search).get("room");
  if (rid) {
    await joinRoom(rid);
  } else {
    showSection("lobby-main");
  }
  startPolling();
})();
