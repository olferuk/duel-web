const $ = (sel) => document.querySelector(sel);

const COIN_IMG = '<img class="coin" src="/static/icons/coin.png" alt="coin">';
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
  hobbits: "Hobbits", dwarves: "Dwarves", humans: "Humans",
  elves: "Elves", ents: "Ents", wizards: "Wizards",
};
const LINK_RU = {
  Pot: "Pot", Anvil: "Anvil", Horseshoe: "Horseshoe", Harp: "Harp",
  Horse: "Horse", Backpack: "Backpack", Fish: "Fish", "Bow And Arrow": "Bow",
  Sword: "Sword", Helmet: "Helmet", Chest: "Chest", Acorn: "Acorn",
  Scroll: "Scroll", Campfire: "Campfire", "Sleeping Bag": "Sleeping Bag",
  "Chest Mail": "Chain Mail", Ax: "Axe",
};
const REGION_RU = {
  lindon: "Lindon", arnor: "Arnor", rhovanion: "Rhovanion", enedwaith: "Enedwaith",
  rohan: "Rohan", gondor: "Gondor", mordor: "Mordor",
};
const SIDE_RU = ["Fellowship", "Sauron"];

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

const TYPE_ORDER = ["grey", "yellow", "green", "red", "blue", "purple"];

/* геометрия арта (analysis/ui_layout.json, разметка владельца + CV) */
const MAPL = {
  W: 2000, H: 1439,
  zoneRadius: 40,
  zones: {
    lindon: [187, 292, 284, 192], arnor: [737, 176, 287, 193], rhovanion: [1476, 297, 284, 195],
    enedwaith: [645, 695, 287, 196], rohan: [1200, 741, 288, 199], gondor: [965, 1099, 284, 194],
    mordor: [1640, 1053, 281, 195],
  },
  pts: {
    lindon: { units: [322, 357], towers: [136, 323] },
    arnor: { units: [869, 243], towers: [685, 206] },
    enedwaith: { units: [778, 770], towers: [593, 724] },
    rohan: { units: [1336, 812], towers: [1147, 772] },
    gondor: { units: [1095, 1166], towers: [911, 1123] },
    rhovanion: { units: [1605, 372], towers: [1422, 323] },
    mordor: { units: [1775, 1117], towers: [1585, 1081] }
  },
  // точки дорог для жетона Балрога, ключ "a|b" (сортированный); размечать
  // на /static/markup.html и вставлять сюда; не размеченные — авто-середина
  roads: {
    "arnor|lindon": [552, 331],
    "arnor|enedwaith": [795, 544],
    "arnor|rhovanion": [1188, 321],
    "rhovanion|rohan": [1455, 627],
    "enedwaith|rohan": [1066, 817],
    "enedwaith|rhovanion": [1138, 615],
    "enedwaith|gondor": [916, 994],
    "gondor|rohan": [1219, 1017],
    "mordor|rohan": [1621, 939],
    "gondor|mordor": [1391, 1179],
  },
};
const RINGL = {
  W: 4305, H: 486,
  frodo: { x: 80, y: 184 },   // старт полосы (offset 0)
  nazgulY: 76,
  stripW: 2216, stripRingX: 2096,
  nazgulW: 273, nazgulDX: -156,
  cellX0: 2178, cellPitch: (4202 - 2178) / 14,
  bgCellY: 400,
  stripCells: [[74,219],[218,219],[362,219],[507,219],[651,219],[795,219],[939,219],
    [1083,219],[1227,219],[1371,219],[1516,219],[1660,219],[1804,219],[1948,219],[2096,213]],
};

const SPACE_TIP = {
  empty: "Empty space",
  coin: "Bonus: +1 coin from the reserve",
  unit: "Bonus: place 1 unit in any region (optional)",
  extra_turn: "Bonus: extra turn (optional)",
  destroy_fortress: "Bonus: destroy one enemy fortress",
  ring: "Ring",
  doom: "Mount Doom: Frodo destroys the Ring here and the Fellowship wins",
};

function cbMode() { return localStorage.getItem("cbMode") === "1"; }
function applyCbMode() { document.body.classList.toggle("cb", cbMode()); }

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
      if (card.opp_coins_lost) fx.push(`enemy −${card.opp_coins_lost}🪙`);
      if (card.casualties) fx.push(`enemy −${card.casualties}⚔️`);
      return `<div class="fx">${fx.map((f) => `<div>${f}</div>`).join("")}</div>`;
    }
  }
  return "";
}

const SKILL_RU = {
  Face: "Cunning", Fist: "Strength", Heart: "Courage", Crown: "Leadership", Book: "Knowledge",
};

function cardTooltip(card) {
  const lines = [];
  switch (card.type) {
    case "grey":
      lines.push(
        card.skills_choice.length
          ? "Skill of your choice (one per turn): " + card.skills_choice.map((s) => SKILL_RU[s]).join(" or ")
          : "Gives skill: " + card.skills.map((s) => SKILL_RU[s]).join(" + ")
      );
      break;
    case "yellow":
      lines.push(`Take ${card.coins} coins from the reserve.`);
      break;
    case "blue":
      lines.push(`Advance ${card.quest_steps} step(s) on the Ring Path.`);
      break;
    case "green":
      lines.push(`Race: ${RACE_RU[card.race]}. Symbol for alliances and the 6-race victory.`);
      break;
    case "red":
      lines.push(
        `Place ${card.troops} unit(s) in ONE region: ${card.destinations.map((d) => REGION_RU[d]).join(" or ")}.`
      );
      break;
    case "purple": {
      if (card.movements) lines.push(`Move your units: ${card.movements} time(s).`);
      if (card.opp_coins_lost) lines.push(`Opponent loses ${card.opp_coins_lost} coin(s).`);
      if (card.casualties) lines.push(`Remove ${card.casualties} enemy unit(s).`);
      break;
    }
  }
  if (card.cost_skills.length || card.cost_coins) {
    const c = card.cost_skills.map((s) => SKILL_RU[s]).join(", ");
    lines.push(
      "Cost: " + [c, card.cost_coins ? `${card.cost_coins} coins` : ""].filter(Boolean).join(" + ")
    );
  } else if (!card.takes_link) {
    lines.push("Free.");
  }
  if (card.takes_link) lines.push(`⛓ Free via chain: ${LINK_RU[card.takes_link]}.`);
  if (card.gives_link) lines.push(`⛓ Gives chain: ${LINK_RU[card.gives_link]}.`);
  return lines.join("<br>");
}

function cardFace(card, price) {
  const tag = price
    ? `<div class="price-tag ${price.affordable ? "" : "no"}">${
        price.chained ? "⛓ 0🪙" : `${price.coins}🪙`
      }</div>`
    : "";
  const pop = `<div class="card-pop">${cardTooltip(card)}</div>`;
  return `<img class="card-art" draggable="false" src="/static/art/cards/${card.id}.jpg">${tag}${pop}`;
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
  const el = $("#map");
  if (!el) return;
  const acts = mapActions();
  if (mapSel && !acts.moves.some((m) => m.from === mapSel)) mapSel = null;
  const P = (x, y) => `left:${(x / MAPL.W) * 100}%;top:${(y / MAPL.H) * 100}%`;
  let h = `<img class="map-bg" draggable="false" src="/static/art/map.jpg">`;

  // плашки присутствия в углах
  if (G && G.players) {
    h += `<div class="map-vp f" title="${SIDE_RU[0]}: presence (7 wins by conquest)">${G.players[0].presence} / 7</div>`;
    h += `<div class="map-vp s" title="${SIDE_RU[1]}: presence (7 wins by conquest)">${G.players[1].presence} / 7</div>`;
  }

  for (const r of (BOARD ? BOARD.regions : [])) {
    const pts = MAPL.pts[r.key];
    if (!pts) continue;
    const cell = G && G.board ? G.board[r.key] : { units: [0, 0], forts: [0, 0] };
    // подсветка/кликабельность
    const dsts = mapSel ? acts.moves.filter((m) => m.from === mapSel).map((m) => m.to) : [];
    let hi = "";
    if (acts.direct[r.key]) hi = "direct";
    else if (mapSel === r.key) hi = "sel";
    else if (mapSel && dsts.includes(r.key)) hi = "dst";
    else if (!mapSel && acts.moves.some((m) => m.from === r.key)) hi = "src";
    const z = MAPL.zones[r.key]; // [x, y, w, h] в пространстве карты — реальная табличка региона
    // правые углы скруглены общим радиусом (левые прямые); радиус в % от размеров зоны
    const rh = ((MAPL.zoneRadius / z[2]) * 100).toFixed(1);
    const rv = ((MAPL.zoneRadius / z[3]) * 100).toFixed(1);
    h += `<div class="map-zone ${hi}" data-region="${r.key}" ${hi ? 'data-clickable="1"' : ""}
       style="left:${(z[0] / MAPL.W) * 100}%;top:${(z[1] / MAPL.H) * 100}%;
       width:${(z[2] / MAPL.W) * 100}%;height:${(z[3] / MAPL.H) * 100}%;
       border-radius:0 ${rh}% ${rh}% 0 / 0 ${rv}% ${rv}% 0" title="${r.name}"></div>`;
    // башни (слева-точка) и юниты (справа-точка): обе стороны на своей точке,
    // вторая сторона сдвигается, чтобы не наезжать
    const marks = [];
    if (cell.forts[0]) marks.push(["tower0", cell.forts[0], pts.towers, -1]);
    if (cell.forts[1]) marks.push(["tower1", cell.forts[1], pts.towers, 1]);
    if (cell.units[0]) marks.push(["troop0", cell.units[0], pts.units, -1]);
    if (cell.units[1]) marks.push(["troop1", cell.units[1], pts.units, 1]);
    for (const [img, n, pt, side] of marks) {
      const both = (img.startsWith("tower") ? cell.forts[0] && cell.forts[1] : cell.units[0] && cell.units[1]);
      const dx = both ? side * 34 : 0;
      const w = img.startsWith("tower") ? 3.4 : 3.4; // солдатики +20%
      h += `<div class="map-mark ${img.startsWith("troop") ? "troop" : "tower"}" style="${P(pt[0] + dx, pt[1])};width:${w}%">
        <img draggable="false" src="/static/icons/${img}.png">
        ${n > 1 ? `<b>${n}</b>` : ""}</div>`;
    }
  }
  // Балрог: перекрытые связи и выбор связи — прямо на карте, в середине дороги.
  // Точка дороги — из ручной разметки MAPL.roads (/static/markup.html), а без неё
  // ≈ середина отрезка между центрами табличек регионов.
  const edgeMid = (key) => {
    if (MAPL.roads && MAPL.roads[key]) return MAPL.roads[key];
    const [a, b] = key.split("|").map((k) => MAPL.zones[k]);
    if (!a || !b) return null;
    return [(a[0] + a[2] / 2 + b[0] + b[2] / 2) / 2, (a[1] + a[3] / 2 + b[1] + b[3] / 2) / 2];
  };
  for (const [key, owner] of Object.entries((G && G.locked_edges) || {})) {
    const m = edgeMid(key);
    if (!m) continue;
    const [a, b] = key.split("|");
    h += `<div class="map-mark lock" style="${P(m[0], m[1])};width:4.2%"
      title="Balrog (${SIDE_RU[owner]}): ${SIDE_RU[1 - owner]} cannot move along ${REGION_RU[a]} ↔ ${REGION_RU[b]}">
      <img draggable="false" src="/static/art/allies/power-small.png"></div>`;
  }
  const lockMoves = G && canAct() ? G.moves.filter((m) => m.type === "lock_link") : [];
  lockMoves.forEach((mv, i) => {
    const m = edgeMid(mv.edge);
    if (!m) return;
    h += `<div class="map-edge-target" data-lock="${i}" style="${P(m[0], m[1])}" title="${mv.label}"></div>`;
  });
  el.innerHTML = h;
  el.querySelectorAll("[data-clickable]").forEach((z) =>
    z.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onRegionClick(z.dataset.region);
    })
  );
  el.querySelectorAll("[data-lock]").forEach((t) =>
    t.addEventListener("click", (ev) => {
      ev.stopPropagation();
      doMove(lockMoves[Number(t.dataset.lock)]);
    })
  );
}

/* ---------- quest ---------- */

function renderQuest(q) {
  const fLeft = 28 - q.frodo;
  const sLeft = q.gap;
  const offset = q.strip_offset; // 0..14 — на сколько клеток уехала полоса Фродо
  const nazgulGlobal = q.nazgul_global; // 0..28
  const px = (v) => (v / RINGL.W) * 100; // проценты ширины панорамы
  const stripX = RINGL.cellX0 + offset * RINGL.cellPitch - RINGL.stripRingX;
  const nazX = RINGL.cellX0 + (nazgulGlobal - 14) * RINGL.cellPitch + RINGL.nazgulDX;
  $("#quest-track").innerHTML = `
    <div class="ring-art">
      <img class="ring-bg" draggable="false" src="/static/art/ring/track-bg.jpg">
      <img class="ring-strip" draggable="false" src="/static/art/ring/track-frodo.png"
        style="left:${px(stripX)}%;top:${(RINGL.frodo.y / RINGL.H) * 100}%;width:${px(RINGL.stripW)}%">
      <img class="ring-nazgul" draggable="false" src="/static/art/ring/track-nazgul.png"
        style="left:${px(nazX)}%;top:${(RINGL.nazgulY / RINGL.H) * 100}%;width:${px(RINGL.nazgulW)}%">
      ${q.frodo_strip.map((kind, i) => {
        const cx = RINGL.cellX0 + i * RINGL.cellPitch;
        const tip = i === 0 ? "Frodo's start" : SPACE_TIP[kind] || kind;
        return `<div class="ring-zone" title="Frodo's path, space ${i}: ${tip}"
          style="left:${px(cx)}%;top:${(RINGL.bgCellY / RINGL.H) * 100}%"></div>`;
      }).join("")}
      ${q.nazgul_strip.map((kind, i) => {
        const [cx, cy] = RINGL.stripCells[i];
        const tip = kind === "ring"
          ? "Ring: the Nazgûl catches Frodo here and Sauron wins"
          : SPACE_TIP[kind] || kind;
        return `<div class="ring-zone naz" title="Nazgûl path, space ${i}: ${tip}"
          style="left:${px(stripX + cx)}%;top:${((RINGL.frodo.y + cy) / RINGL.H) * 100}%"></div>`;
      }).join("")}
    </div>`;
  $("#quest-vp").innerHTML =
    `<div class="race-vp s" title="Steps left for Sauron to catch Frodo">🏇 ${sLeft} left</div>` +
    `<div class="race-vp f" title="Steps left for the Fellowship to reach Mount Doom (Ring victory)">🧝 ${fLeft} left</div>`;
}

/* ---------- tableau ---------- */

const CARD_W = 124, CARD_H = 185; // пропорции арта 624×930, +7% за счёт ужатого трека
const UNIT_X = CARD_W / 2 + 5; // a bit of air between same-row cards
const STEP_Y = Math.round(CARD_H * 0.5); // moderate vertical overlap

function renderTableau() {
  const el = $("#tableau");
  const state = G.tableau;
  const movesBySlot = {};
  if (canAct())
    for (const m of G.moves)
      // выбор цели для эффектов союзников идёт по тем же картам раскладки:
      // «слот 12» в меню игроку ничего не говорит, тапать надо по самой карте
      if (
        m.type === "play" ||
        m.type === "discard" ||
        m.type === "shire_pick" ||
        m.type === "faramir_pick" ||
        m.type === "grima_target"
      )
        (movesBySlot[m.slot] = movesBySlot[m.slot] || []).push(m);

  const xs = state.slots.map((s) => s.x);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const isMobile = window.innerWidth <= 820;
  // на телефоне карты кладём вплотную и режем поля — каждый пиксель идёт в масштаб
  const unitX = isMobile ? CARD_W / 2 : UNIT_X;
  const padX = isMobile ? 10 : 40;
  const width = (maxX - minX) * unitX + CARD_W + padX;
  const height = Math.max(...state.slots.map((s) => s.row)) * STEP_Y + CARD_H + 30;
  const cx = isMobile ? width / 2 : Math.max(el.clientWidth, width) / 2;

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
      // жетон Силы лежит НА карте: его забирает тот, чьё действие её вскроет
      const power = (G.power_slots || []).includes(s.id)
        ? `<img class="power-on-card" draggable="false" src="/static/art/allies/power-small.png"
             title="Power token: goes to whoever reveals this card">`
        : "";
      const content =
        (s.revealed
          ? cardFace(s.card, s.price)
          : `<span class="slot-id" style="color:#c9b280">${s.id}</span>`) + power;
      const left = cx + s.x * unitX - CARD_W / 2;
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

  // Раскладка ВСЕГДА влезает по ширине своей колонки — и на мобиле, и на десктопе:
  // иначе absolute-карты вылезают из блока ПОД карту регионов и их тапы перехватываются
  // (давний десктопный баг на 1440px, пойман e2e туториала).
  // zoom (в отличие от transform) меняет и layout-бокс → высота блока тоже ужимается.
  el.style.zoom = "";
  el.style.width = ""; // сброс перед замером: колонка сама скажет свою ширину
  const avail = el.clientWidth - 2;
  const fit = Math.min(1, avail / width);
  if (fit < 1) {
    el.style.width = width + "px";
    el.style.zoom = fit;
    el.style.minHeight = height + "px";
  } else {
    el.style.minHeight = height + "px";
  }
}

let chooserEl = null, chooserAnchor = null;
function closeChooser() {
  if (chooserEl) {
    chooserEl.remove();
    chooserEl = null;
    // карта руки держалась поднятой ради меню — опускаем вместе с ним
    const row = chooserAnchor && chooserAnchor.closest && chooserAnchor.closest(".ally-row");
    chooserAnchor = null;
    if (row) {
      setHandHover(row, -1);
      // спрятанная рука держала одну карту лицом ради меню — прячем обратно;
      // отложенно, чтобы showChooser успел снять координаты нового якоря
      if (row.dataset.hand && G && !allyHandOpen(Number(row.dataset.hand)))
        setTimeout(() => { renderPanels(); renderHand(); }, 0);
    }
  }
  document.querySelectorAll(".open-pile.show").forEach((el) => el.classList.remove("show"));
}
document.addEventListener("click", closeChooser);

function soldGroups(open) {
  const byType = {};
  for (const c of open) (byType[c.type] = byType[c.type] || []).push(c);
  return TYPE_ORDER.filter((t) => byType[t])
    .map(
      (t) =>
        `<div class="sold-row">` +
        byType[t]
          .map((c) => `<img class="sold-thumb" src="/static/art/cards/${c.id}.jpg" title="${c.type}">`)
          .join("") +
        `</div>`
    )
    .join("");
}

function pileLabel(c) {
  if (c.type === "green") return RACE_RU[c.race];
  if (c.type === "red") return c.destinations.map((d) => REGION_RU[d]).join("/");
  if (c.type === "purple") return "maneuvers";
  return "";
}

function renderPiles() {
  const open = G.discard_open || [];
  $("#piles").innerHTML = coinify(`
    <div class="pile facedown-pile"
      title="Set aside during chapter setup (3 face down each): not in the discard and out of the game">
      <span class="pile-num">${G.discard_hidden}</span><span class="pile-cap">out of play</span>
    </div>
    <div class="pile open-pile ${open.length ? "clickable" : ""}"
      title="Sold and removed cards. Click to view">
      <span class="pile-num">${open.length}</span><span class="pile-cap">sold</span>
      ${open.length ? `<div class="pile-pop"><b>Sold cards:</b>${soldGroups(open)}</div>` : ""}
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

/* ---------- мобильный tap-попап с клампом по краям экрана ---------- */
let popEl = null, popAnchor = null;
function hidePopover() {
  if (popEl) { popEl.remove(); popEl = null; popAnchor = null; }
}
let _tileBuy = {};

/* Единый мобильный tap-попап: тултип сверху + экшен-меню снизу (карты, ландмарки,
   клетки трека, стопки рас) — однородно везде. */
function mobileMenu(anchor, tooltipHtml, actions) {
  hidePopover();
  popEl = document.createElement("div");
  popEl.className = "m-popover m-menu";
  popAnchor = anchor;
  let html = tooltipHtml ? `<div class="pop-tip">${tooltipHtml}</div>` : "";
  if (actions && actions.length) html += `<div class="pop-acts"></div>`;
  popEl.innerHTML = coinify(html);
  document.body.appendChild(popEl);
  if (actions && actions.length) {
    const box = popEl.querySelector(".pop-acts");
    for (const a of actions) {
      const btn = document.createElement("button");
      btn.className = "btn small";
      btn.innerHTML = coinify(a.label);
      btn.addEventListener("click", (ev) => { ev.stopPropagation(); hidePopover(); a.fn(); });
      box.appendChild(btn);
    }
  }
  positionPopover(anchor);
}
function positionPopover(anchor) {
  const r = anchor.getBoundingClientRect();
  const pw = popEl.offsetWidth, ph = popEl.offsetHeight;
  let left = r.left + r.width / 2 - pw / 2 + window.scrollX;
  left = Math.max(6, Math.min(left, window.innerWidth - pw - 6));
  let top = r.top - ph - 8 > 0 ? r.top - ph - 8 + window.scrollY : r.bottom + 8 + window.scrollY;
  top = Math.max(6 + window.scrollY, Math.min(top, window.scrollY + window.innerHeight - ph - 6));
  popEl.style.left = left + "px";
  popEl.style.top = top + "px";
}

document.addEventListener("click", (e) => {
  if (window.innerWidth > 820) return; // десктоп не трогаем
  if (popEl && popEl.contains(e.target)) return;

  const card = e.target.closest("#tableau .card.faceup, .hand-card .stk");
  if (card) {
    e.stopPropagation();
    const inTableau = card.closest("#tableau");
    let cardObj = null, actions = [];
    if (inTableau) {
      const slot = G.tableau.slots.find((s) => String(s.id) === card.dataset.slot);
      cardObj = slot && slot.card;
      const moves = canAct()
        ? G.moves.filter(
            (m) =>
              ["play", "discard", "shire_pick"].includes(m.type) &&
              String(m.slot) === card.dataset.slot
          )
        : [];
      actions = moves.map((m) => ({ label: shortLabel(m), fn: () => doMove(m) }));
    } else {
      const pop = card.querySelector(".card-pop");
      mobileMenu(card, pop ? pop.innerHTML : "", []);
      return;
    }
    if (cardObj) mobileMenu(card, cardTooltip(cardObj), actions);
    return;
  }

  const tile = e.target.closest(".tile.art");
  if (tile && !tile.classList.contains("stack")) {
    e.stopPropagation();
    const id = tile.dataset.tile;
    const tip = tile.querySelector(".lm-pop");
    const actions = _tileBuy[id]
      ? [{
          label: `Buy ${_tileBuy[id].label.match(/\((.+)\)/)?.[1] || ""}`,
          fn: () => doMove(_tileBuy[id]),
        }]
      : [];
    mobileMenu(tile, tip ? tip.innerHTML : "", actions);
    return;
  }

  const cell = e.target.closest(".ring-zone");
  if (cell) {
    const t = cell.getAttribute("title") || "";
    if (/Empty space|Frodo's start/.test(t)) { hidePopover(); return; } // пустая клетка — без тултипа
    e.stopPropagation();
    mobileMenu(cell, t, []);
    return;
  }

  const tok = e.target.closest(".race-token-art");
  if (tok) {
    e.stopPropagation();
    const pop = tok.querySelector(".race-pop");
    mobileMenu(tok, pop ? pop.innerHTML : "<b>Stack is empty</b>", []);
    return;
  }

  const dtok = e.target.closest(".dock-tok");
  if (dtok) {
    e.stopPropagation();
    const tip = dtok.querySelector(".tok-tip");
    mobileMenu(dtok, tip ? tip.innerHTML : "", []);
    return;
  }

  if (popEl && !popEl.contains(e.target)) hidePopover();
}, true);

/* ---------- всплывающие подсказки ---------- */

// Подсказки лежат в потоке `position: fixed` и раскладываются отсюда.
// Так они физически не могут распереть страницу (раньше подсказка у крайней
// карты вылезала за окно и добавляла документу полосы прокрутки) и всегда
// остаются внутри экрана на любом мониторе.
const POP_SEL = ".card-pop, .lm-pop, .tok-pop";
const POP_HOSTS = ".stk, .card.faceup, .tile, .tok-wrap";
const POP_PAD = 8;
let popHost = null;

// Единственная живая подсказка лежит в слое НА ТЕЛЕ страницы, а не внутри
// карточки. Иначе её ломают предки: раскладка ужата через `zoom`, и
// fixed-потомок внутри zoom-контейнера считает координаты в его масштабе —
// подсказка карты пирамиды уезжала на сотни пикселей мимо экрана.
const popLayer = document.createElement("div");
popLayer.id = "pop-layer";
document.body.appendChild(popLayer);

function hidePop() {
  popLayer.style.display = "";
  popHost = null;
}

// force=true — сторона не переворачивается, даже если места не хватает
// (подсказка лишь прижимается к краю окна): рука союзников всегда вниз,
// иначе у соседних карт подсказки прыгали то вверх, то вниз
function showPop(host, above, force) {
  const src = host.querySelector(POP_SEL);
  if (!src) return;
  popHost = host;
  popLayer.className = src.className; // забираем оформление исходной подсказки
  popLayer.innerHTML = src.innerHTML;
  popLayer.style.display = "block";
  popLayer.style.left = "0px";
  popLayer.style.top = "0px";
  const h = host.getBoundingClientRect();
  const p = popLayer.getBoundingClientRect();
  const maxL = Math.max(POP_PAD, window.innerWidth - p.width - POP_PAD);
  const maxT = Math.max(POP_PAD, window.innerHeight - p.height - POP_PAD);
  const fitsAbove = h.top - p.height - POP_PAD >= 0;
  const fitsBelow = h.bottom + p.height + POP_PAD <= window.innerHeight;
  const up = force ? !!above : above ? fitsAbove || !fitsBelow : !fitsBelow && fitsAbove;
  const left = h.left + h.width / 2 - p.width / 2;
  const top = up ? h.top - p.height - POP_PAD : h.bottom + POP_PAD;
  popLayer.style.left = Math.round(Math.min(Math.max(left, POP_PAD), maxL)) + "px";
  popLayer.style.top = Math.round(Math.min(Math.max(top, POP_PAD), maxT)) + "px";
}

document.addEventListener(
  "mouseover",
  (e) => {
    if (!e.target.closest) return;
    if (e.target.closest(".ally-row")) return; // рукой управляют зоны, см. bindHandZones
    const host = e.target.closest(POP_HOSTS);
    if (!host) return hidePop();
    if (host === popHost) return; // уже показана для него
    // стопки, жетоны и карты раскладки раскрываются вверх — снизу под картой
    // живёт меню действий (showChooser), и они не спорят за одно место;
    // ориентиры — вниз
    showPop(host, !!e.target.closest(".stk, .tok-wrap, .card.faceup"));
  },
  true
);
window.addEventListener("scroll", hidePop, true);

function shortLabel(m) {
  if (m.type === "play")
    return m.chained ? "▶ Play ⛓ 0🪙" : `▶ Play ${m.cost}🪙`;
  if (m.type === "discard") return `🗑 Sell +${m.gain}🪙`;
  if (m.type === "shire_pick") return `The Shire ${m.cost != null ? m.cost + "🪙" : ""}`;
  // на самой карте имя уже видно — в меню оставляем только действие и цену
  if (m.type === "ally_enter") return "✋ Summon · 1 token";
  if (m.type === "ally_exit") return "👋 Farewell · 2 tokens";
  return m.label;
}

function showChooser(anchor, moves) {
  closeChooser();
  chooserEl = document.createElement("div");
  chooserEl.className = "chooser";
  for (const m of moves) {
    const b = document.createElement("button");
    b.className = "btn small";
    b.innerHTML = coinify(shortLabel(m));
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
  chooserAnchor = anchor;
}

/* ---------- landmarks / races / panels ---------- */

const LM_TEXT = {
  barad_dur: "Fortress in Mordor. Secretly choose 1 card from the discard and play it for free.",
  bree: "Fortress and 2 units in Arnor. Make 2 moves on the map.",
  erebor: "Fortress in Rhovanion. Take 5 coins from the reserve. 1 move on the map.",
  grey_havens: "Fortress in Lindon. Take the top 2 tokens of any race and keep 1.",
  helms_deep: "Fortress and 3 units in Rohan.",
  isengard: "Fortress in Enedwaith. Discard 1 enemy grey card. +1 step on the Ring Path.",
  minas_tirith: "Fortress and 1 unit in Gondor. +2 steps on the Ring Path.",
  shire: "Play any visible card of the current chapter (even an unavailable one) by paying for it. No fortress is placed.",
  grond: "Destroy an enemy fortress in any region (its units retreat to a neighbor). Place your own fortress and 1 unit there.",
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
        const lockedBy = (G.locked_landmarks || {})[lm.id];
        const lock =
          lockedBy === undefined
            ? ""
            : `<img class="power-lock" draggable="false" src="/static/art/allies/power-small.png"
                 title="Uruk-hai Chief: landmark locked, only ${SIDE_RU[lockedBy]} can take it">`;
        return `<div class="tile art ${m ? "buyable" : ""}" data-tile="${lm.id}">
          <img draggable="false" src="/static/art/landmarks/${lm.id}.jpg">
          ${tag}${lock}
          <div class="lm-pop"><b>${lm.name}</b><br>${LM_TEXT[lm.id] || ""}
            <div class="lm-pop-note">Effects: ${eff.join(" ")} · Surcharge: +1🪙 per fortress you own</div>
          </div>
        </div>`;
      })
      .join("") || '<div class="area-hint">no open tiles</div>');
  if (G.landmarks_deck > 0)
    $("#landmark-row").innerHTML +=
      `<div class="tile art stack" title="Face-down tiles in the stack (promo tiles: ${G.promo ? "in play" : "off"})">` +
      `<img draggable="false" src="/static/art/landmarks/_back.jpg"><small>×${G.landmarks_deck}</small></div>`;
  _tileBuy = movesByTile;
  // покупка тайла — коротким тапом/кликом (тултип — по долгому нажатию)
  document.querySelectorAll(".tile.buyable").forEach((t) =>
    t.addEventListener("click", () => doMove(movesByTile[t.dataset.tile]))
  );
}

const RACE_ORDER = ["elves", "hobbits", "humans", "dwarves", "ents", "wizards"];

function renderRaces() {
  const raceChip = (i) =>
    `<div class="race-vp ${i ? "s" : "f"}"
       title="${SIDE_RU[i]}: races in support (6 wins by races)">
       ${i ? "🏇" : "🧝"} ${G.players[i].race_victory_count}/6</div>`;
  $("#race-vps").innerHTML = raceChip(0) + raceChip(1);
  $("#race-row").innerHTML = RACE_ORDER.filter((r) => r in G.alliance_stacks)
    .map((race) => {
      const st = G.alliance_stacks[race];
      const n = typeof st === "number" ? st : st.count;
      const tokens = typeof st === "number" ? [] : st.tokens;
      const pop = tokens.length
        ? `<div class="race-pop"><b>In the stack (order unknown):</b>${tokens
            .map(
              (t) =>
                `<div class="race-pop-chip"><img class="tok-art" src="/static/art/tokens/${t.id}.png">
                 <span class="tok-txt">${t.text}</span></div>`
            )
            .join("")}</div>`
        : "";
      const lockedBy = (G.locked_stacks || {})[race];
      const lock =
        lockedBy === undefined
          ? ""
          : `<img class="power-lock" draggable="false" src="/static/art/allies/power-small.png"
               title="Shelob: stack locked, only ${SIDE_RU[lockedBy]} can draw or look">`;
      return `<div class="race-token-art">
        <img draggable="false" src="/static/art/tokens/_back_${race}.png">
        <small>×${n}</small>${lock}${pop}
      </div>`;
    })
    .join("");
}

/* ---------- DLC Allies ---------- */

// Хот-сит: рука обоих приезжает в браузер, но по умолчанию закрыта.
// Два независимых способа подсмотреть — кнопка (залипающая) и наведение
// (пока курсор в зоне). Кнопка всегда главнее: если ею закрыли, наведение
// не открывает, пока курсор не выйдет и не вернётся (иначе «скрыть» под
// курсором мгновенно отменяется наведением и выглядит сломанной).
const allyPeek = { turn: -1, sticky: false, hover: false, muted: false };

function allyPeekReset() {
  allyPeek.sticky = allyPeek.hover = allyPeek.muted = false;
  allyPeek.turn = -1;
}

// перерисовываем руки, только если видимость реально изменилась: иначе
// перерисовка подсовывает под курсор новый элемент, он шлёт mouseenter,
// тот снова перерисовывает — и так по кругу
function setAllyPeek(patch) {
  if (!G) return;
  const before = allyHandOpen(G.current);
  if (allyPeek.turn !== G.turn_no) allyPeekReset();
  Object.assign(allyPeek, patch);
  allyPeek.turn = G.turn_no;
  if (allyHandOpen(G.current) !== before) {
    renderPanels();
    renderHand();
  }
}

const ALLY_BACK = ["_back_brotherhood", "_back_sauron"];

// «1 жетон / 2 жетона / 5 жетонов» — счётчик на виду весь ход, режет глаз
function plural(n, one, few, many) {
  const m100 = n % 100;
  if (m100 >= 11 && m100 <= 14) return many;
  const m10 = n % 10;
  if (m10 === 1) return one;
  if (m10 >= 2 && m10 <= 4) return few;
  return many;
}

function allyHandOpen(seat) {
  if (!G.allies) return false;
  if (ROOM && ROOM.mode === "hotseat") {
    if (seat !== G.current) return false; // чужую руку не показываем никогда
    if (allyPeek.turn !== G.turn_no) return false; // новый ход — снова закрыто
    return allyPeek.sticky || allyPeek.hover;
  }
  return seat === mySeat(); // своё устройство — своя рука всегда открыта
}

// ходы призыва, привязанные к конкретной карте: играем ТАП ПО КАРТЕ,
// а не только кнопкой в общем меню выбора
function allyMovesFor(id) {
  if (!G || !canAct()) return [];
  return (G.moves || []).filter(
    (m) => (m.type === "ally_enter" || m.type === "ally_exit") && m.ally === id
  );
}

function allyCard(a, cls) {
  const playable = allyMovesFor(a.id).length ? " playable" : "";
  return `<div class="ally ${cls}${playable}" data-ally="${a.id}">
    <img draggable="false" src="/static/art/allies/${a.id}.jpg">
    <div class="card-pop"><b>${a.name}</b>
      <div class="ally-eff"><i>Summon (1 token):</i> ${a.enter}</div>
      <div class="ally-eff"><i>Farewell (2 tokens):</i> ${a.exit}</div>
    </div>
  </div>`;
}

function allyBack(seat) {
  return `<div class="ally back">
    <img draggable="false" src="/static/art/allies/${ALLY_BACK[seat]}.jpg">
  </div>`;
}

// карта руки, у которой сейчас открыто меню действий: она остаётся лицом
// вверх, даже когда остальная рука уже спрятана
function pinnedAlly(seat) {
  if (!chooserEl || !chooserAnchor || !chooserAnchor.dataset || !chooserAnchor.dataset.ally) return null;
  const row = chooserAnchor.closest(".ally-row");
  return row && row.dataset.hand === String(seat) ? chooserAnchor.dataset.ally : null;
}

function alliesBlock(seat) {
  if (!G.allies) return "";
  const pl = G.players[seat];
  const open = allyHandOpen(seat);
  const pinned = pinnedAlly(seat);
  const hand = open
    ? pl.ally_hand.map((a) => allyCard(a, "hand")).join("")
    : pinned && pl.ally_hand && pl.ally_hand.length === pl.ally_hand_count
      ? pl.ally_hand.map((a) => (a.id === pinned ? allyCard(a, "hand") : allyBack(seat))).join("")
      : Array.from({ length: pl.ally_hand_count }, () => allyBack(seat)).join("");
  // кнопка «показать руку» нужна только без мыши: с мышью рука открывается наведением
  const peekable =
    !HAS_HOVER && ROOM && ROOM.mode === "hotseat" && seat === G.current && pl.ally_hand_count;
  const peek = peekable
    ? `<button class="btn small ally-peek" data-peek="${open ? "0" : "1"}">
         ${open ? "🙈 hide hand" : "👁 show my hand"}</button>`
    : "";
  const rows = [];
  if (pl.ally_hand_count)
    rows.push(`<div class="ally-row" data-hand="${seat}">${hand}</div>`);
  if (pl.ally_open.length)
    rows.push(
      `<div class="ally-row">${pl.ally_open.map((a) => allyCard(a, "open")).join("")}</div>`
    );
  if (pl.ally_gone.length)
    rows.push(
      `<div class="ally-row">${pl.ally_gone.map((a) => allyCard(a, "gone")).join("")}</div>`
    );
  const locks = G.quest_locks && G.quest_locks[seat]
    ? `<span class="ally-lock" title="Tom Bombadil: Ring track steps
needed to remove tokens before moving">🚫💍 ${G.quest_locks[seat]}</span>`
    : "";
  return `<div class="allies-box">
    <div class="power-line">
      <img class="power-ico" draggable="false" src="/static/art/allies/power-small.png">
      <b>${pl.power}</b> <span class="power-cap">${plural(pl.power, "Power token", "Power tokens", "Power tokens")}</span>${locks}${peek}
    </div>
    ${rows.join("")}
  </div>`;
}

const HAS_HOVER = window.matchMedia && window.matchMedia("(hover: hover)").matches;

// Снять глушилку наведения, когда курсор реально ушёл из зоны руки.
// На mouseleave полагаться нельзя: перерисовка подменяет элемент под курсором,
// и браузер шлёт boundary-события уже другому узлу — «скрыть» залипало навсегда.
function armUnmute() {
  const off = (ev) => {
    if (ev.target && ev.target.closest && ev.target.closest(".ally-row[data-hand]")) return;
    allyPeek.muted = false;
    document.removeEventListener("pointermove", off, true);
  };
  document.addEventListener("pointermove", off, true);
}

function bindAllies(root) {
  if (!root) return;
  root.querySelectorAll(".ally-peek").forEach((b) =>
    b.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const show = b.dataset.peek === "1";
      // закрыли кнопкой, а курсор всё ещё над зоной — глушим наведение
      // до тех пор, пока курсор не уйдёт и не вернётся
      setAllyPeek({ sticky: show, hover: show ? allyPeek.hover : false, muted: !show });
      if (!show) armUnmute();
    })
  );
  // наведение — только там, где есть настоящая мышь; на тач-экране кнопка
  if (HAS_HOVER && ROOM && ROOM.mode === "hotseat") {
    root.querySelectorAll(".ally-row[data-hand]").forEach((row) => {
      if (Number(row.dataset.hand) !== G.current) return;
      row.addEventListener("mouseenter", () => {
        if (!allyPeek.muted) setAllyPeek({ hover: true });
      });
      row.addEventListener("mouseleave", () => setAllyPeek({ hover: false, muted: false }));
    });
  }
  root.querySelectorAll(".ally-row").forEach(bindHandZones);
}

/* Веер руки: карты лежат внахлёст, и увеличенная карта накрывает соседку.
   Если полагаться на :hover, курсор «залипает» на поднятой карте и до соседней
   не добраться — как в настольном симуляторе, целимся не по видимой картинке,
   а по ЗОНЕ вдоль руки: у каждой карты своя полоса по X, ширина полосы равна
   шагу нахлёста (у последней — вся её ширина). Подъём делается трансформом
   картинки, поэтому прямоугольник самой карты не меняется и зоны стабильны. */
function handCards(row) {
  return [...row.children].filter((c) => c.classList.contains("ally"));
}

function handZoneIndex(row, x) {
  const cards = handCards(row);
  if (!cards.length) return -1;
  const r = cards.map((c) => c.getBoundingClientRect());
  if (x < r[0].left || x > r[r.length - 1].right) return -1;
  for (let i = 0; i < cards.length; i++) {
    const right = i < cards.length - 1 ? r[i + 1].left : r[i].right;
    if (x < right) return i;
  }
  return cards.length - 1;
}

function setHandHover(row, idx) {
  const cards = handCards(row);
  // пока открыто меню действий у карты этой руки, она остаётся поднятой,
  // даже если курсор ушёл: иначе меню висит над уже спрятанной картой
  if (chooserEl && chooserAnchor && row.contains(chooserAnchor)) {
    const pinned = cards.indexOf(chooserAnchor);
    if (pinned >= 0 && idx !== pinned) idx = pinned;
  }
  if (row._hovIdx === idx) return;
  row._hovIdx = idx;
  cards.forEach((c, i) => c.classList.toggle("hov", i === idx));
  hidePop();
  if (idx >= 0) showPop(cards[idx], false, true);
}

function bindHandZones(row) {
  row._hovIdx = undefined;
  // перерисовка (опрос состояния раз в секунду) подменяет карты под открытым
  // меню — перевешиваем якорь на новую карту, чтобы она осталась поднятой
  if (chooserEl && chooserAnchor && chooserAnchor.dataset && chooserAnchor.dataset.ally) {
    const oldRow = chooserAnchor.closest(".ally-row");
    if (oldRow && oldRow.dataset.hand === row.dataset.hand) {
      const cards = handCards(row);
      const idx = cards.findIndex((c) => c.dataset.ally === chooserAnchor.dataset.ally);
      if (idx >= 0) {
        chooserAnchor = cards[idx];
        row._hovIdx = idx;
        cards.forEach((c, i) => c.classList.toggle("hov", i === idx));
      }
    }
  }
  row.addEventListener("pointermove", (e) => {
    if (e.pointerType === "touch") return; // на тач-экране работает тап
    setHandHover(row, handZoneIndex(row, e.clientX));
  });
  row.addEventListener("pointerleave", () => setHandHover(row, -1));
  row.addEventListener("click", (e) => {
    const idx = handZoneIndex(row, e.clientX);
    if (idx < 0) return;
    const card = handCards(row)[idx];
    const moves = allyMovesFor(card.dataset.ally);
    if (!moves.length) return;
    e.stopPropagation();
    closeChooser(); // снять пин с прежней карты до подъёма новой
    setHandHover(row, idx);
    showChooser(card, moves);
    hidePop(); // подсказка и меню оба под картой — меню важнее
  });
}

function renderPanels() {
  for (const i of [0, 1]) {
    const pl = G.players[i];
    const el = document.querySelector(`#panel-${i} .panel-body`);
    const byType = {};
    for (const c of pl.played) (byType[c.type] = byType[c.type] || []).push(c);
    const cardsHtml = TYPE_ORDER.filter((t) => byType[t])
      .map(
        (t) =>
          `<div class="stack-col">` +
          byType[t]
            .map(
              (c) =>
                `<div class="stk"><img draggable="false" src="/static/art/cards/${c.id}.jpg">
                 <div class="card-pop">${cardTooltip(c)}</div></div>`
            )
            .join("") +
          `</div>`
      )
      .join("");
    el.innerHTML = coinify(`
      <div class="coins">🪙 ${pl.coins}</div>
      <div class="stat">regions: ${pl.presence} / 7 · races: ${pl.race_victory_count} / 6</div>
      <div class="stat">units in supply: ${pl.supply}</div>
      ${pl.tokens.length ? `<div class="tokens-art">${pl.tokens.map((t) => `<span class="tok-wrap"><img class="tok-art ${t.kind === "instant" ? "used" : ""}" src="/static/art/tokens/${t.id}.png"><span class="tok-pop">${t.text}${t.kind === "instant" ? " <i>(used)</i>" : ""}</span></span>`).join("")}</div>` : ""}
      ${alliesBlock(i)}
      <div class="stacks">${cardsHtml}</div>
      ${pl.last_action ? `<div class="last-action">${pl.last_action}</div>` : ""}`);
    const panel = document.getElementById(`panel-${i}`);
    panel.classList.toggle("active", G.current === i && !G.winner);
    const ended = G.winner !== null && G.winner !== undefined;
    panel.classList.toggle("won", ended && G.winner === i);
    panel.classList.toggle("lost", ended && G.winner === 1 - i);
    let badge = "";
    if (ended && G.winner === i) badge = '<div class="result-badge win">🏆 VICTORY! 🎉</div>';
    else if (ended && G.winner === 1 - i) badge = '<div class="result-badge lose">💀 Defeat</div>';
    else if (ended) badge = '<div class="result-badge draw">🤝 Draw</div>';
    el.insertAdjacentHTML("afterbegin", badge);
  }
  // привязываемся строго внутри перерисованных панелей: общий по документу
  // querySelectorAll вешал бы дубли обработчиков на оверлей руки
  for (const i of [0, 1]) bindAllies(document.getElementById(`panel-${i}`));
}

// финал партии: подсвечиваем не только блок, но и КОНКРЕТНЫЙ индикатор причины
// (плашка присутствия на карте / счётчик рас / шаги по Пути Кольца) — он мигает.
function winGlowTargets(reason, side) {
  switch (reason) {
    case "quest":
      return {
        box: ".quest",
        chips: [`#quest-vp .race-vp.${side}`],
        art: [side === "f" ? ".ring-art .ring-strip" : ".ring-art .ring-nazgul"],
      };
    case "races":
      // мигает только счётчик «N/6» — сами жетоны не обводим
      return { box: ".supply-row", chips: [`#race-vps .race-vp.${side}`], art: [] };
    case "conquest":
    case "presence":
      return { box: ".mid-row .board", chips: [`.map-vp.${side}`], art: [] };
    default:
      return null;
  }
}

let _winGlowShown = false;

function renderWinGlow() {
  document
    .querySelectorAll(".vp-glow, .vp-flash, .vp-flash-art")
    .forEach((e) => e.classList.remove("vp-glow", "vp-flash", "vp-flash-art", "vp-lose"));
  if (!G || G.winner === null || G.winner === undefined || G.winner === "draw") {
    _winGlowShown = false;
    return;
  }
  const t = winGlowTargets(G.win_reason, G.winner === 1 ? "s" : "f");
  if (!t) return;
  const lost = mySeat() !== G.winner;
  const mark = (sel, cls) =>
    document.querySelectorAll(sel).forEach((el) => {
      el.classList.add(cls);
      if (lost) el.classList.add("vp-lose");
    });
  mark(t.box, "vp-glow");
  t.chips.forEach((s) => mark(s, "vp-flash"));
  t.art.forEach((s) => mark(s, "vp-flash-art"));
  if (!_winGlowShown) {
    // один раз довозим экран до причины финала — иначе мигание можно не увидеть
    _winGlowShown = true;
    const box = document.querySelector(t.box);
    if (box) setTimeout(() => box.scrollIntoView({ behavior: "smooth", block: "center" }), 400);
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

// человеческая причина финала (подписываем ею и мигающий индикатор)
const WIN_WHY = { quest: "Ring Path", races: "race support", conquest: "conquest of Middle-earth", presence: "presence" };

function renderTurn() {
  const tb = $("#turnbar");
  if (G.winner !== null && G.winner !== undefined) {
    const txt =
      G.winner === "draw" ? "Draw!" : `Winner: ${SIDE_RU[G.winner]}`;
    const why = WIN_WHY[G.win_reason] || "";
    tb.innerHTML = `🏆 ${txt} <small>(${why})</small>`;
    tb.className = "turnbar winner";
  } else {
    let who = "";
    if (ROOM && ROOM.mode !== "hotseat")
      who = actorSeat() === ROOM.seat
        ? " — your turn"
        : ["bot", "tutorial"].includes(ROOM.mode) ? "" : " — waiting for opponent";
    if (G.waiting) who = " — ⏳ opponent has not joined yet";
    tb.innerHTML = `Chapter ${G.chapter} · turn ${G.turn_no} · to move: <b class="${G.current ? "s" : "f"}">${SIDE_RU[G.current]}</b>${who}`;
    tb.className = "turnbar";
  }
  $("#reserve").textContent = `🪙 reserve: ${G.reserve}`;

  renderPrompt();
}

const MAP_TYPES = ["place", "move", "kill", "retreat", "lock_link"]; // управляются кликами по карте
let _mapPendingKey = null;
let _extraOfferShown = false; // чтобы подскроллить к вопросу ровно один раз

function renderPrompt() {
  const pr = $("#prompt");
  // на десктопе рука союзников видна в панели — призываем тапом по карте,
  // и дублировать это кнопками сверху незачем; на телефоне панелей нет,
  // рука живёт в оверлее, поэтому кнопки остаются единственным путём
  const handOnScreen = window.innerWidth > 820;
  const hidden = ["play", "discard", "tile", "shire_pick"];
  if (handOnScreen) hidden.push("ally_enter", "ally_exit");
  const all = canAct() ? G.moves.filter((m) => !hidden.includes(m.type)) : [];
  const isDiscard = G.pending && G.pending.type === "play_from_discard";
  const canSkip = all.some((m) => m.type === "skip");
  const btnMoves = all.filter((m) => !MAP_TYPES.includes(m.type) && m.type !== "skip");
  const mapMoves = all.filter((m) => MAP_TYPES.includes(m.type));
  const isExtraOffer = !!(G.pending && G.pending.type === "extra_turn_offer") && canAct();
  if (!isExtraOffer) _extraOfferShown = false;

  const skipBtn = () => {
    const b = document.createElement("button");
    b.className = "btn small ghost";
    b.textContent = "Skip";
    b.addEventListener("click", () => doMove({ type: "skip", label: "Skip" }));
    return b;
  };

  if (isDiscard) {
    pr.style.display = "";
    pr.innerHTML =
      `<div class="prompt-title">Play any sold card for free:</div>` +
      `<div class="prompt-btns"></div>`;
    const box = pr.querySelector(".prompt-btns");
    for (const m of all.filter((m) => m.type === "discard_play")) {
      const card = G.discard_open[m.index];
      const d = document.createElement("div");
      d.className = "discard-pick";
      d.innerHTML = `<img src="/static/art/cards/${card.id}.jpg">`;
      d.title = m.label;
      d.addEventListener("click", () => doMove(m));
      box.appendChild(d);
    }
    if (canSkip) box.appendChild(skipBtn());
  } else if (G.pending && G.pending.type === "ally_offer" && canAct()) {
    // Вопрос про призыв обязан быть виден ВСЕГДА и всегда иметь выход:
    // на десктопе призыв делается тапом по карте, поэтому кнопок призыва тут
    // нет — и без явной кнопки «Завершить ход» ход просто застревал.
    pr.style.display = "";
    pr.innerHTML =
      `<div class="prompt-title">You gained a Power token. Summon an ally?` +
      (handOnScreen ? " Click a card in your hand." : "") +
      `</div><div class="prompt-btns"></div>`;
    const box = pr.querySelector(".prompt-btns");
    for (const m of btnMoves) {
      const b = document.createElement("button");
      b.className = "btn small";
      b.innerHTML = coinify(m.label);
      b.addEventListener("click", () => doMove(m));
      box.appendChild(b);
    }
    const end = document.createElement("button");
    end.className = "btn small ghost";
    end.textContent = "➡ End turn";
    end.addEventListener("click", () => doMove({ type: "skip", label: "Skip" }));
    box.appendChild(end);
  } else if (G.pending && G.pending.type === "shire_play" && canAct()) {
    pr.style.display = "";
    pr.innerHTML = `<div class="prompt-title">The Shire: choose a visible card in the layout</div>`;
    pr.appendChild(skipBtn());
  } else if (isExtraOffer && btnMoves.length) {
    // доп. ход с трека — отдельный явный вопрос, кнопки вверху экрана
    pr.style.display = "";
    pr.innerHTML =
      `<div class="prompt-title">🔄 Ring track bonus: take another turn?</div>` +
      `<div class="prompt-btns"></div>`;
    const box = pr.querySelector(".prompt-btns");
    for (const m of btnMoves) {
      const b = document.createElement("button");
      b.className = "btn small" + (m.take ? "" : " ghost");
      b.textContent = m.take ? "🔄 Take another turn" : "➡ Pass the turn";
      b.addEventListener("click", () => doMove(m));
      box.appendChild(b);
    }
    if (!_extraOfferShown) {
      _extraOfferShown = true; // спросили впервые — покажем вопрос, а не низ страницы
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  } else if (btnMoves.length) {
    // не-картовые выборы (доп. ход, жетоны, расы) — кнопками
    pr.style.display = "";
    const why = G.pending && G.pending.why ? ` (${G.pending.why})` : "";
    pr.innerHTML = `<div class="prompt-title">Choose${why}:</div><div class="prompt-btns"></div>`;
    const box = pr.querySelector(".prompt-btns");
    for (const m of btnMoves.slice(0, 60)) {
      const b = document.createElement("button");
      b.className = "btn small";
      b.innerHTML = coinify(m.label);
      b.addEventListener("click", () => doMove(m));
      box.appendChild(b);
    }
    if (canSkip) box.appendChild(skipBtn());
  } else if (mapMoves.length) {
    // действие по карте — регионы сами подсвечиваются; текст-подсказку НЕ показываем,
    // только кнопку «Пропустить» (если действие опционально) + автоскролл к карте
    const key = mapMoves.map((m) => m.type + (m.region || m.to || "")).join();
    if (canSkip) {
      pr.style.display = "";
      pr.innerHTML = `<div class="prompt-btns"></div>`;
      pr.querySelector(".prompt-btns").appendChild(skipBtn());
    } else {
      pr.style.display = "none";
      pr.innerHTML = "";
    }
    if (key !== _mapPendingKey && window.innerWidth <= 820) {
      document.querySelector(".board").scrollIntoView({ behavior: "smooth", block: "center" });
    }
    _mapPendingKey = key;
  } else {
    pr.style.display = "none";
    pr.innerHTML = "";
    _mapPendingKey = null;
  }
}

// в логе красим стороны фамильными цветами: Братство — синий, Саурон — тёмно-красный
function colorSides(text) {
  return text
    .replace(/Fellowship/g, (m) => `<b class="f">${m}</b>`)
    .replace(/Sauron/g, (m) => `<b class="s">${m}</b>`);
}

// в состоянии приходит только хвост журнала (он опрашивается раз в секунду);
// полную историю подтягиваем отдельным запросом при открытии оверлея и дописываем хвостом
let _fullLog = null;
const _logHtml = {};

function mergeTail(full, tail) {
  for (let k = Math.min(full.length, tail.length); k > 0; k--) {
    if (full.slice(-k).every((l, i) => l === tail[i])) return full.concat(tail.slice(k));
  }
  return full.concat(tail);
}

function paintLog(sel, lines) {
  const el = $(sel);
  if (!el) return;
  const html = coinify(lines.map((l) => `<div>${colorSides(l)}</div>`).join(""));
  if (html === _logHtml[sel]) return; // ничего не изменилось — не трогаем скролл читателя
  _logHtml[sel] = html;
  // если читатель отлистал вверх — не дёргаем его вниз при каждом обновлении
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  el.innerHTML = html;
  if (atBottom) el.scrollTop = el.scrollHeight;
}

function renderLog() {
  if (_fullLog) _fullLog = mergeTail(_fullLog, G.log);
  paintLog("#game-log", G.log);
  paintLog("#log-full", _fullLog || G.log);
}

/* ---------- мобильный статус-бар + док своих карт ---------- */

function mySeat() {
  if (ROOM && ROOM.mode !== "hotseat") return ROOM.seat;
  return actorSeat() ?? 0;
}

function renderMobile() {
  const seat = mySeat();
  const pl = G.players[seat];
  const opp = G.players[1 - seat];
  const ended = G.winner !== null && G.winner !== undefined;

  const mt = $("#m-turn");
  if (ended) {
    const why = WIN_WHY[G.win_reason] ? `: ${WIN_WHY[G.win_reason]}` : "";
    mt.textContent =
      G.winner === seat ? `🏆 Victory${why}` : G.winner === "draw" ? "🤝 Draw" : `💀 Defeat${why}`;
    mt.className = "";
  } else if (G.waiting) {
    mt.textContent = "⏳ Waiting for opponent";
    mt.className = "";
  } else if (canAct()) {
    mt.textContent = "▶ Your turn";
    mt.className = "my";
  } else {
    mt.textContent = "⏳ Opponent's turn…";
    mt.className = "";
  }
  // сверху справа — жетоны содружества соперника (тап → полный расклад врага)
  const oppToks = ended ? [] : opp.tokens || []; // в финале место нужно под причину победы
  const oppPower =
    G.allies && !ended
      ? `<span class="m-power" title="opponent's Power tokens"><img src="/static/art/allies/power-small.png">${opp.power}</span>`
      : "";
  $("#m-opp").innerHTML = oppPower + (oppToks.length
    ? `<span class="opp-toks ${seat === 1 ? "f" : "s"}" id="opp-toks" title="opponent's alliance tokens">🛡` +
      oppToks
        .slice(0, 3)
        .map(
          (t) =>
            `<img src="/static/art/tokens/${t.id}.png" class="${t.kind === "instant" ? "used" : ""}">`
        )
        .join("") +
      (oppToks.length > 3 ? `<b>+${oppToks.length - 3}</b>` : "") +
      `</span>`
    : "");

  // нижний бар: слева мои деньги, справа деньги врага (цвет по фракции)
  const oppSeat = 1 - seat;
  // жетоны Силы стоят рядом с монетами: это вторая валюта хода
  const powerChip = (p) =>
    G.allies
      ? ` <span class="m-power" title="Power tokens"><img src="/static/art/allies/power-small.png">${p.power}</span>`
      : "";
  // мои жетоны — рядом со своими монетами; жетоны соперника не влезают
  // в нижний бар на 360–390px, поэтому живут в верхнем баре рядом с его щитом
  $("#dock-coins").innerHTML = coinify(`🪙 ${pl.coins}`) + powerChip(pl);
  $("#dock-coins").className = "dock-coin " + (seat === 1 ? "s" : "f");
  $("#dock-opp-coins").innerHTML = coinify(`🪙 ${opp.coins}`);
  $("#dock-opp-coins").className = "dock-coin " + (oppSeat === 1 ? "s" : "f");

  // слева — мои зелёные карты (расы), справа — накопленные жетоны
  const greens = pl.played.filter((c) => c.type === "green");
  $("#dock-races").innerHTML = greens.length
    ? greens.map((c) => `<img src="/static/art/cards/${c.id}.jpg">`).join("") +
      `<span class="dock-rc">${pl.race_victory_count}/6</span>`
    : `<span class="dock-empty">races ${pl.race_victory_count}/6</span>`;
  $("#dock-tokens").innerHTML = pl.tokens.length
    ? pl.tokens
        .map(
          (t) =>
            `<span class="dock-tok"><img src="/static/art/tokens/${t.id}.png" class="${
              t.kind === "instant" ? "used" : ""
            }"><span class="tok-tip">${t.text}${
              t.kind === "instant" ? " <i>(used)</i>" : ""
            }</span></span>`
        )
        .join("")
    : "";

  renderHand();
}

let handWho = "me"; // "me" | "opp" | "sold"

// сводка игрока в оверлее: деньги/регионы/расы + жетоны содружества (их не видно в доке у врага)
function handSummary(seat) {
  const pl = G.players[seat];
  const toks = pl.tokens.length
    ? pl.tokens
        .map(
          (t) =>
            `<span class="dock-tok hand-tok"><img src="/static/art/tokens/${t.id}.png" class="${
              t.kind === "instant" ? "used" : ""
            }"><span class="tok-tip">${t.text}${
              t.kind === "instant" ? " <i>(used)</i>" : ""
            }</span></span>`
        )
        .join("")
    : `<span class="dock-empty">no alliance tokens yet</span>`;
  return coinify(
    `<div class="hand-stat">🪙 ${pl.coins} · regions ${pl.presence}/7 · races ${pl.race_victory_count}/6</div>` +
      `<div class="hand-toks">${toks}</div>` +
      (pl.tokens.length ? `<div class="hand-hint">alliance tokens: tap to read</div>` : "")
  );
}

function renderHand() {
  if (!G || G.empty) return;
  let cards, title, sum = "";
  if (handWho === "sold") {
    cards = G.discard_open || [];
    title = "Sold / discarded";
  } else {
    const seat = handWho === "me" ? mySeat() : 1 - mySeat();
    cards = G.players[seat].played;
    title = handWho === "me" ? "My cards" : `Cards: ${SIDE_RU[1 - mySeat()]}`;
    sum = handSummary(seat);
  }
  // союзники живут в том же оверлее: на телефоне боковых панелей нет
  if (handWho !== "sold" && G.allies) {
    sum += alliesBlock(handWho === "me" ? mySeat() : 1 - mySeat());
  }
  $("#hand-sum").innerHTML = sum;
  $("#hand-title").textContent = title;
  $("#hand-me").classList.toggle("on", handWho === "me");
  $("#hand-opp").classList.toggle("on", handWho === "opp");
  const byType = {};
  for (const c of cards) (byType[c.type] = byType[c.type] || []).push(c);
  $("#hand-full").innerHTML =
    TYPE_ORDER.filter((t) => byType[t])
      .map(
        (t) =>
          `<div class="stack-col">` +
          byType[t]
            .map(
              (c) =>
                `<div class="stk"><img draggable="false" src="/static/art/cards/${c.id}.jpg">
                 <div class="card-pop">${cardTooltip(c)}</div></div>`
            )
            .join("") +
          `</div>`
      )
      .join("") || "<p class='small'>no cards yet</p>";
  bindAllies($("#hand-overlay"));
}

/* ---------- автома: карта решения и ход рассуждений ---------- */

const DEC_COLORS = {
  grey: "#8f96a3", yellow: "#d9b23a", green: "#3f9d4e",
  blue: "#2f6fb8", red: "#c0392b", purple: "#8e44ad",
};
const DEC_REP_ICON = { shelob: "🕷", grond: "🐏" };

function decSlotHtml(slot) {
  const cols = slot.colors.map((c) => DEC_COLORS[c] || "#888");
  let bg = cols[0];
  if (cols.length === 2) bg = `linear-gradient(135deg, ${cols[0]} 0 50%, ${cols[1]} 50% 100%)`;
  if (cols.length >= 3)
    bg = `linear-gradient(135deg, ${cols[0]} 0 33%, ${cols[1]} 33% 66%, ${cols[2]} 66% 100%)`;
  return `<span class="dec-slot${slot.pref ? " pref" : ""}" style="background:${bg}"
    title="${slot.label}">${slot.pref ? "★" : ""}</span>`;
}

function decCardHtml(card) {
  if (!card) return `<span class="dec-none">no decision card revealed yet</span>`;
  const slots = card.slots.map(decSlotHtml).join(`<span class="dec-arrow">›</span>`);
  const rep = card.repeat
    ? `<span class="dec-rep${card.repeat_matches ? " hit" : ""}"
        title="Repeat symbol${card.repeat_matches ? ": matches the character, extra turn!" : " (inactive for this character)"}">${DEC_REP_ICON[card.repeat]}</span>`
    : "";
  const dirTip = card.direction === "lr" ? "scan the layout left to right" : "scan the layout right to left";
  return `<span class="dec-card">${slots}${rep}
    <span class="dec-dir" title="${dirTip}">${card.direction === "lr" ? "→" : "←"}</span></span>`;
}

function renderAutoma() {
  const bar = $("#automa-bar");
  if (!bar) return;
  const a = G && G.automa;
  if (!a) { bar.classList.add("hidden"); return; }
  bar.classList.remove("hidden");
  const lastDie = [...(a.trace || [])].reverse().find((t) => t.kind === "die");
  bar.innerHTML =
    `<img class="automa-mini" src="/static/art/solo/${a.art}" alt="" draggable="false">` +
    `<span class="automa-name">${a.name} <small>· automa</small></span>` +
    decCardHtml(a.card) +
    (lastDie ? `<span class="automa-die">🎲 ${lastDie.roll}</span>` : "") +
    `<span class="automa-more">how it thinks ›</span>`;
  if (!$("#automa-overlay").classList.contains("hidden")) fillAutomaOverlay();
}

function fillAutomaOverlay() {
  const a = G && G.automa;
  if (!a) return;
  $("#automa-title").textContent = `🎲 ${a.name} — automa`;
  $("#automa-art").src = `/static/art/solo/${a.art}`;
  $("#automa-power").innerHTML = `<b>Character traits:</b> ${a.power}`;
  $("#automa-deckinfo").textContent =
    `Decision deck: ${a.deck} in the stack · ${a.discarded} discarded · plays cards for free, ` +
    `landmarks for coins (7/5/2 + fortresses)`;
  let dec = decCardHtml(a.card);
  if (a.card) {
    dec += `<ol class="dec-legend">${a.card.slots
      .map((s) => `<li>${s.label}</li>`)
      .join("")}</ol>`;
    dec += `<div class="dec-note">Slot order is the card priority; the arrow is the
      layout scan direction${a.card.repeat ? `; ${DEC_REP_ICON[a.card.repeat]} is the repeat symbol` : ""}.</div>`;
  }
  $("#automa-decision").innerHTML = dec;
  const tr = $("#automa-trace");
  tr.innerHTML = (a.trace || [])
    .map((t) => `<div class="tr-${t.kind}">${t.text}</div>`)
    .join("") || "<div>the automa has not moved yet</div>";
  tr.scrollTop = tr.scrollHeight;
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
  renderWinGlow();
  renderMobile();
  renderAutoma();
  if (window.TUT) TUT.onRender(); // перерисовка стирает подсветку шага — вернуть
}

/* ---------- rooms: bot / pvp / hotseat ---------- */

const PROMO_CHIP =
  ' <span class="promo-chip" title="The Shire and Grond promo tiles are in play">promo</span>';
const ALLIES_CHIP =
  ' <span class="promo-chip allies-chip" title="Allies expansion: Power tokens and ally cards">allies</span>';

function modeChips(resp) {
  return (resp.promo ? PROMO_CHIP : "") + (resp.allies ? ALLIES_CHIP : "");
}

function setRoom(resp) {
  ROOM = { id: resp.room, token: resp.token || (ROOM && ROOM.token), seat: resp.seat ?? (ROOM && ROOM.seat), mode: resp.mode };
  G = resp;
  _fullLog = null; // новая партия — историю подтянем заново
  const info = $("#room-info");
  if (resp.mode === "pvp") {
    const link = `${location.origin}/?room=${resp.room}`;
    info.innerHTML = `PvP room <code>${resp.room}</code>
      <button class="btn small" id="topbar-copy">📋 link</button>`;
    $("#topbar-copy").addEventListener("click", () => navigator.clipboard.writeText(link));
  } else if (resp.mode === "tutorial") {
    info.textContent = "🎓 tutorial";
  } else if (resp.mode === "bot") {
    info.textContent = `vs bot: ${ROOM.botLabel || resp.bot_kind}`;
  } else {
    info.textContent = "hot-seat";
  }
  info.innerHTML += modeChips(resp);
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

// бот ходит мгновенно — мигаем тем, что он забрал, ПОКА оно ещё на экране
function visibleSnapshot(state) {
  return {
    chapter: state && state.tableau ? state.tableau.chapter : null,
    slots: new Set(
      (state && state.tableau ? state.tableau.slots : [])
        .filter((s) => s.card)
        .map((s) => String(s.id))
    ),
    tiles: new Set((state && state.landmarks ? state.landmarks : []).map((lm) => lm.id)),
  };
}

async function flashBotMove(before, next) {
  const now = visibleSnapshot(next);
  let el = null;
  if (before.chapter !== null && now.chapter !== before.chapter) {
    // забрана ПОСЛЕДНЯЯ карта эпохи: id слотов новой раскладки не сравнить со старыми,
    // но на экране осталась ровно одна открытая карта — её и мигаем, до смены эпохи
    el = document.querySelector("#tableau .card.faceup");
  } else {
    const goneSlot = [...before.slots].find((id) => !now.slots.has(id));
    const goneTile = [...before.tiles].find((id) => !now.tiles.has(id));
    el = goneSlot
      ? document.querySelector(`#tableau .card[data-slot="${goneSlot}"]`)
      : goneTile
        ? document.querySelector(`.tile.art[data-tile="${goneTile}"]`)
        : null;
  }
  if (!el) return;
  el.classList.add("bot-flash");
  await new Promise((r) => setTimeout(r, 640)); // две вспышки по ~180 мс + пауза
  el.classList.remove("bot-flash");
}

// один ход бота по кнопке шага туториала (сам botIfNeeded в туториале молчит)
window.tutBotStep = async function () {
  if (!ROOM || !G) return;
  let guard = 0;
  while (G.winner === null && actorSeat() === G.bot_seat && guard++ < 10) {
    const before = visibleSnapshot(G);
    const next = await post(`/api/room/${ROOM.id}/bot_step`, { token: ROOM.token });
    await flashBotMove(before, next);
    G = next;
    renderAll();
  }
};

let botBusy = false;
async function botIfNeeded() {
  if (!ROOM || !["bot", "tutorial"].includes(ROOM.mode) || botBusy) return;
  if (window.TUT && !TUT.allowBot()) return; // в туториале бот ходит по кнопке шага
  botBusy = true;
  try {
    let guard = 0;
    while (G && G.winner === null && actorSeat() === G.bot_seat && guard++ < 80) {
      $("#turnbar").innerHTML += ' <span class="thinking">🤔 bot is thinking…</span>';
      const before = visibleSnapshot(G);
      const next = await post(`/api/room/${ROOM.id}/bot_step`, { token: ROOM.token });
      await flashBotMove(before, next); // сначала показать, ЧТО он взял, потом перерисовать
      G = next;
      renderAll();
      await new Promise((r) => setTimeout(r, 250));
    }
  } finally {
    botBusy = false;
  }
}

async function doMove(m) {
  if (!canAct()) return;
  if (window.TUT && TUT.active() && !TUT.allowMove(m)) {
    toast("🎓 Make the highlighted move first");
    return;
  }
  mapSel = null;
  try {
    G = await post(`/api/room/${ROOM.id}/move`, { token: ROOM.token, move: m });
    renderAll();
    if (window.TUT) TUT.onMoved();
    await botIfNeeded();
  } catch (e) {
    toast("Move rejected: " + e.message);
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

let pickedBot = null;
function chosenSide(id) {
  const v = $(id).value;
  return v === "random" ? Math.floor(Math.random() * 2) : Number(v);
}
async function loadBotMenu() {
  try {
    const resp = await api("/api/bots");
    const box = $("#bot-pick");
    const abox = $("#automa-pick");
    box.innerHTML = "";
    abox.innerHTML = "";
    const markPicked = (btn) =>
      document
        .querySelectorAll("#bot-pick .bot-opt, #automa-pick .bot-opt")
        .forEach((b) => b.classList.toggle("on", b === btn));
    for (const m of resp.menu || []) {
      const isAutoma = m.group === "automa";
      const btn = document.createElement("button");
      btn.className = "btn bot-opt" + (isAutoma ? " automa" : "");
      btn.dataset.id = m.id;
      btn.dataset.desc = m.desc || "";
      // у автомы — карточка персонажа с артом, у обычных ботов label с эмодзи
      btn.innerHTML = isAutoma
        ? `<img src="${m.art}" alt="" draggable="false"><span>${m.label}</span>`
        : m.label;
      btn.addEventListener("click", () => {
        pickedBot = m.id;
        markPicked(btn);
        $("#bot-desc").textContent = m.desc || "";
        // герои играют оба режима (E10: один универсал); автома — только базу
        const al = $("#bot-allies");
        if (al) {
          al.disabled = isAutoma;
          if (isAutoma) al.checked = false;
          al.closest("label").classList.toggle("off", isAutoma);
        }
      });
      (isAutoma ? abox : box).appendChild(btn);
    }
    document
      .querySelector(".automa-title")
      .classList.toggle("hidden", !abox.querySelector(".bot-opt"));
    const first = box.querySelector(".bot-opt");
    if (first) first.click(); // выбрать первого (чемпионку) по умолчанию
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

for (const id of ["cb-bot", "cb-pvp"]) {
  const el = document.getElementById(id);
  if (!el) continue;
  el.checked = cbMode();
  el.addEventListener("change", () => {
    localStorage.setItem("cbMode", el.checked ? "1" : "0");
    for (const other of ["cb-bot", "cb-pvp"]) {
      const o = document.getElementById(other);
      if (o) o.checked = el.checked;
    }
    applyCbMode();
  });
}
applyCbMode();

$("#lobby-bot").addEventListener("click", () => showSection("lobby-bot-opts"));
$("#lobby-pvp").addEventListener("click", () => showSection("lobby-pvp-opts"));
document.querySelectorAll("[data-back]").forEach((b) =>
  b.addEventListener("click", () => showSection("lobby-main"))
);

$("#start-bot").addEventListener("click", async () => {
  const picked = document.querySelector("#bot-pick .bot-opt.on, #automa-pick .bot-opt.on");
  let resp;
  try {
    resp = await post("/api/room/new", {
      mode: "bot",
      bot: pickedBot || "mcts",
      side: chosenSide("#side-select"),
      promo: $("#promo").checked,
      allies: $("#bot-allies").checked,
    });
  } catch (e) {
    toast("Could not create the game: " + e.message);
    return;
  }
  setRoom(resp);
  ROOM.botLabel = picked ? picked.textContent : pickedBot;
  $("#room-info").textContent = `vs bot: ${ROOM.botLabel}`;
  $("#room-info").innerHTML += modeChips(resp);
  hideLobby();
  await botIfNeeded(); // if the bot's side opens the game
});

$("#lobby-hotseat").addEventListener("click", () => showSection("lobby-hotseat-opts"));

$("#start-hotseat").addEventListener("click", async () => {
  let resp;
  try {
    resp = await post("/api/room/new", {
      mode: "hotseat",
      promo: $("#hs-promo").checked,
      allies: $("#hs-allies").checked,
    });
  } catch (e) {
    toast("Could not create the game: " + e.message);
    return;
  }
  setRoom(resp);
  hideLobby();
});

$("#lobby-tutorial").addEventListener("click", async () => {
  let resp;
  try {
    resp = await post("/api/room/new", { mode: "tutorial" });
  } catch (e) {
    toast("Could not create the tutorial: " + e.message);
    return;
  }
  setRoom(resp);
  hideLobby();
  if (window.TUT) TUT.start();
});

$("#start-pvp").addEventListener("click", async () => {
  const resp = await post("/api/room/new", {
    mode: "pvp",
    side: chosenSide("#pvp-side-select"),
    promo: $("#pvp-promo").checked,
    allies: $("#pvp-allies").checked,
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
    $("#join-info").textContent = "Could not connect: " + e.message;
  }
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), 3500);
}

function leaveToLobby() {
  if (!G || G.winner !== null) { location.href = "/"; return; }
  $("#confirm-modal").classList.remove("hidden");
}
$("#to-lobby").addEventListener("click", leaveToLobby);
$("#m-lobby").addEventListener("click", leaveToLobby);
function openHand(who) {
  handWho = who;
  renderHand();
  $("#hand-overlay").classList.remove("hidden");
}
function logToBottom() {
  // свежие события внизу: на телефоне листается сам оверлей, на десктопе — блок лога
  const ov = $("#log-overlay"), el = $("#log-full");
  el.scrollTop = el.scrollHeight;
  ov.scrollTop = ov.scrollHeight;
}

$("#m-log").addEventListener("click", async () => {
  if (!G || G.empty) return;
  renderLog();
  $("#log-overlay").classList.remove("hidden");
  logToBottom();
  if (!ROOM) return;
  try {
    // вся история, а не последние 14 строк из состояния
    const r = await api(`/api/room/${ROOM.id}/log?token=${encodeURIComponent(ROOM.token)}`);
    _fullLog = r.log;
    renderLog();
    logToBottom();
  } catch (e) {
    /* сеть подвела — остаётся хвост из состояния */
  }
});
$("#log-close").addEventListener("click", () => $("#log-overlay").classList.add("hidden"));

// автома: бар открывает оверлей «как думает»
function openAutoma() {
  if (!G || !G.automa) return;
  fillAutomaOverlay();
  $("#automa-overlay").classList.remove("hidden");
}
$("#automa-bar").addEventListener("click", openAutoma);
$("#automa-bar").addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openAutoma(); }
});
$("#automa-close").addEventListener("click", () => $("#automa-overlay").classList.add("hidden"));
closeOnBackdrop("#automa-overlay");

// оверлей теперь листается целиком — свайп не должен считаться тапом по фону
function closeOnBackdrop(id) {
  const ov = $(id);
  let dragged = false;
  ov.addEventListener("touchstart", () => (dragged = false), { passive: true });
  ov.addEventListener("touchmove", () => (dragged = true), { passive: true });
  ov.addEventListener("click", (ev) => {
    if (dragged) { dragged = false; return; }
    if (ev.target === ov) ov.classList.add("hidden");
  });
}
closeOnBackdrop("#log-overlay");
$("#m-opp").addEventListener("click", (ev) => {
  if (ev.target.closest(".opp-toks")) { ev.stopPropagation(); openHand("opp"); }
});
$("#dock-all").addEventListener("click", () => openHand("me"));
$("#dock-opp").addEventListener("click", () => openHand("opp"));
$("#dock-sold").addEventListener("click", () => openHand("sold"));
$("#hand-me").addEventListener("click", () => openHand("me"));
$("#hand-opp").addEventListener("click", () => openHand("opp"));
$("#hand-close").addEventListener("click", () => $("#hand-overlay").classList.add("hidden"));
closeOnBackdrop("#hand-overlay");
let _raf;
window.addEventListener("resize", () => {
  clearTimeout(_raf);
  _raf = setTimeout(() => { if (G && !G.empty) renderAll(); }, 150);
});
$("#confirm-yes").addEventListener("click", () => (location.href = "/"));
$("#confirm-no").addEventListener("click", () =>
  $("#confirm-modal").classList.add("hidden"));
$("#confirm-modal").addEventListener("click", (ev) => {
  if (ev.target.id === "confirm-modal") $("#confirm-modal").classList.add("hidden");
});

(async function init() {
  // браузеры восстанавливают состояние чекбоксов после перезагрузки (bfcache) —
  // промо-режим включался «сам собой»; в лобби всегда стартуем с выключенного
  for (const id of ["promo", "bot-allies", "pvp-promo", "hs-promo", "pvp-allies", "hs-allies"]) {
    const el = document.getElementById(id);
    if (el) el.checked = false;
  }
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
