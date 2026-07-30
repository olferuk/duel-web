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
  empty: "Пустая клетка",
  coin: "Бонус: +1 монета из резерва",
  unit: "Бонус: выставь 1 юнита в любой регион (по желанию)",
  extra_turn: "Бонус: право дополнительного хода (по желанию)",
  destroy_fortress: "Бонус: снеси одну вражескую крепость",
  ring: "Кольцо",
  doom: "Роковая гора: дойдя сюда, Фродо уничтожает Кольцо — победа Братства",
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
    h += `<div class="map-vp f" title="${SIDE_RU[0]}: присутствие (7 — победа покорением)">${G.players[0].presence} / 7</div>`;
    h += `<div class="map-vp s" title="${SIDE_RU[1]}: присутствие (7 — победа покорением)">${G.players[1].presence} / 7</div>`;
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
  el.innerHTML = h;
  el.querySelectorAll("[data-clickable]").forEach((z) =>
    z.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onRegionClick(z.dataset.region);
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
        const tip = i === 0 ? "Старт Фродо" : SPACE_TIP[kind] || kind;
        return `<div class="ring-zone" title="Путь Фродо, клетка ${i}: ${tip}"
          style="left:${px(cx)}%;top:${(RINGL.bgCellY / RINGL.H) * 100}%"></div>`;
      }).join("")}
      ${q.nazgul_strip.map((kind, i) => {
        const [cx, cy] = RINGL.stripCells[i];
        const tip = kind === "ring"
          ? "Кольцо: здесь назгул настигает Фродо — победа Саурона"
          : SPACE_TIP[kind] || kind;
        return `<div class="ring-zone naz" title="Путь назгула, клетка ${i}: ${tip}"
          style="left:${px(stripX + cx)}%;top:${((RINGL.frodo.y + cy) / RINGL.H) * 100}%"></div>`;
      }).join("")}
    </div>`;
  $("#quest-vp").innerHTML =
    `<div class="race-vp s" title="Саурону осталось шагов, чтобы настичь Фродо">🏇 ещё ${sLeft}</div>` +
    `<div class="race-vp f" title="Братству осталось шагов до Роковой горы (победа Кольцом)">🧝 ещё ${fLeft}</div>`;
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
      if (m.type === "play" || m.type === "discard" || m.type === "shire_pick")
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
      const content = s.revealed
        ? cardFace(s.card, s.price)
        : `<span class="slot-id" style="color:#c9b280">${s.id}</span>`;
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

  // мобильный масштаб: раскладка ВСЕГДА влезает по ширине — никакого горизонтального скролла.
  // zoom (в отличие от transform) меняет и layout-бокс → высота блока тоже ужимается.
  if (isMobile) {
    const avail = el.parentElement.clientWidth - 2;
    const fit = Math.min(1, avail / width);
    el.style.width = width + "px";
    el.style.zoom = fit;
    el.style.minHeight = height + "px";
  } else {
    el.style.zoom = "";
    el.style.width = "";
    el.style.minHeight = height + "px";
  }
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
  if (c.type === "purple") return "манёвры";
  return "";
}

function renderPiles() {
  const open = G.discard_open || [];
  $("#piles").innerHTML = coinify(`
    <div class="pile facedown-pile"
      title="Отложены из игры при сетапе эпох (по 3 закрытых): в сброс не входят и в игру не вернутся">
      <span class="pile-num">${G.discard_hidden}</span><span class="pile-cap">вне игры</span>
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
          label: `Купить ${_tileBuy[id].label.match(/\((.+)\)/)?.[1] || ""}`,
          fn: () => doMove(_tileBuy[id]),
        }]
      : [];
    mobileMenu(tile, tip ? tip.innerHTML : "", actions);
    return;
  }

  const cell = e.target.closest(".ring-zone");
  if (cell) {
    const t = cell.getAttribute("title") || "";
    if (/Пустая клетка|Старт/.test(t)) { hidePopover(); return; } // пустая клетка — без тултипа
    e.stopPropagation();
    mobileMenu(cell, t, []);
    return;
  }

  const tok = e.target.closest(".race-token-art");
  if (tok) {
    e.stopPropagation();
    const pop = tok.querySelector(".race-pop");
    mobileMenu(tok, pop ? pop.innerHTML : "<b>Стопка пуста</b>", []);
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

function shortLabel(m) {
  if (m.type === "play")
    return m.chained ? "▶ Сыграть ⛓ 0🪙" : `▶ Сыграть ${m.cost}🪙`;
  if (m.type === "discard") return `🗑 Продать +${m.gain}🪙`;
  if (m.type === "shire_pick") return `Шир ${m.cost != null ? m.cost + "🪙" : ""}`;
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
        return `<div class="tile art ${m ? "buyable" : ""}" data-tile="${lm.id}">
          <img draggable="false" src="/static/art/landmarks/${lm.id}.jpg">
          ${tag}
          <div class="lm-pop"><b>${lm.name}</b><br>${LM_TEXT[lm.id] || ""}
            <div class="lm-pop-note">Эффекты: ${eff.join(" ")} · Доплата: +1🪙 за каждую свою крепость</div>
          </div>
        </div>`;
      })
      .join("") || '<div class="area-hint">нет открытых тайлов</div>');
  if (G.landmarks_deck > 0)
    $("#landmark-row").innerHTML +=
      `<div class="tile art stack" title="Закрытые тайлы в стопке">` +
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
       title="${SIDE_RU[i]}: рас в поддержке (6 — победа по расам)">
       ${i ? "🏇" : "🧝"} ${G.players[i].race_victory_count}/6</div>`;
  $("#race-vps").innerHTML = raceChip(0) + raceChip(1);
  $("#race-row").innerHTML = RACE_ORDER.filter((r) => r in G.alliance_stacks)
    .map((race) => {
      const st = G.alliance_stacks[race];
      const n = typeof st === "number" ? st : st.count;
      const tokens = typeof st === "number" ? [] : st.tokens;
      const pop = tokens.length
        ? `<div class="race-pop"><b>В стопке (порядок неизвестен):</b>${tokens
            .map(
              (t) =>
                `<div class="race-pop-chip"><img class="tok-art" src="/static/art/tokens/${t.id}.png">
                 <span class="tok-txt">${t.text}</span></div>`
            )
            .join("")}</div>`
        : "";
      return `<div class="race-token-art">
        <img draggable="false" src="/static/art/tokens/_back_${race}.png">
        <small>×${n}</small>${pop}
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
      <div class="stat">регионов: ${pl.presence} / 7 · рас: ${pl.race_victory_count} / 6</div>
      <div class="stat">юнитов в запасе: ${pl.supply}</div>
      ${pl.tokens.length ? `<div class="tokens-art">${pl.tokens.map((t) => `<span class="tok-wrap"><img class="tok-art ${t.kind === "instant" ? "used" : ""}" src="/static/art/tokens/${t.id}.png"><span class="tok-pop">${t.text}${t.kind === "instant" ? " <i>(использован)</i>" : ""}</span></span>`).join("")}</div>` : ""}
      <div class="stacks">${cardsHtml}</div>
      ${pl.last_action ? `<div class="last-action">${pl.last_action}</div>` : ""}`);
    const panel = document.getElementById(`panel-${i}`);
    panel.classList.toggle("active", G.current === i && !G.winner);
    const ended = G.winner !== null && G.winner !== undefined;
    panel.classList.toggle("won", ended && G.winner === i);
    panel.classList.toggle("lost", ended && G.winner === 1 - i);
    let badge = "";
    if (ended && G.winner === i) badge = '<div class="result-badge win">🏆 ПОБЕДА! 🎉</div>';
    else if (ended && G.winner === 1 - i) badge = '<div class="result-badge lose">💀 Поражение</div>';
    else if (ended) badge = '<div class="result-badge draw">🤝 Ничья</div>';
    el.insertAdjacentHTML("afterbegin", badge);
  }
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
const WIN_WHY = { quest: "Путь Кольца", races: "поддержка рас", conquest: "покорение Средиземья", presence: "присутствие" };

function renderTurn() {
  const tb = $("#turnbar");
  if (G.winner !== null && G.winner !== undefined) {
    const txt =
      G.winner === "draw" ? "Ничья!" : `Победа: ${SIDE_RU[G.winner]}`;
    const why = WIN_WHY[G.win_reason] || "";
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

  renderPrompt();
}

const MAP_TYPES = ["place", "move", "kill", "retreat"]; // управляются кликами по карте
let _mapPendingKey = null;
let _extraOfferShown = false; // чтобы подскроллить к вопросу ровно один раз

function renderPrompt() {
  const pr = $("#prompt");
  const all = canAct()
    ? G.moves.filter((m) => !["play", "discard", "tile", "shire_pick"].includes(m.type))
    : [];
  const isDiscard = G.pending && G.pending.type === "play_from_discard";
  const canSkip = all.some((m) => m.type === "skip");
  const btnMoves = all.filter((m) => !MAP_TYPES.includes(m.type) && m.type !== "skip");
  const mapMoves = all.filter((m) => MAP_TYPES.includes(m.type));
  const isExtraOffer = !!(G.pending && G.pending.type === "extra_turn_offer") && canAct();
  if (!isExtraOffer) _extraOfferShown = false;

  const skipBtn = () => {
    const b = document.createElement("button");
    b.className = "btn small ghost";
    b.textContent = "Пропустить";
    b.addEventListener("click", () => doMove({ type: "skip", label: "Пропустить" }));
    return b;
  };

  if (isDiscard) {
    pr.style.display = "";
    pr.innerHTML =
      `<div class="prompt-title">Сыграй бесплатно любую проданную карту:</div>` +
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
  } else if (G.pending && G.pending.type === "shire_play" && canAct()) {
    pr.style.display = "";
    pr.innerHTML = `<div class="prompt-title">Шир: выбери видимую карту в раскладке</div>`;
    pr.appendChild(skipBtn());
  } else if (isExtraOffer && btnMoves.length) {
    // доп. ход с трека — отдельный явный вопрос, кнопки вверху экрана
    pr.style.display = "";
    pr.innerHTML =
      `<div class="prompt-title">🔄 Бонус трека Кольца: сходить ещё раз?</div>` +
      `<div class="prompt-btns"></div>`;
    const box = pr.querySelector(".prompt-btns");
    for (const m of btnMoves) {
      const b = document.createElement("button");
      b.className = "btn small" + (m.take ? "" : " ghost");
      b.textContent = m.take ? "🔄 Сходить ещё раз" : "➡ Передать ход противнику";
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
    pr.innerHTML = `<div class="prompt-title">Выбор${why}:</div><div class="prompt-btns"></div>`;
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
    .replace(/Братств(?:о|а|у|ом|е)(\sКольца)?/g, (m) => `<b class="f">${m}</b>`)
    .replace(/Саурон(?:ом|а|у|е)?/g, (m) => `<b class="s">${m}</b>`);
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
      G.winner === seat ? `🏆 Победа${why}` : G.winner === "draw" ? "🤝 Ничья" : `💀 Поражение${why}`;
    mt.className = "";
  } else if (G.waiting) {
    mt.textContent = "⏳ Ждём соперника";
    mt.className = "";
  } else if (canAct()) {
    mt.textContent = "▶ Твой ход";
    mt.className = "my";
  } else {
    mt.textContent = "⏳ Ход соперника…";
    mt.className = "";
  }
  // сверху справа — жетоны содружества соперника (тап → полный расклад врага)
  const oppToks = ended ? [] : opp.tokens || []; // в финале место нужно под причину победы
  $("#m-opp").innerHTML = oppToks.length
    ? `<span class="opp-toks ${seat === 1 ? "f" : "s"}" id="opp-toks" title="жетоны содружества соперника">🛡` +
      oppToks
        .slice(0, 3)
        .map(
          (t) =>
            `<img src="/static/art/tokens/${t.id}.png" class="${t.kind === "instant" ? "used" : ""}">`
        )
        .join("") +
      (oppToks.length > 3 ? `<b>+${oppToks.length - 3}</b>` : "") +
      `</span>`
    : "";

  // нижний бар: слева мои деньги, справа деньги врага (цвет по фракции)
  const oppSeat = 1 - seat;
  $("#dock-coins").innerHTML = coinify(`🪙 ${pl.coins}`);
  $("#dock-coins").className = "dock-coin " + (seat === 1 ? "s" : "f");
  $("#dock-opp-coins").innerHTML = coinify(`🪙 ${opp.coins}`);
  $("#dock-opp-coins").className = "dock-coin " + (oppSeat === 1 ? "s" : "f");

  // слева — мои зелёные карты (расы), справа — накопленные жетоны
  const greens = pl.played.filter((c) => c.type === "green");
  $("#dock-races").innerHTML = greens.length
    ? greens.map((c) => `<img src="/static/art/cards/${c.id}.jpg">`).join("") +
      `<span class="dock-rc">${pl.race_victory_count}/6</span>`
    : `<span class="dock-empty">рас ${pl.race_victory_count}/6</span>`;
  $("#dock-tokens").innerHTML = pl.tokens.length
    ? pl.tokens
        .map(
          (t) =>
            `<span class="dock-tok"><img src="/static/art/tokens/${t.id}.png" class="${
              t.kind === "instant" ? "used" : ""
            }"><span class="tok-tip">${t.text}${
              t.kind === "instant" ? " <i>(использован)</i>" : ""
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
              t.kind === "instant" ? " <i>(использован)</i>" : ""
            }</span></span>`
        )
        .join("")
    : `<span class="dock-empty">жетонов содружества пока нет</span>`;
  return coinify(
    `<div class="hand-stat">🪙 ${pl.coins} · регионов ${pl.presence}/7 · рас ${pl.race_victory_count}/6</div>` +
      `<div class="hand-toks">${toks}</div>` +
      (pl.tokens.length ? `<div class="hand-hint">жетоны содружества — тапни, чтобы прочитать</div>` : "")
  );
}

function renderHand() {
  if (!G || G.empty) return;
  let cards, title, sum = "";
  if (handWho === "sold") {
    cards = G.discard_open || [];
    title = "Проданные / сброшенные";
  } else {
    const seat = handWho === "me" ? mySeat() : 1 - mySeat();
    cards = G.players[seat].played;
    title = handWho === "me" ? "Мои карты" : `Карты: ${SIDE_RU[1 - mySeat()]}`;
    sum = handSummary(seat);
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
      .join("") || "<p class='small'>карт пока нет</p>";
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
}

/* ---------- rooms: bot / pvp / hotseat ---------- */

function setRoom(resp) {
  ROOM = { id: resp.room, token: resp.token || (ROOM && ROOM.token), seat: resp.seat ?? (ROOM && ROOM.seat), mode: resp.mode };
  G = resp;
  _fullLog = null; // новая партия — историю подтянем заново
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

let botBusy = false;
async function botIfNeeded() {
  if (!ROOM || ROOM.mode !== "bot" || botBusy) return;
  botBusy = true;
  try {
    let guard = 0;
    while (G && G.winner === null && actorSeat() === G.bot_seat && guard++ < 80) {
      $("#turnbar").innerHTML += ' <span class="thinking">🤔 бот думает…</span>';
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
  mapSel = null;
  try {
    G = await post(`/api/room/${ROOM.id}/move`, { token: ROOM.token, move: m });
    renderAll();
    await botIfNeeded();
  } catch (e) {
    toast("Ход отклонён: " + e.message);
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
    box.innerHTML = "";
    for (const m of resp.menu || []) {
      const btn = document.createElement("button");
      btn.className = "btn bot-opt";
      btn.dataset.id = m.id;
      btn.dataset.desc = m.desc || "";
      btn.innerHTML = m.label; // в label уже есть эмодзи (👑, и т.п.)
      btn.addEventListener("click", () => {
        pickedBot = m.id;
        box.querySelectorAll(".bot-opt").forEach((b) => b.classList.toggle("on", b === btn));
        $("#bot-desc").textContent = m.desc || "";
      });
      box.appendChild(btn);
    }
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
  const picked = $(`#bot-pick .bot-opt.on`);
  let resp;
  try {
    resp = await post("/api/room/new", {
      mode: "bot",
      bot: pickedBot || "mcts",
      side: chosenSide("#side-select"),
      promo: $("#promo").checked,
    });
  } catch (e) {
    toast("Не удалось создать партию: " + e.message);
    return;
  }
  setRoom(resp);
  ROOM.botLabel = picked ? picked.textContent : pickedBot;
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
    side: chosenSide("#pvp-side-select"),
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
