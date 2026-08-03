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
      text: "<b>Добро пожаловать в Средиземье!</b> Это обучение: сыграем начало " +
        "настоящей партии, я подскажу каждый шаг. Ты играешь за <b class='f'>Братство " +
        "Кольца</b> против Саурона.",
    },
    {
      type: "info",
      hl: [".mid-row .board", "#map"],
      text: "Победить можно тремя способами. <b>Первый — покорение:</b> занять все " +
        "7 регионов Средиземья (юнитом или крепостью). Счёт присутствия — плашки " +
        "1/7 в углах карты.",
    },
    {
      type: "info",
      hl: ["#race-vps", "#race-row"],
      text: "<b>Второй — расы:</b> собрать символы 6 разных рас на зелёных картах " +
        "(орёл хоббитов тоже считается). Счётчик N/6 — над рядом жетонов.",
    },
    {
      type: "info",
      hl: [".quest"],
      text: "<b>Третий — Кольцо:</b> довести Фродо и Сэма до Роковой горы (или, за " +
        "Саурона, догнать их назгулом) на этом треке.",
    },
    {
      type: "info",
      hl: ["#tableau"],
      text: "Карты эпохи разложены пирамидой. Брать можно только <b>открытые и не " +
        "накрытые</b> (они подсвечены зелёной рамкой). Закрытые перевернутся, когда " +
        "освободятся.",
    },
    {
      type: "bot",
      text: "Саурон ходит первым. Нажми — посмотрим, что он возьмёт.",
      btn: "⚔️ Ход Саурона",
    },
    {
      type: "move",
      match: { type: "play", slot: 14 },
      hl: ['#tableau .card[data-slot="14"]'],
      text: "Твой ход! Возьми подсвеченную <b>серую карту</b> «Отвага». Серые карты " +
        "дают <b>навыки</b> — это постоянная скидка: карта с таким значком в цене " +
        "станет для тебя дешевле. Эта — бесплатная: жми и выбери «Сыграть».",
    },
    { type: "bot", text: "Ход Саурона.", btn: "⚔️ Ход Саурона" },
    {
      type: "move",
      match: { type: "play", slot: 19 },
      hl: ['#tableau .card[data-slot="19"]'],
      text: "Теперь <b>жёлтая карта</b> «Золото +2» — возьми её. Монеты нужны, когда " +
        "навыков не хватает: недостающий значок цены можно доплатить монетой " +
        "(1 значок = 1🪙). И ориентиры строятся тоже за монеты.",
    },
    { type: "bot", text: "Ход Саурона.", btn: "⚔️ Ход Саурона" },
    {
      type: "move",
      match: { type: "play", slot: 9 },
      hl: ['#tableau .card[data-slot="9"]'],
      text: "<b>Красная карта</b> «Война» — возьми. Красные выставляют юнитов в один " +
        "из регионов, указанных на карте: так захватывают Средиземье.",
    },
    {
      type: "move",
      match: { type: "place", region: "rhovanion" },
      hl: ['.map-zone[data-region="rhovanion"]'],
      text: "Теперь выбери регион: тапни <b>Рованион</b> на карте — юнит высадится " +
        "туда. Если в регионе встретятся юниты обеих сторон, они разменяются 1:1.",
    },
    {
      type: "bot",
      text: "Смотри: Саурон сейчас <b>продаст</b> карту — любую карту можно не " +
        "играть, а сбросить за монеты (в 1-й эпохе +1🪙, дальше дороже).",
      btn: "⚔️ Ход Саурона",
    },
    {
      type: "move",
      match: { type: "play", slot: 13 },
      hl: ['#tableau .card[data-slot="13"]'],
      text: "<b>Зелёная карта</b> «Эльфы». У тебя нет навыка из её цены — видишь " +
        "ценник 1🪙? Это та самая доплата монетой. Бери: расы приближают победу, " +
        "а 2 одинаковых или 3 разных символа дадут <b>жетон союза</b> с бонусом.",
    },
    { type: "bot", text: "Ход Саурона.", btn: "⚔️ Ход Саурона" },
    {
      type: "move",
      match: { type: "play", slot: 12 },
      hl: ['#tableau .card[data-slot="12"]'],
      text: "И <b>синяя карта</b> «Кольцо» — возьми: Фродо и Сэм сделают шаг к " +
        "Роковой горе. На треке попадаются клетки с бонусами — монеты, юниты и " +
        "даже дополнительный ход.",
    },
    { type: "bot", text: "Ход Саурона.", btn: "⚔️ Ход Саурона" },
    {
      type: "info",
      hl: ["#landmark-row"],
      text: "Осталось два элемента. <b>Ориентиры</b> (тайлы сверху): покупаются за " +
        "монеты, ставят крепость в свой регион и дают мощные бонусы. Крепость — " +
        "постоянное присутствие, юниты через неё не размениваются.",
    },
    {
      type: "info",
      hl: ["#race-row"],
      text: "И <b>жетоны союзов</b>: собрал 2 одинаковых символа расы — берёшь " +
        "верхний жетон её стопки; 3 разных — жетон любой из этих рас (раз за " +
        "партию). Эффекты — от лишних ходов до юнитов и монет.",
    },
    {
      type: "end",
      text: "<b>Ты готов!</b> Доиграй партию сам — соперник в обучении не самый " +
        "грозный. Помни про три пути к победе и следи, куда клонится Саурон. Удачи!",
      btn: "⚔️ В бой!",
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
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
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
      b.textContent = s.btn || "Далее →";
      b.addEventListener("click", () => {
        if (s.type === "end") stop();
        else advance();
      });
      btns.appendChild(b);
    } else if (s.type === "bot") {
      const b = document.createElement("button");
      b.className = "btn small";
      b.textContent = s.btn || "⚔️ Ход Саурона";
      b.addEventListener("click", async () => {
        b.disabled = true;
        await window.tutBotStep(); // один ход бота (app.js)
        advance();
      });
      btns.appendChild(b);
    }
    // move-шаги — без кнопок: ученик делает подсвеченный ход
    applyHl();
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
    if (active()) applyHl();
  }

  window.TUT = { active, start, stop, allowMove, allowBot, onMoved, onRender };
})();
