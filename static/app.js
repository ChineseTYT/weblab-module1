(() => {
  const QUEST_ANSWERS = {
    1: "FLAG-DOM-101",
    2: "FLAG-HEADER-200",
    3: "302",
    4: "lab_session",
    5: "FLAG-ROLE-MENTOR",
    6: "429",
  };

  const QUEST_HINTS = {
    1: "Кликни правой кнопкой по голубому пунктирному блоку -> «Просмотреть код». Внутри тега <div id=\"secretDomBox\"> написан атрибут data-secret-flag=\"...\".",
    2: "Нажми кнопку «Выполнить секретный запрос», в DevTools -> Network кликни на строчку header-clue, справа открой вкладку Headers -> Response Headers и найди X-DevTools-Flag.",
    3: "В Network обязательно поставь галочку Keep log (Preserve log), затем нажми «Запустить редирект страницы (302)». Вверху списка увидишь запрос 302-page и его статус 302.",
    4: "Войди во вкладке 3 под student/1234. Открой F12 -> Application -> Cookies -> http://127.0.0.1:8080. У одной из двух кук стоит галочка в столбце HttpOnly.",
    5: "Войди во вкладке 3 под mentor / admin123, нажми «Зайти в панель наставника» и посмотри поле flag в JSON-ответе.",
    6: "Нажми «Отправить запрос к /api/status/429» 4 раза подряд быстрее чем за 10 секунд — на 4-й раз сервер вернёт код 429.",
  };

  const STATUS_EXPLANATIONS = {
    200: ["200 OK — всё успешно, сервер отдал данные.", "ok"],
    201: ["201 Created — новый ресурс успешно создан после POST-запроса.", "ok"],
    302: ["302 Found — сервер перенаправил браузер по новому URL (смотри заголовок Location).", "warn"],
    304: ["304 Not Modified — файл/данные не изменились, браузер использовал копию из кэша (экономия трафика!).", "ok"],
    400: ["400 Bad Request — клиент прислал невалидные или пустые данные.", "warn"],
    401: ["401 Unauthorized — ты не вошёл в аккаунт (нужна авторизация).", "warn"],
    403: ["403 Forbidden — сервер тебя знает (или запрещает ресурс), но прав доступа нет.", "err"],
    404: ["404 Not Found — запрошенного адреса или объекта не существует.", "warn"],
    429: ["429 Too Many Requests — слишком много запросов подряд! Сработал Rate Limit.", "err"],
    500: ["500 Internal Server Error — внутренняя ошибка на сервере.", "err"],
  };

  const STORAGE_QUESTS_KEY = "weblab_m1_quests";
  const STORAGE_JWT_KEY = "weblab_jwt";

  function loadSolvedQuests() {
    try {
      const raw = localStorage.getItem(STORAGE_QUESTS_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  let solvedQuests = loadSolvedQuests();

  function saveSolvedQuests() {
    try {
      localStorage.setItem(STORAGE_QUESTS_KEY, JSON.stringify(solvedQuests));
    } catch {
      // ignore storage failure
    }
  }

  function updateQuestUI() {
    const total = 6;
    const count = Object.keys(solvedQuests).filter((k) => solvedQuests[k]).length;
    const badge = document.getElementById("questProgressBadge");
    const tabBtn = document.getElementById("tabQuestsBtn");
    if (badge) badge.textContent = `Квесты: ${count} / ${total}`;
    if (tabBtn) tabBtn.textContent = `5. Квесты F12 (${count}/${total})`;

    for (let id = 1; id <= total; id++) {
      const card = document.querySelector(`.quest-card[data-quest="${id}"]`);
      const st = document.getElementById(`qStatus${id}`);
      const isDone = Boolean(solvedQuests[id]);
      if (card) card.classList.toggle("solved", isDone);
      if (st) {
        st.textContent = isDone ? "Пройден ✓" : "Не пройден";
        st.classList.toggle("done", isDone);
      }
    }
  }

  function markQuestSolved(id, message) {
    solvedQuests[id] = true;
    saveSolvedQuests();
    updateQuestUI();
    const fb = document.getElementById(`qFeedback${id}`);
    if (fb && message) {
      fb.textContent = message;
      fb.className = "q-feedback ok";
    }
  }

  function switchTab(tabName) {
    document.querySelectorAll(".tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === tabName);
    });
    document.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", p.id === `tab-${tabName}`);
    });
  }

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  function setInspector(method, url, status, statusText, headersObj, bodyData, hintText) {
    const pill = document.getElementById("inspectorStatus");
    const meta = document.getElementById("inspectorMeta");
    const hdrEl = document.getElementById("inspectorHeaders");
    const bodyEl = document.getElementById("inspectorBody");
    const hintEl = document.getElementById("devtoolsHintText");

    pill.textContent = `${status} ${statusText}`;
    pill.className = "status-pill";
    if (status >= 200 && status < 300) pill.classList.add("status-2xx");
    else if (status >= 300 && status < 400) pill.classList.add("status-3xx");
    else if (status >= 400 && status < 500) pill.classList.add("status-4xx");
    else if (status >= 500) pill.classList.add("status-5xx");
    else pill.classList.add("status-idle");

    meta.textContent = `${method} ${url}`;
    const hdrLines = Object.entries(headersObj).map(([k, v]) => `${k}: ${v}`);
    hdrEl.textContent = hdrLines.length ? hdrLines.join("\n") : "(нет заголовков)";

    if (typeof bodyData === "string") {
      bodyEl.textContent = bodyData || "(пустое тело ответа — например, как при 304 Not Modified)";
    } else {
      bodyEl.textContent = JSON.stringify(bodyData, null, 2);
    }

    if (hintText) {
      hintEl.textContent = hintText;
    }
  }

  async function apiRequest(method, url, { body = null, headers = {}, hint = "" } = {}) {
    const fetchOpts = {
      method,
      headers: { ...headers },
      credentials: "same-origin",
    };
    if (body !== null) {
      fetchOpts.headers["Content-Type"] = "application/json";
      fetchOpts.body = JSON.stringify(body);
    }

    const res = await fetch(url, fetchOpts);
    const respHeaders = {};
    res.headers.forEach((v, k) => {
      respHeaders[k] = v;
    });

    const rawText = await res.text();
    let parsed = rawText;
    try {
      if (rawText.trim()) parsed = JSON.parse(rawText);
    } catch {
      parsed = rawText;
    }

    setInspector(method, url, res.status, res.statusText || "", respHeaders, parsed, hint);

    if (res.status === 429 && url.includes("/api/status/429")) {
      const inp6 = document.getElementById("qInput6");
      if (inp6 && !inp6.value) inp6.value = "429";
      markQuestSolved(6, "Отлично! Ты поймал настоящий ответ 429 Too Many Requests от сервера.");
    }

    return { status: res.status, headers: respHeaders, data: parsed, rawText };
  }

  // ------------------------------------------------------------------
  // Вкладка 1: GET / POST / PUT / DELETE
  // ------------------------------------------------------------------
  async function runGetSearch() {
    const q = document.getElementById("getSearchQ").value.trim();
    const cat = document.getElementById("getSearchCat").value;
    const tag = document.getElementById("getStudentTag").value.trim();
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (cat) params.set("category", cat);
    const url = `/api/methods/search?${params.toString()}`;
    const headers = tag ? { "X-Student-Tag": tag } : {};

    const res = await apiRequest("GET", url, {
      headers,
      hint: "Открой F12 -> Network -> кликни на search?..., посмотри Query String Parameters и Request Headers -> X-Student-Tag.",
    });

    const grid = document.getElementById("getResults");
    const items = res.data && res.data.items ? res.data.items : [];
    if (!items.length) {
      grid.innerHTML = '<div class="muted">Ничего не найдено по этому фильтру.</div>';
      return;
    }
    grid.innerHTML = items
      .map(
        (it) => `
      <div class="topic-item">
        <div class="topic-cat">${escapeHtml(it.category)}</div>
        <h4>${escapeHtml(it.title)}</h4>
        <p>${escapeHtml(it.desc)}</p>
      </div>`
      )
      .join("");
  }

  async function loadNotes(silent = false) {
    const res = await fetch("/api/methods/notes", { credentials: "same-origin" });
    const data = await res.json();
    if (!silent) {
      const h = {};
      res.headers.forEach((v, k) => (h[k] = v));
      setInspector(
        "GET",
        "/api/methods/notes",
        res.status,
        res.statusText || "OK",
        h,
        data,
        "В Network видно запрос notes со статусом 200 и массивом заметок в Preview/Response."
      );
    }
    renderNotes(data.notes || []);
  }

  function renderNotes(notes) {
    const list = document.getElementById("notesList");
    if (!notes.length) {
      list.innerHTML = '<div class="muted">Список заметок пуст. Создай новую заметку через POST!</div>';
      return;
    }
    list.innerHTML = "";
    notes.forEach((n) => {
      const row = document.createElement("div");
      row.className = "note-item";

      const info = document.createElement("div");
      info.className = "note-body";
      const st = document.createElement("strong");
      st.textContent = `#${n.id} — ${n.title}`;
      const sp = document.createElement("span");
      sp.textContent = n.text || "(без описания)";
      info.appendChild(st);
      info.appendChild(sp);

      const actions = document.createElement("div");
      actions.className = "btn-row";
      actions.style.marginBottom = "0";

      const btnPut = document.createElement("button");
      btnPut.type = "button";
      btnPut.className = "btn btn-amber btn-sm";
      btnPut.textContent = "Изменить (PUT)";
      btnPut.addEventListener("click", async () => {
        const newTitle = prompt("Новый заголовок заметки:", n.title);
        if (newTitle === null) return;
        const newText = prompt("Новый текст заметки:", n.text || "");
        if (newText === null) return;
        await apiRequest("PUT", `/api/methods/notes/${n.id}`, {
          body: { title: newTitle, text: newText },
          hint: `Открой F12 -> Network -> найди запрос ${n.id} с методом PUT и посмотри вкладку Payload.`,
        });
        await loadNotes(true);
      });

      const btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "btn btn-danger btn-sm";
      btnDel.textContent = "Удалить (DELETE)";
      btnDel.addEventListener("click", async () => {
        await apiRequest("DELETE", `/api/methods/notes/${n.id}`, {
          hint: `В Network появился запрос ${n.id} с методом DELETE и статусом 200 OK.`,
        });
        await loadNotes(true);
      });

      actions.appendChild(btnPut);
      actions.appendChild(btnDel);
      row.appendChild(info);
      row.appendChild(actions);
      list.appendChild(row);
    });
  }

  document.getElementById("btnRunGet").addEventListener("click", runGetSearch);
  document.getElementById("btnReloadNotes").addEventListener("click", () => loadNotes(false));
  document.getElementById("btnCreateNote").addEventListener("click", async () => {
    const title = document.getElementById("noteTitle").value.trim();
    const text = document.getElementById("noteText").value.trim();
    const res = await apiRequest("POST", "/api/methods/notes", {
      body: { title, text },
      hint: "Открой F12 -> Network -> запрос notes (метод POST). Посмотри Payload (отправленный JSON) и заголовок X-Created-By в ответе.",
    });
    if (res.status === 201) {
      document.getElementById("noteTitle").value = "";
      document.getElementById("noteText").value = "";
      await loadNotes(true);
    }
  });

  // ------------------------------------------------------------------
  // Вкладка 2: Полигон статус-кодов
  // ------------------------------------------------------------------
  function showStatusExplain(code, customMsg = null) {
    const box = document.getElementById("statusExplainCard");
    const entry = STATUS_EXPLANATIONS[code];
    const text = customMsg || (entry ? entry[0] : `Получен статус ${code}`);
    const cls = entry ? entry[1] : "warn";
    box.textContent = text;
    box.className = `explain-card ${cls}`;
  }

  async function triggerStatus(method, url, hint) {
    const res = await apiRequest(method, url, { hint });
    const custom = res.data && res.data.meaning ? `${res.status}: ${res.data.meaning}` : null;
    showStatusExplain(res.status, custom);
    return res;
  }

  document.getElementById("btnSt200").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/200", "В Network видишь зелёный статус 200.")
  );
  document.getElementById("btnSt201").addEventListener("click", () =>
    triggerStatus("POST", "/api/status/201", "POST-запрос вернул статус 201 Created.")
  );
  document.getElementById("btnSt302").addEventListener("click", async () => {
    const res = await triggerStatus(
      "GET",
      "/api/status/302",
      "Открой F12 -> Network: браузер сам перешёл с 302 на redirect-target (видны оба запроса подряд!)."
    );
    showStatusExplain(302, `Браузер получил 302 от /api/status/302 и автоматически перешёл на /api/status/redirect-target (финальный статус ${res.status}). Смотри цепочку в F12 -> Network!`);
  });
  document.getElementById("btnSt302Page").addEventListener("click", () => {
    window.location.href = "/api/status/302-page";
  });
  document.getElementById("btnSt304").addEventListener("click", async () => {
    const res = await apiRequest("GET", "/api/status/304", {
      hint: "Если Disable cache выключен, на 2-м нажатии в Network появится серый статус 304 Not Modified и ETag!",
    });
    if (res.status === 304) {
      showStatusExplain(304, "304 Not Modified — сервер сравнил ETag и подтвердил: данные не менялись, браузер взял копию из кэша!");
    } else {
      showStatusExplain(200, "Первый ответ вернул 200 OK и выдал заголовок ETag. Нажми «304 (Кэш ETag)» ещё раз (не включая Disable cache), чтобы получить 304!");
    }
  });
  document.getElementById("btnSt400").addEventListener("click", () =>
    triggerStatus("POST", "/api/status/400", "400 Bad Request в Network подсвечивается как ошибка клиента.")
  );
  document.getElementById("btnSt401").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/401", "При 401 сервер часто добавляет заголовок WWW-Authenticate.")
  );
  document.getElementById("btnSt403").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/403", "403 Forbidden означает запрет доступа из-за нехватки прав.")
  );
  document.getElementById("btnSt404").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/404", "404 Not Found — запрошенный адрес отсутствует на сервере.")
  );
  document.getElementById("btnSt429").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/429", "Смотри заголовки X-RateLimit-Remaining и Retry-After при появлении 429!")
  );
  document.getElementById("btnReset429").addEventListener("click", () =>
    triggerStatus("POST", "/api/status/429/reset", "Счётчик ограничений сброшен.")
  );
  document.getElementById("btnSt500").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/500", "500 Internal Server Error — в продакшене тут не должно быть подробного Stack Trace!")
  );

  // ------------------------------------------------------------------
  // Вкладка 3: Cookies, Сессии и JWT
  // ------------------------------------------------------------------
  function b64UrlDecodeUtf8(str) {
    const pad = "=".repeat((4 - (str.length % 4)) % 4);
    const b64 = (str + pad).replace(/-/g, "+").replace(/_/g, "/");
    const bin = atob(b64);
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }

  function b64UrlEncodeUtf8(str) {
    const bytes = new TextEncoder().encode(str);
    let bin = "";
    bytes.forEach((b) => {
      bin += String.fromCharCode(b);
    });
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  function renderJwtBreakdown(token) {
    const hEl = document.getElementById("jwtHeaderOut");
    const pEl = document.getElementById("jwtPayloadOut");
    const sEl = document.getElementById("jwtSigOut");
    const parts = (token || "").trim().split(".");
    if (parts.length !== 3) {
      hEl.textContent = "{}";
      pEl.textContent = "{}";
      sEl.textContent = token ? "(ожидается 3 части через точку)" : "—";
      return;
    }
    try {
      hEl.textContent = JSON.stringify(JSON.parse(b64UrlDecodeUtf8(parts[0])), null, 2);
    } catch {
      hEl.textContent = "(ошибка декодирования Header)";
    }
    try {
      pEl.textContent = JSON.stringify(JSON.parse(b64UrlDecodeUtf8(parts[1])), null, 2);
    } catch {
      pEl.textContent = "(ошибка декодирования Payload)";
    }
    sEl.textContent = parts[2];
  }

  function setAuthBox(text, cls) {
    const box = document.getElementById("authStateBox");
    box.textContent = text;
    box.className = `explain-card ${cls}`;
  }

  document.getElementById("btnFillStudent").addEventListener("click", () => {
    document.getElementById("loginUsername").value = "student";
    document.getElementById("loginPassword").value = "1234";
  });
  document.getElementById("btnFillMentor").addEventListener("click", () => {
    document.getElementById("loginUsername").value = "mentor";
    document.getElementById("loginPassword").value = "admin123";
  });
  document.getElementById("btnFillWrong").addEventListener("click", () => {
    document.getElementById("loginUsername").value = "student";
    document.getElementById("loginPassword").value = "wrongpass";
  });

  document.getElementById("btnLogin").addEventListener("click", async () => {
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    const res = await apiRequest("POST", "/api/auth/login", {
      body: { username, password },
      hint: "Открой F12 -> Application -> Cookies! Там появятся и public_user, и lab_session (с галочкой HttpOnly). А в Local Storage появится weblab_jwt.",
    });

    if (res.status === 200 && res.data && res.data.jwt) {
      localStorage.setItem(STORAGE_JWT_KEY, res.data.jwt);
      document.getElementById("jwtRawInput").value = res.data.jwt;
      renderJwtBreakdown(res.data.jwt);
      setAuthBox(`Вход выполнен: ${res.data.display} (роль: ${res.data.role}). Cookies и JWT установлены!`, "ok");
    } else {
      setAuthBox(`Ошибка входа (${res.status}): ${(res.data && res.data.error) || "Неверные данные"}`, "err");
    }
  });

  document.getElementById("btnCheckMe").addEventListener("click", async () => {
    const res = await apiRequest("GET", "/api/auth/me", {
      hint: "В DevTools -> Network -> me -> Headers -> Request Headers посмотри строчку Cookie: браузер сам отправил lab_session!",
    });
    if (res.status === 200) {
      setAuthBox(`Активная сессия: ${res.data.display}, роль: ${res.data.role}.`, "ok");
    } else {
      setAuthBox("Ты сейчас не авторизован (сервер вернул 401 Unauthorized).", "warn");
    }
  });

  document.getElementById("btnAdminPanel").addEventListener("click", async () => {
    const res = await apiRequest("GET", "/api/auth/admin-panel", {
      hint: "Под student сервер возвращает 403 Forbidden, а под mentor — 200 OK с флагом!",
    });
    if (res.status === 200) {
      setAuthBox(`Доступ к панели наставника РАЗРЕШЁН! Флаг: ${res.data.flag}`, "ok");
    } else if (res.status === 403) {
      setAuthBox(`403 Forbidden: ты вошёл как ${res.data.current_role}, нужна роль mentor.`, "warn");
    } else {
      setAuthBox("401 Unauthorized: сначала войди в аккаунт.", "err");
    }
  });

  document.getElementById("btnReadJsCookies").addEventListener("click", () => {
    const raw = document.cookie;
    const out = document.getElementById("jsCookieOutput");
    if (!raw) {
      out.textContent = "(пусто) — ни одной обычной cookie не найдено.";
    } else {
      out.textContent = `${raw}\n\nОбрати внимание: cookie lab_session СПЕЦИАЛЬНО здесь не видна, потому что у неё стоит флаг HttpOnly!`;
    }
  });

  document.getElementById("btnLogout").addEventListener("click", async () => {
    await apiRequest("POST", "/api/auth/logout", {
      hint: "Сервер прислал Set-Cookie с Max-Age=0, удалив обе cookies из браузера.",
    });
    localStorage.removeItem(STORAGE_JWT_KEY);
    document.getElementById("jwtRawInput").value = "";
    renderJwtBreakdown("");
    document.getElementById("jsCookieOutput").textContent = "(вышли из аккаунта — нажми «Прочитать document.cookie»)";
    setAuthBox("Выход выполнен, серверная сессия удалена.", "warn");
  });

  document.getElementById("jwtRawInput").addEventListener("input", (e) => {
    renderJwtBreakdown(e.target.value);
  });

  document.getElementById("btnTamperJwt").addEventListener("click", () => {
    const inp = document.getElementById("jwtRawInput");
    const parts = inp.value.trim().split(".");
    if (parts.length !== 3) {
      setAuthBox("Сначала войди в аккаунт, чтобы получить рабочий JWT для эксперимента.", "warn");
      return;
    }
    try {
      const payload = JSON.parse(b64UrlDecodeUtf8(parts[1]));
      payload.role = "mentor";
      payload.tampered = true;
      const newPayloadB64 = b64UrlEncodeUtf8(JSON.stringify(payload));
      const forged = `${parts[0]}.${newPayloadB64}.${parts[2]}`;
      inp.value = forged;
      localStorage.setItem(STORAGE_JWT_KEY, forged);
      renderJwtBreakdown(forged);
      setAuthBox("Роль в Payload изменена на mentor прямо в браузере (подпись старая). Теперь нажми «Отправить JWT на проверку серверу»!", "warn");
    } catch {
      setAuthBox("Не удалось изменить Payload — проверь формат токена.", "err");
    }
  });

  document.getElementById("btnVerifyJwt").addEventListener("click", async () => {
    const token = document.getElementById("jwtRawInput").value.trim();
    const res = await apiRequest("POST", "/api/auth/verify-jwt", {
      body: { token },
      hint: "Смотри статус ответа: при подмене Payload без секретного ключа сервера вернётся 403 Forbidden!",
    });
    if (res.status === 200) {
      setAuthBox("Сервер проверил подпись JWT: токен подлинный (200 OK).", "ok");
    } else {
      setAuthBox(`Сервер ОТКЛОНИЛ токен (${res.status}): ${(res.data && res.data.message) || "Ошибка подписи"}`, "err");
    }
  });

  // ------------------------------------------------------------------
  // Вкладка 4: Клиент vs Сервер
  // ------------------------------------------------------------------
  document.getElementById("btnTamperPrice").addEventListener("click", () => {
    document.getElementById("csPriceInput").value = "1";
  });

  document.getElementById("btnBuyDemo").addEventListener("click", async () => {
    const modeEl = document.querySelector('input[name="csMode"]:checked');
    const mode = modeEl ? modeEl.value : "safe";
    const price = Number(document.getElementById("csPriceInput").value);
    const qty = Number(document.getElementById("csQtyInput").value);
    const res = await apiRequest("POST", "/api/quests/buy-demo", {
      body: { mode, item: "course", price, qty },
      hint: "Посмотри в Network -> buy-demo -> Payload: браузер честно отправил то, что ввёл пользователь, а дальше всё решает код сервера.",
    });

    const box = document.getElementById("csResultBox");
    if (res.status >= 400) {
      box.textContent = `Ошибка ${res.status}: ${(res.data && res.data.error) || "Отклонено сервером"}`;
      box.className = "explain-card err";
    } else if (res.data && res.data.vulnerable && res.data.tampering_succeeded) {
      box.textContent = `УЯЗВИМОСТЬ СРАБОТАЛА! Итого к оплате: ${res.data.final_total_rub} руб. (вместо ${res.data.real_server_price * res.data.qty} руб.). ${res.data.explanation}`;
      box.className = "explain-card err";
    } else {
      box.textContent = `Итого к оплате: ${res.data.final_total_rub} руб. ${res.data.explanation}`;
      box.className = res.data && res.data.tamper_detected ? "explain-card warn" : "explain-card ok";
    }
  });

  // ------------------------------------------------------------------
  // Вкладка 5: Квесты
  // ------------------------------------------------------------------
  document.getElementById("btnQuestHeaderClue").addEventListener("click", () =>
    apiRequest("GET", "/api/quests/header-clue", {
      hint: "В DevTools -> Network кликни на header-clue -> вкладка Headers -> Response Headers -> найди X-DevTools-Flag!",
    })
  );

  document.getElementById("btnQuest302Page").addEventListener("click", () => {
    window.location.href = "/api/status/302-page";
  });

  document.getElementById("btnQuest429Quick").addEventListener("click", () =>
    triggerStatus("GET", "/api/status/429", "Нажми ещё быстрее, пока не вернётся 429 Too Many Requests!")
  );

  document.getElementById("btnQuest429Reset").addEventListener("click", () =>
    triggerStatus("POST", "/api/status/429/reset", "Счётчик Rate Limit сброшен.")
  );

  document.querySelectorAll("[data-check-quest]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.checkQuest);
      const inp = document.getElementById(`qInput${id}`);
      const fb = document.getElementById(`qFeedback${id}`);
      const val = (inp.value || "").trim();
      if (!val) {
        fb.textContent = "Сначала введи найденное значение.";
        fb.className = "q-feedback err";
        return;
      }
      if (val.toLowerCase() === QUEST_ANSWERS[id].toLowerCase()) {
        markQuestSolved(id, `Верно! Квест №${id} засчитан.`);
      } else {
        fb.textContent = "Пока неверно. Проверь значение в DevTools или нажми «Подсказка».";
        fb.className = "q-feedback err";
      }
    });
  });

  document.querySelectorAll("[data-hint-quest]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = Number(btn.dataset.hintQuest);
      const fb = document.getElementById(`qFeedback${id}`);
      fb.textContent = `Подсказка: ${QUEST_HINTS[id]}`;
      fb.className = "q-feedback hint";
    });
  });

  document.getElementById("btnResetQuests").addEventListener("click", () => {
    solvedQuests = {};
    saveSolvedQuests();
    updateQuestUI();
    for (let id = 1; id <= 6; id++) {
      const fb = document.getElementById(`qFeedback${id}`);
      const inp = document.getElementById(`qInput${id}`);
      if (fb) {
        fb.textContent = "";
        fb.className = "q-feedback";
      }
      if (inp) inp.value = "";
    }
  });

  document.getElementById("btnCloseRedirectBanner").addEventListener("click", () => {
    document.getElementById("redirectBanner").classList.add("hidden");
  });

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Инициализация при открытии страницы
  const savedJwt = localStorage.getItem(STORAGE_JWT_KEY) || "";
  if (savedJwt) {
    document.getElementById("jwtRawInput").value = savedJwt;
    renderJwtBreakdown(savedJwt);
  }

  if (window.location.search.includes("redirected=1")) {
    document.getElementById("redirectBanner").classList.remove("hidden");
    const inp3 = document.getElementById("qInput3");
    if (inp3 && !inp3.value) inp3.value = "302";
    markQuestSolved(3, "Верно! Страница прошла через редирект 302 Found.");
    if (window.location.hash === "#statuses") {
      switchTab("statuses");
      showStatusExplain(302, "Ты перешёл по 302 редиректу! Открой F12 -> Network и проверь верхнюю строчку 302-page (если был включён Keep log).");
    }
  }

  updateQuestUI();
  runGetSearch();
  loadNotes(true);
})();
