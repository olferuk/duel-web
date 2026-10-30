/* Интерактивный туториал: guided play по фиксированному сиду (server: seed 10,
   соперник GreedyBot seed 7 — детерминирован, пока ученик идёт по рельсам).

   Движок шагов: info (текст + «Далее»), bot (кнопка «Ход Саурона» → один
   bot_step), move (ученик обязан сделать подсвеченный ход; прочие блокируются).
   app.js дергает window.TUT: active()/allowMove()/allowBot()/onRender()/start().

   Сценарий выверен под сид: любое изменение сида/бота — перепрогнать
   scratchpad/find_tut_seed.py и переписать слоты. */

(function () {
  "use strict";

  // — сценарий (слоты из прогона сида 10) —
  const STEPS = [
    {
      type: "info",
      text: "<b>Welcome to Middle-earth!</b> This is the tutorial: we'll play the start " +
        "of a real game and I'll guide every step. You play the <b class='f'>Fellowship " +
        "of the Ring</b> against Sauron.",
    },
    {
      type: "info",
      hl: [".mid-row .board", "#map"],
      text: "There are three ways to win. <b>First, conquest:</b> hold all " +
        "7 regions of Middle-earth with a unit or fortress. Your presence score is on the " +
        "1/7 plates in the map corners.",
    },
    {
      type: "info",
      hl: ["#race-vps", "#race-row"],
      text: "<b>Second, races:</b> collect symbols of 6 different races on green cards " +
        "(the Hobbits' eagle counts too). The N/6 counter sits above the token row.",
    },
    {
      type: "info",
      hl: [".quest"],
      text: "<b>Third, the Ring:</b> take Frodo and Sam to Mount Doom along this " +
        "track. Sauron wins if the Nazgûl catches them.",
    },
    {
      type: "info",
      hl: ["#tableau"],
      text: "The chapter's cards form a pyramid. You can only take cards that are <b>face up and " +
        "uncovered</b> (they have a green frame). Face-down cards flip when " +
        "they are freed.",
    },
    {
      type: "bot",
      text: "Sauron goes first. Press the button to see what he takes.",
      btn: "⚔️ Sauron's turn",
    },
    {
      type: "move",
      match: { type: "play", slot: 14 },
      hl: ['#tableau .card[data-slot="14"]'],
      text: "Your turn! Take the highlighted <b>grey card</b> “Courage”. Grey cards " +
        "give <b>skills</b>, a permanent discount: any card with this icon in its cost " +
        "gets cheaper for you. This one is free: click it and choose “Play”.",
    },
    { type: "bot", text: "Sauron's turn.", btn: "⚔️ Sauron's turn" },
    {
      type: "move",
      match: { type: "play", slot: 19 },
      hl: ['#tableau .card[data-slot="19"]'],
      text: "Now take the <b>yellow card</b> “Gold +2”. You need coins when " +
        "you lack skills: pay for a missing cost icon with a coin " +
        "(1 icon = 1🪙). Landmarks are built with coins too.",
    },
    { type: "bot", text: "Sauron's turn.", btn: "⚔️ Sauron's turn" },
    {
      type: "move",
      match: { type: "play", slot: 9 },
      hl: ['#tableau .card[data-slot="9"]'],
      text: "Take the <b>red card</b> “War”. Red cards place units in one " +
        "of the regions shown on the card. That is how you conquer Middle-earth.",
    },
    {
      type: "move",
      match: { type: "place", region: "rhovanion" },
      hl: ['.map-zone[data-region="rhovanion"]'],
      text: "Now choose a region: tap <b>Rhovanion</b> on the map and your unit lands " +
        "there. If both sides meet in a region, their units trade 1:1.",
    },
    {
      type: "bot",
      text: "Watch: Sauron will <b>sell</b> a card. Instead of playing a card you can " +
        "discard it for coins (+1🪙 in Chapter 1, more later).",
      btn: "⚔️ Sauron's turn",
    },
    {
      type: "move",
      match: { type: "play", slot: 13 },
      hl: ['#tableau .card[data-slot="13"]'],
      text: "<b>Green card</b> “Elves”. You lack a skill from its cost, so see the " +
        "1🪙 price tag? That is the coin top-up. Take it: races bring you closer to victory, " +
        "and 2 matching or 3 different symbols earn an <b>alliance token</b> with a bonus.",
    },
    { type: "bot", text: "Sauron's turn.", btn: "⚔️ Sauron's turn" },
    {
      type: "move",
      match: { type: "play", slot: 12 },
      hl: ['#tableau .card[data-slot="12"]'],
      text: "Take the <b>blue card</b> “Ring”: Frodo and Sam step closer to " +
        "Mount Doom. Note that the Nazgûl <b>doesn't fall behind</b>: its strip follows " +
        "them, so the gap can only hold or shrink. " +
        "Track spaces hold bonuses: coins, units and even an extra turn.",
    },
    { type: "bot", text: "Sauron's turn.", btn: "⚔️ Sauron's turn" },
    {
      type: "info",
      hl: ["#landmark-row"],
      text: "Two things left. <b>Landmarks</b> (the tiles on top) cost " +
        "coins, put a fortress in their region and give strong bonuses. A fortress is " +
        "permanent presence: units don't trade against it.",
    },
    {
      type: "info",
      hl: ["#race-row"],
      text: "And <b>alliance tokens</b>: collect 2 matching race symbols and you reveal " +
        "the top <b>two</b> tokens of that stack and keep one. Collect 3 different " +
        "symbols and you reveal the top token of each of the three stacks and keep one " +
        "(once per game). Effects range from extra turns to units and coins.",
    },
    {
      type: "end",
      text: "<b>You're ready!</b> Finish the game yourself. The tutorial opponent isn't the most " +
        "dangerous. Remember the three paths to victory and watch where Sauron is heading. Good luck!",
      btn: "⚔️ To battle!",
    },
  ];

  let idx = -1; // -1 = не активен
  let panel = null;

  function active() {
    return idx >= 0 && idx < STEPS.length;
  }
  function step() {
    return active() ? STEPS[idx] : null;
  }

  function start() {
    idx = 0;
    ensurePanel();
    render();
  }
  function stop() {
    idx = -1;
    clearHl();
    if (panel) {
      panel.remove();
      panel = null;
    }
  }

  function ensurePanel() {
    if (panel) return;
    panel = document.createElement("div");
    panel.id = "tut-panel";
    panel.innerHTML = '<div id="tut-text"></div><div id="tut-btns"></div>';
    document.body.appendChild(panel);
  }

  function clearHl() {
    document.querySelectorAll(".tut-hl").forEach((el) => el.classList.remove("tut-hl"));
  }

  function applyHl() {
    clearHl();
    const s = step();
    if (!s || !s.hl) return;
    for (const sel of s.hl) {
      document.querySelectorAll(sel).forEach((el) => el.classList.add("tut-hl"));
    }
  }

  // панель живёт РЯДОМ с тем, о чём рассказывает: под целью (или над, если снизу
  // не влезает), в координатах документа — скроллится вместе с целью.
  // Шаги без цели (приветствие, финал) — по центру экрана.
  function positionPanel() {
    if (!panel) return;
    const s = step();
    const target = s && s.hl ? document.querySelector(s.hl[0]) : null;
    if (!target) {
      panel.classList.add("tut-center");
      panel.style.left = "";
      panel.style.top = "";
      return;
    }
    panel.classList.remove("tut-center");
    const r = target.getBoundingClientRect();
    const pw = panel.offsetWidth;
    const ph = panel.offsetHeight;
    let left = window.scrollX + r.left + r.width / 2 - pw / 2;
    left = Math.max(6, Math.min(left, window.scrollX + window.innerWidth - pw - 6));
    // предпочитаем место НАД целью: под карточкой раскрывается меню «Сыграть/
    // Продать», и панель снизу перекрывала бы его
    let top;
    if (r.top - ph - 14 >= 6) {
      top = window.scrollY + r.top - ph - 10; // над целью
    } else {
      top = window.scrollY + Math.min(r.bottom + 10, window.innerHeight - ph - 6); // под целью
    }
    panel.style.left = left + "px";
    panel.style.top = top + "px";
  }

  function advance() {
    idx += 1;
    if (idx >= STEPS.length) {
      stop();
      return;
    }
    render();
    const s = step();
    if (s && s.hl && s.hl.length) {
      const el = document.querySelector(s.hl[0]);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        // плавный скролл асинхронный — доводим позицию панели после него
        setTimeout(positionPanel, 380);
      }
    }
  }

  function render() {
    if (!active()) return;
    ensurePanel();
    const s = step();
    panel.querySelector("#tut-text").innerHTML =
      `<span class="tut-n">${idx + 1}/${STEPS.length}</span> ` + s.text;
    const btns = panel.querySelector("#tut-btns");
    btns.innerHTML = "";
    if (s.type === "info" || s.type === "end") {
      const b = document.createElement("button");
      b.className = "btn small";
      b.textContent = s.btn || "Next →";
      b.addEventListener("click", () => {
        if (s.type === "end") stop();
        else advance();
      });
      btns.appendChild(b);
    } else if (s.type === "bot") {
      const b = document.createElement("button");
      b.className = "btn small";
      b.textContent = s.btn || "⚔️ Sauron's turn";
      b.addEventListener("click", async () => {
        b.disabled = true;
        await window.tutBotStep(); // один ход бота (app.js)
        advance();
      });
      btns.appendChild(b);
    }
    // move-шаги — без кнопок: ученик делает подсвеченный ход
    applyHl();
    positionPanel();
  }

  // ход ученика разрешён, только если совпадает с рельсами текущего шага
  function allowMove(m) {
    if (!active()) return true;
    const s = step();
    if (s.type !== "move") return false;
    return Object.entries(s.match).every(([k, v]) => String(m[k]) === String(v));
  }

  // после успешного хода ученика — шаг вперёд
  function onMoved() {
    const s = step();
    if (s && s.type === "move") advance();
  }

  // бот ходит только по кнопке шага "bot" (и свободно после конца туториала)
  function allowBot() {
    return !active();
  }

  // перерисовки уничтожают подсвеченные элементы — восстанавливаем метки
  function onRender() {
    if (!active()) return;
    applyHl();
    positionPanel();
  }

  let _rz;
  window.addEventListener("resize", () => {
    clearTimeout(_rz);
    _rz = setTimeout(() => active() && positionPanel(), 150);
  });

  window.TUT = { active, start, stop, allowMove, allowBot, onMoved, onRender };
})();
