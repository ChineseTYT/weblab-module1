import argparse
import base64
import hashlib
import hmac
import http.cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Демо-пользователи для учебного стенда
USERS = {
    "student": {"password": "1234", "role": "student", "display": "Ученик (student)"},
    "mentor": {"password": "admin123", "role": "mentor", "display": "Наставник (mentor)"},
}

# Серверный каталог товаров (источник правды для Задания «Клиент vs Сервер»)
SERVER_CATALOG = {
    "course": {"title": "Курс: Сайты с ИИ и AppSec", "price": 15000},
}

# База карточек для тренировки GET-поиска
SEARCH_TOPICS = [
    {"id": 1, "category": "http", "title": "Метод GET", "desc": "Запрашивает данные у сервера. Параметры передаются прямо в URL (?q=...)."},
    {"id": 2, "category": "http", "title": "Метод POST", "desc": "Отправляет новые данные в теле (Body) запроса — например, форму или JSON."},
    {"id": 3, "category": "status", "title": "Статус 302 и Keep log", "desc": "Редирект перекидывает браузер на новый URL. Keep log сохраняет старый запрос в списке."},
    {"id": 4, "category": "status", "title": "Статус 304 и кэш", "desc": "Сервер сообщает браузеру: файл не изменился, возьми копию из кэша (ETag)."},
    {"id": 5, "category": "auth", "title": "Cookie с HttpOnly", "desc": "Хранится в браузере и улетает на сервер, но скрыта от JavaScript (document.cookie)."},
    {"id": 6, "category": "auth", "title": "JWT (JSON Web Token)", "desc": "Состоит из Header.Payload.Signature. Payload читается в Base64, но защищён подписью."},
    {"id": 7, "category": "security", "title": "Золотое правило сервера", "desc": "Всегда проверяй цены, права доступа и ввод на сервере — клиенту доверять нельзя."},
]

JWT_SECRET = secrets.token_bytes(32)
STATE_LOCK = threading.Lock()

NOTES = [
    {
        "id": 1,
        "title": "Изучить HTTP-методы",
        "text": "GET читает, POST создаёт (201), PUT обновляет, DELETE удаляет.",
    },
    {
        "id": 2,
        "title": "Проверить флаг HttpOnly",
        "text": "Cookie lab_session видна в Application -> Cookies, но скрыта от document.cookie.",
    },
]
NEXT_NOTE_ID = 3
SESSIONS: dict[str, dict] = {}
RATE_LIMIT_LOG: dict[str, list[float]] = {}
RATE_LIMIT_MAX = 3
RATE_LIMIT_WINDOW = 10.0


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(segment: str) -> bytes:
    pad = "=" * ((4 - len(segment) % 4) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def create_jwt(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h_b64 = b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    p_b64 = b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(JWT_SECRET, signing_input, hashlib.sha256).digest()
    return f"{h_b64}.{p_b64}.{b64url_encode(sig)}"


def verify_jwt(token: str) -> tuple[bool, dict | None, dict | None, str]:
    parts = token.strip().split(".")
    if len(parts) != 3:
        return False, None, None, "Токен должен состоять ровно из 3 частей: Header.Payload.Signature."
    h_b64, p_b64, sig_b64 = parts
    try:
        header = json.loads(b64url_decode(h_b64).decode("utf-8"))
        payload = json.loads(b64url_decode(p_b64).decode("utf-8"))
    except Exception:
        return False, None, None, "Не удалось декодировать Base64/JSON в Header или Payload."

    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    expected_sig = b64url_encode(hmac.new(JWT_SECRET, signing_input, hashlib.sha256).digest())
    if not hmac.compare_digest(sig_b64, expected_sig):
        return (
            False,
            header,
            payload,
            "Подпись (Signature) НЕ совпала! Данные Payload были изменены без секретного ключа сервера.",
        )

    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and time.time() > exp:
        return False, header, payload, "Срок действия токена (exp) истёк."

    return True, header, payload, "Подпись (Signature) действительна: сервер доверяет этому токену."


class WebLabHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:
        ts = time.strftime("%H:%M:%S")
        try:
            msg = format % args
        except Exception:
            msg = " ".join(str(a) for a in args)
        print(f"[{ts}] {self.client_address[0]} - {msg}")

    def send_json(
        self,
        status: int,
        data: dict | list,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_empty(
        self,
        status: int,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(status)
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        if status != 304 and status != 204:
            self.send_header("Content-Length", "0")
        self.end_headers()

    def serve_static(self, rel_path: str, content_type: str) -> None:
        full_path = os.path.normpath(os.path.join(STATIC_DIR, rel_path))
        if not full_path.startswith(os.path.normpath(STATIC_DIR)) or not os.path.isfile(full_path):
            self.send_json(404, {"error": "Статический файл не найден"})
            return
        with open(full_path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def cookie_security_attrs(self) -> str:
        proto = (self.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip().lower()
        return "; Secure" if proto == "https" else ""

    def read_json_body(self) -> tuple[dict | None, str | None]:
        length_hdr = self.headers.get("Content-Length")
        if not length_hdr:
            return {}, None
        try:
            length = int(length_hdr)
        except ValueError:
            return None, "Некорректный заголовок Content-Length"
        if length <= 0:
            return {}, None
        if length > 1024 * 256:
            return None, "Слишком большое тело запроса"
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                return None, "Ожидался JSON-объект {...}"
            return parsed, None
        except Exception:
            return None, "Невалидный JSON в теле запроса"

    def get_session(self) -> tuple[str | None, dict | None]:
        cookie_hdr = self.headers.get("Cookie", "")
        if not cookie_hdr:
            return None, None
        c = http.cookies.SimpleCookie()
        try:
            c.load(cookie_hdr)
        except Exception:
            return None, None
        morsel = c.get("lab_session")
        if not morsel:
            return None, None
        sid = morsel.value
        with STATE_LOCK:
            sess = SESSIONS.get(sid)
            return sid, dict(sess) if sess else None

    # ------------------------------------------------------------------
    # HTTP GET
    # ------------------------------------------------------------------
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        # Статика
        if path == "/" or path == "/index.html":
            self.serve_static("index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self.serve_static("styles.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self.serve_static("app.js", "application/javascript; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_empty(204)
            return

        # Блок 1: Методы
        if path == "/api/methods/search":
            q = (qs.get("q", [""])[0] or "").strip().lower()
            cat = (qs.get("category", ["all"])[0] or "all").strip().lower()
            results = []
            for item in SEARCH_TOPICS:
                if cat != "all" and item["category"] != cat:
                    continue
                if q and (q not in item["title"].lower() and q not in item["desc"].lower()):
                    continue
                results.append(item)
            self.send_json(
                200,
                {
                    "method": "GET",
                    "count": len(results),
                    "items": results,
                    "received_query": {"q": q, "category": cat},
                    "received_headers": {
                        "User-Agent": self.headers.get("User-Agent", ""),
                        "X-Student-Tag": self.headers.get("X-Student-Tag", "(не передан)"),
                        "Cookie_present": bool(self.headers.get("Cookie")),
                    },
                    "explanation": "GET передаёт параметры поиска прямо в URL после знака вопроса ? и не имеет тела запроса.",
                },
            )
            return

        if path == "/api/methods/notes":
            with STATE_LOCK:
                items = list(NOTES)
            self.send_json(200, {"count": len(items), "notes": items})
            return

        # Блок 2: Полигон статус-кодов
        if path == "/api/status/200":
            self.send_json(
                200,
                {
                    "status": 200,
                    "meaning": "OK — Запрос успешно обработан сервером",
                    "tip": "Самый частый код при загрузке страниц, картинок и успешном чтении API.",
                },
            )
            return

        if path == "/api/status/302":
            self.send_empty(
                302,
                extra_headers=[
                    ("Location", "/api/status/redirect-target"),
                    ("Cache-Control", "no-store"),
                ],
            )
            return

        if path == "/api/status/redirect-target":
            self.send_json(
                200,
                {
                    "status": 200,
                    "redirected_from": "/api/status/302",
                    "meaning": "Браузер получил 302 Found от /api/status/302 и автоматически перешёл сюда (заголовок Location).",
                    "tip": "Открой DevTools -> Network и посмотри: там видно ДВА запроса подряд — сначала 302, затем 200!",
                },
            )
            return

        if path == "/api/status/302-page":
            self.send_empty(
                302,
                extra_headers=[
                    ("Location", "/?redirected=1#statuses"),
                    ("Cache-Control", "no-store"),
                ],
            )
            return

        if path == "/api/status/304":
            etag = '"weblab-etag-v1"'
            inm = self.headers.get("If-None-Match", "")
            if etag in inm or "weblab-etag-v1" in inm:
                self.send_empty(
                    304,
                    extra_headers=[
                        ("ETag", etag),
                        ("Cache-Control", "no-cache"),
                        ("X-Cache-Demo", "Browser used cached version"),
                    ],
                )
            else:
                self.send_response(200)
                body = json.dumps(
                    {
                        "status": 200,
                        "etag": "weblab-etag-v1",
                        "meaning": "Первый запрос отдал данные (200 OK) и выдал заголовок ETag.",
                        "tip": "Нажми кнопку '304 (Кэш ETag)' ещё раз БЕЗ Disable cache: браузер пришлёт If-None-Match и получит 304 Not Modified!",
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
            return

        if path == "/api/status/401":
            self.send_json(
                401,
                {
                    "status": 401,
                    "error": "Unauthorized",
                    "meaning": "Ты НЕ авторизован. Сервер требует вход в аккаунт или валидный токен.",
                },
                extra_headers=[("WWW-Authenticate", 'Bearer realm="WebLab"')],
            )
            return

        if path == "/api/status/403":
            self.send_json(
                403,
                {
                    "status": 403,
                    "error": "Forbidden",
                    "meaning": "Доступ запрещён! Сервер может даже знать, кто ты, но прав на этот ресурс нет (например, у student нет прав mentor).",
                },
            )
            return

        if path == "/api/status/404":
            self.send_json(
                404,
                {
                    "status": 404,
                    "error": "Not Found",
                    "meaning": "Такого URL или объекта на сервере не существует.",
                },
            )
            return

        if path == "/api/status/429":
            client_ip = self.client_address[0]
            now = time.time()
            with STATE_LOCK:
                history = [t for t in RATE_LIMIT_LOG.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW]
                if len(history) >= RATE_LIMIT_MAX:
                    retry_after = max(1, int(RATE_LIMIT_WINDOW - (now - history[0])) + 1)
                    RATE_LIMIT_LOG[client_ip] = history
                    blocked = True
                    remaining = 0
                else:
                    history.append(now)
                    RATE_LIMIT_LOG[client_ip] = history
                    blocked = False
                    remaining = RATE_LIMIT_MAX - len(history)
                    retry_after = 0

            if blocked:
                self.send_json(
                    429,
                    {
                        "status": 429,
                        "error": "Too Many Requests",
                        "meaning": f"Сработал Rate Limiting! Превышен лимит ({RATE_LIMIT_MAX} запроса за {int(RATE_LIMIT_WINDOW)} сек).",
                        "retry_after_seconds": retry_after,
                    },
                    extra_headers=[
                        ("Retry-After", str(retry_after)),
                        ("X-RateLimit-Limit", str(RATE_LIMIT_MAX)),
                        ("X-RateLimit-Remaining", "0"),
                    ],
                )
            else:
                self.send_json(
                    200,
                    {
                        "status": 200,
                        "meaning": f"Запрос разрешён. Осталось попыток в 10-сек окне: {remaining} из {RATE_LIMIT_MAX}.",
                        "tip": "Нажми эту же кнопку быстро ещё несколько раз, чтобы поймать настоящий 429 Too Many Requests!",
                    },
                    extra_headers=[
                        ("X-RateLimit-Limit", str(RATE_LIMIT_MAX)),
                        ("X-RateLimit-Remaining", str(remaining)),
                    ],
                )
            return

        if path == "/api/status/500":
            self.send_json(
                500,
                {
                    "status": 500,
                    "error": "Internal Server Error",
                    "meaning": "Внутренняя ошибка сервера (упал код бэкенда). В продакшене стек вызовов (Stack Trace) скрывается от пользователя!",
                },
            )
            return

        # Блок 3: Cookies / Сессии / Роли
        if path == "/api/auth/me":
            sid, sess = self.get_session()
            if not sess:
                self.send_json(
                    401,
                    {
                        "authenticated": False,
                        "error": "Сессия не найдена. Войди через форму ниже, чтобы сервер установил HttpOnly cookie lab_session.",
                    },
                )
                return
            self.send_json(
                200,
                {
                    "authenticated": True,
                    "username": sess["username"],
                    "role": sess["role"],
                    "display": sess["display"],
                    "session_id_preview": (sid[:8] + "...") if sid else "",
                    "note": "Сервер узнал тебя по cookie lab_session, которую браузер автоматически приложил к запросу.",
                },
            )
            return

        if path == "/api/auth/admin-panel":
            _, sess = self.get_session()
            if not sess:
                self.send_json(
                    401,
                    {
                        "status": 401,
                        "error": "Сначала войди в аккаунт (нет активной серверной сессии).",
                    },
                )
                return
            if sess["role"] != "mentor":
                self.send_json(
                    403,
                    {
                        "status": 403,
                        "error": "Forbidden — недостаточно прав!",
                        "current_role": sess["role"],
                        "required_role": "mentor",
                        "explanation": "Сервер знает, что ты student (не 401), но доступ в панель наставника закрыт (403 Forbidden).",
                    },
                )
                return
            self.send_json(
                200,
                {
                    "status": 200,
                    "access": "granted",
                    "role": sess["role"],
                    "flag": "FLAG-ROLE-MENTOR",
                    "secret_message": "Добро пожаловать в панель наставника! Роль проверена на сервере через сессию.",
                },
            )
            return

        # Блок 4: Квест заголовка
        if path == "/api/quests/header-clue":
            self.send_json(
                200,
                {
                    "message": "Флаг спрятан НЕ здесь в JSON, а в HTTP-заголовке ответа (Response Headers)!",
                    "hint": "Открой DevTools (F12) -> Network -> кликни на header-clue -> вкладка Headers -> раздел Response Headers -> X-DevTools-Flag.",
                },
                extra_headers=[("X-DevTools-Flag", "FLAG-HEADER-200")],
            )
            return

        self.send_json(404, {"error": f"Маршрут GET {path} не найден"})

    # ------------------------------------------------------------------
    # HTTP POST
    # ------------------------------------------------------------------
    def do_POST(self) -> None:
        global NEXT_NOTE_ID
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/methods/notes":
            data, err = self.read_json_body()
            if err or data is None:
                self.send_json(400, {"error": err or "Ошибка JSON"})
                return
            title = str(data.get("title", "")).strip()
            text = str(data.get("text", "")).strip()
            if not title:
                self.send_json(400, {"error": "Поле title не может быть пустым (400 Bad Request)."})
                return
            with STATE_LOCK:
                note = {"id": NEXT_NOTE_ID, "title": title, "text": text}
                NEXT_NOTE_ID += 1
                NOTES.append(note)
            self.send_json(
                201,
                {
                    "status": 201,
                    "created": note,
                    "explanation": "POST передал JSON в теле запроса, а сервер создал объект и ответил статусом 201 Created.",
                },
                extra_headers=[("X-Created-By", "WebLab-Server")],
            )
            return

        if path == "/api/status/201":
            self.send_json(
                201,
                {
                    "status": 201,
                    "meaning": "Created — новый ресурс успешно создан (обычно после POST).",
                },
            )
            return

        if path == "/api/status/400":
            self.send_json(
                400,
                {
                    "status": 400,
                    "error": "Bad Request",
                    "meaning": "Сервер отклонил запрос: неверный формат JSON, пустое поле или некорректные данные.",
                },
            )
            return

        if path == "/api/status/429/reset":
            client_ip = self.client_address[0]
            with STATE_LOCK:
                RATE_LIMIT_LOG.pop(client_ip, None)
            self.send_json(200, {"ok": True, "message": "Счётчик Rate Limit сброшен."})
            return

        if path == "/api/auth/login":
            data, err = self.read_json_body()
            if err or data is None:
                self.send_json(400, {"error": err or "Ошибка JSON"})
                return
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))
            user = USERS.get(username)
            if not user or user["password"] != password:
                self.send_json(
                    401,
                    {
                        "status": 401,
                        "error": "Неверный логин или пароль",
                        "explanation": "Обрати внимание: сервер не подсказывает, что именно неверно (логин или пароль) — это защита от перебора пользователей.",
                    },
                )
                return

            sid = secrets.token_hex(16)
            with STATE_LOCK:
                SESSIONS[sid] = {
                    "username": username,
                    "role": user["role"],
                    "display": user["display"],
                    "created_at": int(time.time()),
                }

            now = int(time.time())
            jwt_token = create_jwt(
                {
                    "sub": username,
                    "role": user["role"],
                    "iat": now,
                    "exp": now + 3600,
                }
            )
            secure_attr = self.cookie_security_attrs()
            self.send_json(
                200,
                {
                    "ok": True,
                    "username": username,
                    "role": user["role"],
                    "display": user["display"],
                    "jwt": jwt_token,
                    "cookies_set": [
                        "public_user (обычная cookie — читается из document.cookie)",
                        "lab_session (HttpOnly cookie — видна в Application -> Cookies, но скрыта от JS)",
                    ],
                },
                extra_headers=[
                    ("Set-Cookie", f"public_user={username}; Path=/; SameSite=Lax{secure_attr}"),
                    ("Set-Cookie", f"lab_session={sid}; Path=/; HttpOnly; SameSite=Lax{secure_attr}"),
                ],
            )
            return

        if path == "/api/auth/verify-jwt":
            data, err = self.read_json_body()
            if err or data is None:
                self.send_json(400, {"error": err or "Ошибка JSON"})
                return
            token = str(data.get("token", ""))
            ok, header, payload, msg = verify_jwt(token)
            status = 200 if ok else 403
            self.send_json(
                status,
                {
                    "valid": ok,
                    "status": status,
                    "message": msg,
                    "decoded_header": header,
                    "decoded_payload": payload,
                },
            )
            return

        if path == "/api/auth/logout":
            sid, _ = self.get_session()
            if sid:
                with STATE_LOCK:
                    SESSIONS.pop(sid, None)
            secure_attr = self.cookie_security_attrs()
            self.send_json(
                200,
                {"ok": True, "message": "Сессия завершена, cookies очищены."},
                extra_headers=[
                    ("Set-Cookie", f"public_user=; Path=/; Max-Age=0; SameSite=Lax{secure_attr}"),
                    ("Set-Cookie", f"lab_session=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax{secure_attr}"),
                ],
            )
            return

        if path == "/api/quests/buy-demo":
            data, err = self.read_json_body()
            if err or data is None:
                self.send_json(400, {"error": err or "Ошибка JSON"})
                return
            mode = str(data.get("mode", "safe"))
            item_id = str(data.get("item", "course"))
            catalog_item = SERVER_CATALOG.get(item_id)
            if not catalog_item:
                self.send_json(404, {"error": "Товар не найден в каталоге сервера"})
                return
            real_price = catalog_item["price"]

            try:
                client_price = int(data.get("price", real_price))
                qty = int(data.get("qty", 1))
            except (TypeError, ValueError):
                self.send_json(400, {"error": "price и qty должны быть целыми числами"})
                return

            if mode == "naive":
                total = client_price * qty
                tampered = (client_price != real_price) or (qty <= 0)
                self.send_json(
                    200,
                    {
                        "mode": "naive",
                        "vulnerable": True,
                        "tampering_succeeded": tampered,
                        "client_sent_price": client_price,
                        "real_server_price": real_price,
                        "qty": qty,
                        "final_total_rub": total,
                        "explanation": (
                            "ОПАСНАЯ ОШИБКА: сервер доверился цене/количеству, присланным из браузера! "
                            "Любой пользователь через F12 или Postman мог купить курс за 1 руб. или отрицательную сумму."
                            if tampered
                            else "Сервер рассчитал сумму по цене из запроса клиента. Попробуй подменить цену на 1 или -500!"
                        ),
                    },
                )
                return

            # Защищённый режим (safe)
            if qty < 1 or qty > 100:
                self.send_json(
                    400,
                    {
                        "mode": "safe",
                        "status": 400,
                        "error": "Количество (qty) должно быть от 1 до 100. Сервер отклонил некорректный ввод.",
                    },
                )
                return

            total = real_price * qty
            tamper_detected = client_price != real_price
            self.send_json(
                200,
                {
                    "mode": "safe",
                    "vulnerable": False,
                    "tamper_detected": tamper_detected,
                    "client_sent_price": client_price,
                    "used_server_price": real_price,
                    "qty": qty,
                    "final_total_rub": total,
                    "explanation": (
                        f"АТАКА ОТБИТА: клиент пытался подсунуть цену {client_price} руб., "
                        f"но сервер проигнорировал её и взял настоящую цену {real_price} руб. из базы данных!"
                        if tamper_detected
                        else f"Сервер взял цену {real_price} руб. из серверного каталога (не из запроса клиента)."
                    ),
                },
            )
            return

        self.send_json(404, {"error": f"Маршрут POST {path} не найден"})

    # ------------------------------------------------------------------
    # HTTP PUT
    # ------------------------------------------------------------------
    def do_PUT(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/methods/notes/"):
            id_str = path.rsplit("/", 1)[-1]
            try:
                note_id = int(id_str)
            except ValueError:
                self.send_json(400, {"error": "Некорректный ID заметки"})
                return
            data, err = self.read_json_body()
            if err or data is None:
                self.send_json(400, {"error": err or "Ошибка JSON"})
                return
            title = str(data.get("title", "")).strip()
            text = str(data.get("text", "")).strip()
            if not title:
                self.send_json(400, {"error": "Поле title не может быть пустым"})
                return
            with STATE_LOCK:
                for note in NOTES:
                    if note["id"] == note_id:
                        note["title"] = title
                        note["text"] = text
                        self.send_json(
                            200,
                            {
                                "status": 200,
                                "updated": dict(note),
                                "explanation": "PUT обновил существующую запись на сервере по её ID.",
                            },
                        )
                        return
            self.send_json(404, {"error": f"Заметка #{note_id} не найдена"})
            return

        self.send_json(404, {"error": f"Маршрут PUT {path} не найден"})

    # ------------------------------------------------------------------
    # HTTP DELETE
    # ------------------------------------------------------------------
    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/methods/notes/"):
            id_str = path.rsplit("/", 1)[-1]
            try:
                note_id = int(id_str)
            except ValueError:
                self.send_json(400, {"error": "Некорректный ID заметки"})
                return
            with STATE_LOCK:
                for idx, note in enumerate(NOTES):
                    if note["id"] == note_id:
                        removed = NOTES.pop(idx)
                        self.send_json(
                            200,
                            {
                                "status": 200,
                                "deleted": removed,
                                "explanation": "DELETE удалил ресурс на сервере по его ID.",
                            },
                        )
                        return
            self.send_json(404, {"error": f"Заметка #{note_id} не найдена"})
            return

        self.send_json(404, {"error": f"Маршрут DELETE {path} не найден"})


def bind_server(host: str, start_port: int, strict_port: bool = False) -> tuple[ThreadingHTTPServer, int]:
    max_tries = 1 if strict_port else 20
    for offset in range(max_tries):
        port = start_port + offset
        try:
            srv = ThreadingHTTPServer((host, port), WebLabHandler)
            return srv, port
        except OSError:
            if strict_port:
                raise
            continue
    raise RuntimeError(f"Не удалось найти свободный порт в диапазоне {start_port}..{start_port + max_tries - 1}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="WebLab Модуль 1: Учебный сервер HTTP, Cookies, Статус-коды и DevTools")
    parser.add_argument("--host", default=None, help="Хост привязки (по умолчанию 127.0.0.1, либо 0.0.0.0 при переменной PORT)")
    parser.add_argument("--port", type=int, default=None, help="Начальный порт (по умолчанию 8080, либо переменная PORT)")
    parser.add_argument("--no-browser", action="store_true", help="Не открывать браузер автоматически")
    args = parser.parse_args()

    env_port_raw = os.environ.get("PORT", "").strip()
    has_env_port = bool(env_port_raw)
    port = args.port if args.port is not None else (int(env_port_raw) if has_env_port else 8080)
    host = args.host if args.host is not None else ("0.0.0.0" if has_env_port else "127.0.0.1")
    strict_port = has_env_port
    no_browser = args.no_browser or has_env_port

    srv, port = bind_server(host, port, strict_port=strict_port)
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    print("=" * 66)
    print("  WebLab Модуль 1 — Интерактивный тренажёр по вебу и DevTools")
    print(f"  Сервер запущен: http://{host}:{port} (локально: {url})")
    print("  Нажми Ctrl+C в этом окне, чтобы остановить сервер.")
    print("=" * 66)

    if not no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановка сервера...")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
